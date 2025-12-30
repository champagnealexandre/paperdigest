import feedparser
import os
import json
import datetime
from lib import utils, hunter, ai, feed as feed_gen

def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

def main():
    config = load_config()
    
    # Setup AI
    api_key = os.getenv("OPENROUTER_API_KEY")
    client = ai.get_client(api_key)
    
    primary_model = ai.MODEL_MAP.get(config['model_tier'], "openai/gpt-4o-mini")
    shadow_model = ai.MODEL_MAP.get(1) if config['shadow_mode'] else None
    
    all_keywords = list(set(config['keywords_astro'] + config['keywords_ool']))
    
    print("Fetching RSS feeds...")
    rss_links = config['rss_urls']
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
    
    history = utils.load_history(config['history_file'])
    existing_titles = {item.get('title') for item in history}
    new_hits = []

    for link in rss_links:
        print(f"-> Parsing {link[:40]}...")
        feed = feedparser.parse(link)
        
        raw_feed_title = getattr(feed.feed, 'title', 'General')
        clean_category = raw_feed_title.split(' via ')[0]
        feed_category = clean_category.upper()

        for entry in feed.entries:
            if entry.title in existing_titles: continue
            
            pub_date = datetime.datetime.now(datetime.timezone.utc)
            if hasattr(entry, 'published_parsed'):
                 pub_date = datetime.datetime(*entry.published_parsed[:6]).replace(tzinfo=datetime.timezone.utc)

            if pub_date < cutoff: continue
            
            source_title = "Unknown"
            if hasattr(entry, 'source') and hasattr(entry.source, 'title'):
                source_title = entry.source.title
            if source_title == "Unknown": source_title = "Web" 
            
            # --- 1. RUN HUNTER FIRST ---
            print(f"   [Hunter] Scanning {entry.link[:40]}...")
            hunted_links = hunter.hunt_paper_links(entry.link, config['academic_domains'])
            
            # --- 2. ANALYZE ---
            analysis_primary = ai.analyze_paper(
                client,
                primary_model,
                entry.title, 
                getattr(entry, 'description', ''), 
                hunted_links,
                all_keywords,
                config['custom_instructions']
            )
            score_primary = analysis_primary['score']
            
            score_shadow = None
            if config['shadow_mode']:
                analysis_shadow = ai.analyze_paper(
                    client,
                    shadow_model,
                    entry.title, 
                    getattr(entry, 'description', ''), 
                    hunted_links,
                    all_keywords,
                    config['custom_instructions']
                )
                score_shadow = analysis_shadow['score']

            paper_obj = {
                "title": entry.title,
                "link": entry.link, 
                "score": score_primary,
                "summary": analysis_primary['summary'],
                "extracted_links": hunted_links,
                "abstract": getattr(entry, 'description', ''),
                "published": pub_date.isoformat(),
                "category": feed_category,
                "feed_source": source_title
            }

            new_hits.append(paper_obj)
            existing_titles.add(entry.title)

            if score_primary >= 40:
                print(f"✅ ACCEPTED [{score_primary}]: {entry.title}")
                utils.log_decision(entry.title, score_primary, score_shadow, "✅ Accepted", entry.link)
            else:
                print(f"❌ REJECTED [{score_primary}]: {entry.title}")
                utils.log_decision(entry.title, score_primary, score_shadow, "❌ Rejected", entry.link)

    if new_hits:
        print(f"Processed {len(new_hits)} papers.")
        updated_history = new_hits + history
        utils.save_history(updated_history, config['history_file'])
        feed_gen.generate_manual_atom(updated_history, config)
    else:
        feed_gen.generate_manual_atom(history, config)
        print("No new papers, but feed regenerated.")

if __name__ == "__main__":
    main()