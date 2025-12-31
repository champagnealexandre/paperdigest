import feedparser
import datetime

def fetch_new_entries(rss_urls, existing_titles, cutoff):
    found_items = []
    for link in rss_urls:
        print(f"-> Parsing {link[:40]}...")
        try:
            feed = feedparser.parse(link)
            
            raw_feed_title = getattr(feed.feed, 'title', 'General')
            clean_category = raw_feed_title.split(' via ')[0]
            feed_category = clean_category.upper()

            for entry in feed.entries:
                if entry.title in existing_titles: continue
                
                pub_date = datetime.datetime.now(datetime.timezone.utc)
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                     pub_date = datetime.datetime(*entry.published_parsed[:6]).replace(tzinfo=datetime.timezone.utc)

                if pub_date < cutoff: continue
                
                source_title = "Unknown"
                if hasattr(entry, 'source') and hasattr(entry.source, 'title'):
                    source_title = entry.source.title
                if source_title == "Unknown": source_title = "Web"
                
                found_items.append({
                    'entry': entry,
                    'category': feed_category,
                    'source_title': source_title,
                    'pub_date': pub_date
                })
        except Exception as e:
            print(f"Error parsing {link}: {e}")
            
    return found_items