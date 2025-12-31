import os
import yaml
import datetime
import logging
import concurrent.futures
from lib import utils, hunter, ai, feed as feed_gen, rss
from lib.config_schema import Config

def load_config() -> dict:
    with open("config.yaml", "r") as f:
        raw_config = yaml.safe_load(f)
    # Validate with Pydantic
    config_model = Config(**raw_config)
    # Return as dict to maintain compatibility with existing code
    return config_model.model_dump()

def process_feed_item(item, config, client, all_keywords):
    """
    Worker function to process a single paper:
    1. Scrape links (Hunter)
    2. Analyze with AI
    3. Return the result object
    """
    entry = item['entry']
    feed_category = item['category']
    
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

def main():
    # Setup Logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )

    config = load_config()
    
    # Setup AI
    api_key = os.getenv("OPENROUTER_API_KEY")
    client = ai.get_client(api_key)
    
    all_keywords = list(set(config['keywords_astro'] + config['keywords_ool']))
    
    logging.info("Fetching RSS feeds...")
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
    
    history = utils.load_history(config['history_file'])
    existing_titles = {item.get('title') for item in history}
    
    feed_items = rss.fetch_new_entries(config['rss_urls'], existing_titles, cutoff)
    new_hits = []

    # Parallel Execution
    # We use max_workers=5 to be polite to servers, but you can increase this.
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
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
                    utils.log_decision(entry.title, score, "✅ Accepted", entry.link)
                else:
                    logging.info(f"❌ REJECTED [{score}]: {entry.title}")
                    utils.log_decision(entry.title, score, "❌ Rejected", entry.link)

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