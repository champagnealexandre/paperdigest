import os
import yaml
import datetime
from lib import utils, hunter, ai, feed as feed_gen, rss

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def main():
    config = load_config()
    
    # Setup AI
    api_key = os.getenv("OPENROUTER_API_KEY")
    client = ai.get_client(api_key)
    
    primary_model = config['models'].get(str(config['model_tier']), "openai/gpt-5.2")
    
    all_keywords = list(set(config['keywords_astro'] + config['keywords_ool']))
    
    print("Fetching RSS feeds...")
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
    
    history = utils.load_history(config['history_file'])
    existing_titles = {item.get('title') for item in history}
    
    feed_items = rss.fetch_new_entries(config['rss_urls'], existing_titles, cutoff)
    new_hits = []

    for item in feed_items:
            entry = item['entry']
            feed_category = item['category']
            
            # --- 1. RUN HUNTER FIRST ---
            print(f"   [Hunter] Scanning {entry.link[:40]}...")
            hunted_links = hunter.hunt_paper_links(entry.link, config['academic_domains'])
            
            # --- 2. ANALYZE ---
            analysis_primary = ai.analyze_paper(
                client,
                primary_model,
                config.get('model_prompt', ''),
                entry.title, 
                getattr(entry, 'description', ''), 
                hunted_links,
                all_keywords,
                config['custom_instructions'],
                temperature=config.get('model_temperature', 0.1)
            )
            score_primary = analysis_primary['score']
            
            paper_obj = {
                "title": entry.title,
                "link": entry.link, 
                "score": score_primary,
                "summary": analysis_primary['summary'],
                "extracted_links": hunted_links,
                "abstract": getattr(entry, 'description', ''),
                "published": item['pub_date'].isoformat(),
                "category": feed_category,
                "feed_source": item['source_title']
            }

            new_hits.append(paper_obj)
            existing_titles.add(entry.title)

            if score_primary >= 0:
                print(f"✅ ACCEPTED [{score_primary}]: {entry.title}")
                utils.log_decision(entry.title, score_primary, "✅ Accepted", entry.link)
            else:
                print(f"❌ REJECTED [{score_primary}]: {entry.title}")
                utils.log_decision(entry.title, score_primary, "❌ Rejected", entry.link)

    if new_hits:
        print(f"Processed {len(new_hits)} papers.")
        updated_history = new_hits + history
        utils.save_history(updated_history, config['history_file'])
        papers_to_gen = updated_history
    else:
        papers_to_gen = history
        print("No new papers, but feed regenerated.")

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