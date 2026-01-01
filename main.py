import os
import yaml
import datetime
import logging
import concurrent.futures
import feedparser
import time
from time import mktime
from lib import utils, hunter, ai, feed as feed_gen
from lib.config_schema import Config

def load_config() -> dict:
    with open("config.yaml", "r") as f:
        raw_config = yaml.safe_load(f)
    # Validate with Pydantic
    config_model = Config(**raw_config)
    # Return as dict to maintain compatibility with existing code
    return config_model.model_dump()

def load_feeds_config():
    with open("feeds.yaml", "r") as f:
        config = yaml.safe_load(f)
    all_feeds = []
    for category, feeds_in_category in config.get('feed_categories', {}).items():
        if feeds_in_category:
            all_feeds.extend(feeds_in_category)
    return all_feeds

def determine_category(text, config):
    text = text.lower()
    if any(k.lower() in text for k in config['keywords_ool']):
        return 'KEYWORDS-OOL'
    if any(k.lower() in text for k in config['keywords_astro']):
        return 'KEYWORDS-ASTROBIOLOGY'
    return 'KEYWORDS-OOL'

def filter_by_keywords(entry, keywords):
    text_content = (entry.get('title', '') + " " + 
                    entry.get('summary', '') + " " + 
                    entry.get('description', '')).lower()
    if 'tags' in entry:
        for tag in entry.tags:
            text_content += " " + tag.term.lower()

    for keyword in keywords:
        if keyword.lower() in text_content:
            return True
    return False

def append_decision(filename, title, score, status, link):
    try:
        with open(filename, "a") as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"- **{timestamp}** {status} | Score: {score} | [{title}]({link})\n")
    except Exception as e:
        logging.error(f"Failed to write to {filename}: {e}")

def fetch_feed(feed_config, existing_links, keywords, cutoff_date):
    url = feed_config['url']
    feed_title = feed_config['title']
    relevant_entries = []
    
    logging.info(f"Fetching {feed_title}...")
    
    try:
        parsed = feedparser.parse(url)
        for entry in parsed.entries:
            link = entry.get('link')
            if not link or link in existing_links:
                continue
            
            published = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published = datetime.datetime.fromtimestamp(mktime(entry.published_parsed), datetime.timezone.utc)
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                published = datetime.datetime.fromtimestamp(mktime(entry.updated_parsed), datetime.timezone.utc)
            
            if published and published < cutoff_date:
                continue

            title = entry.get('title', 'No Title')
            if filter_by_keywords(entry, keywords):
                logging.info(f"Keyword MATCH: {title}")
                append_decision("logs/keyword-decisions.md", title, "N/A", "MATCH", link)
                relevant_entries.append({
                    'entry': entry,
                    'source_title': feed_title,
                    'pub_date': published if published else datetime.datetime.now(datetime.timezone.utc)
                })
            else:
                append_decision("logs/keyword-decisions.md", title, "N/A", "REJECT", link)
    except Exception as e:
        logging.error(f"Error fetching {url}: {e}")
        
    return relevant_entries

def process_feed_item(item, config, client, all_keywords):
    """
    Worker function to process a single paper:
    1. Scrape links (Hunter)
    2. Analyze with AI
    3. Return the result object
    """
    entry = item['entry']
    
    # Determine category based on content
    content_text = (entry.get('title', '') + " " + 
                    entry.get('summary', '') + " " + 
                    entry.get('description', '')).lower()
    feed_category = determine_category(content_text, config)
    
    logging.info(f"[Hunter] Scanning {entry.link[:40]}...")
    hunted_links = hunter.hunt_paper_links(entry.link, config['academic_domains'])
    
    # Analyze
    analysis_primary = ai.analyze_paper(
        client,
        config['models'].get(str(config['model_tier']), "openai/gpt-5.2"),
        config.get('model_prompt', ''),
        entry.title, 
        getattr(entry, 'description', ''), 
        hunted_links,
        all_keywords,
        config['custom_instructions'],
        temperature=config.get('model_temperature', 0.1)
    )
    
    return {
        "paper": entry,
        "analysis": analysis_primary,
        "links": hunted_links,
        "category": feed_category,
        "source": item['source_title'],
        "pub_date": item['pub_date']
    }

def setup_logging():
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    log_filename = f"logs/run_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()
        ]
    )

def main():
    # Setup Logging
    setup_logging()

    config = load_config()
    
    # Setup AI
    api_key = os.getenv("OPENROUTER_API_KEY")
    client = ai.get_client(api_key)
    
    all_keywords = list(set(config['keywords_astro'] + config['keywords_ool']))
    
    logging.info("Fetching RSS feeds...")
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
    
    history = utils.load_history(config['history_file'])
    existing_links = {item.get('link') for item in history}
    
    feeds = load_feeds_config()
    feed_items = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [
            executor.submit(fetch_feed, feed, existing_links, all_keywords, cutoff) 
            for feed in feeds
        ]
        for future in concurrent.futures.as_completed(futures):
            feed_items.extend(future.result())
            
    logging.info(f"Found {len(feed_items)} candidates matching keywords.")
    
    new_hits = []

    # Parallel Execution
    # We use max_workers=10 to be polite to servers, but you can increase this.
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.get('max_workers', 10)) as executor:
        future_to_item = {
            executor.submit(process_feed_item, item, config, client, all_keywords): item 
            for item in feed_items
        }

        for future in concurrent.futures.as_completed(future_to_item):
            try:
                result = future.result()
                entry = result['paper']
                score = result['analysis']['score']
                
                paper_obj = {
                    "title": entry.title,
                    "link": entry.link, 
                    "score": score,
                    "summary": result['analysis']['summary'],
                    "extracted_links": result['links'],
                    "abstract": getattr(entry, 'description', ''),
                    "published": result['pub_date'].isoformat(),
                    "category": result['category'],
                    "feed_source": result['source']
                }
                
                new_hits.append(paper_obj)
                
                if score >= 0:
                    logging.info(f"✅ ACCEPTED [{score}]: {entry.title}")
                    append_decision("logs/ai-decisions.md", entry.title, score, "✅ Accepted", entry.link)
                else:
                    logging.info(f"❌ REJECTED [{score}]: {entry.title}")
                    append_decision("logs/ai-decisions.md", entry.title, score, "❌ Rejected", entry.link)

            except Exception as e:
                logging.error(f"⚠️ Error processing a paper: {e}")

    if new_hits:
        logging.info(f"Processed {len(new_hits)} papers.")
        updated_history = new_hits + history
        utils.save_history(updated_history, config['history_file'])
        papers_to_gen = updated_history
    else:
        papers_to_gen = history
        logging.info("No new papers, but feed regenerated.")

    # 1. Generate Aggregate Feed
    feed_gen.generate_feed(papers_to_gen, config, "all.xml", "All")

    # 2. Generate Category Feeds
    categories = set(p.get('category') for p in papers_to_gen if p.get('category'))
    for cat in categories:
        cat_papers = [p for p in papers_to_gen if p.get('category') == cat]
        safe_filename = cat.lower().strip() + ".xml"
        feed_gen.generate_feed(cat_papers, config, safe_filename, cat)

if __name__ == "__main__":
    main()