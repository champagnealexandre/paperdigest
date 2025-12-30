import feedparser
import os
import json
import datetime
from openai import OpenAI
from feedgen.feed import FeedGenerator

# --- Configuration ---
RSS_URL = os.getenv("RSS_URL") 
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
HISTORY_FILE = "paper_history.json"
FEED_FILE = "feed.xml"

# Initialize OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

def get_ai_score(title, abstract):
    """
    Sends abstract to GPT-4o-mini for scoring.
    """
    prompt = f"""
    Role: Senior Astrobiologist.
    Task: Score the relevance of this paper to 'Origins of Life' or 'Astrobiology'.
    
    Title: {title}
    Abstract: {abstract}
    
    Rubric:
    0-50: Irrelevant (General astronomy, terrestrial geology, pure biology).
    51-80: Tangential (Extremophiles, planetary formation, instrumentation).
    81-100: Core Breakthrough (Abiogenesis pathways, biosignatures, chemical evolution).
    
    Output JSON ONLY: {{"score": int, "summary": "1 sentence summary"}}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Error processing paper: {e}")
        return {"score": 0, "summary": "Error"}

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    return []

def save_history(data):
    # Keep only the last 50 items to keep the feed manageable
    with open(HISTORY_FILE, 'w') as f:
        json.dump(data[:50], f, indent=2)

def generate_rss(papers):
    fg = FeedGenerator()
    
    # 1. Define the Feed ID and Title
    fg.id('https://github.com/astro-digest')
    fg.title('Astrobiology AI Digest')
    fg.description('Hourly AI-curated papers on Origins of Life')
    
    # 2. Link to the "Human Readable" page (your Repo)
    # (Optional: Replace with your actual repo URL if you want)
    fg.link(href='https://github.com', rel='alternate')
    
    # 3. *** THE FIX *** # Link to the "Feed Itself". Feedly requires this to be accurate.
    # REPLACE THESE VALUES:
    username = "champagnealexandre" 
    repo_name = "ooldigest"      
    
    feed_url = f'https://{username}.github.io/{repo_name}/feed.xml'
    fg.link(href=feed_url, rel='self')
    
    # 4. Add Entries
    for p in papers:
        fe = fg.add_entry()
        fe.id(p['link'])
        # Title format: [Score] [Category] Title
        fe.title(f"[{p['score']}] [{p['category']}] {p['title']}")
        fe.link(href=p['link'])
        
        description = f"""
        <p><b>Score:</b> {p['score']}/100 | <b>Category:</b> {p['category']}</p>
        <p><b>AI Summary:</b> {p['summary']}</p>
        <hr/>
        <p><b>Abstract:</b> {p['abstract']}</p>
        <p><a href="{p['link']}">Read Full Paper</a></p>
        """
        fe.description(description)
        fe.pubDate(p['published'])

    # 5. Generate the file
    fg.rss_file(FEED_FILE)

def main():
    if not RSS_URL or not OPENAI_API_KEY:
        print("Error: Missing Environment Variables.")
        return

    print("Fetching RSS feed...")
    feed = feedparser.parse(RSS_URL)
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
    
    history = load_history()
    existing_links = {item['link'] for item in history}
    new_hits = []

    print(f"Scanning {len(feed.entries)} entries...")

    for entry in feed.entries:
        if entry.link in existing_links:
            continue
            
        # Parse date safely
        pub_date = datetime.datetime.now(datetime.timezone.utc)
        if hasattr(entry, 'published_parsed'):
             pub_date = datetime.datetime(*entry.published_parsed[:6]).replace(tzinfo=datetime.timezone.utc)

        # Only check papers from the last 24h
        if pub_date < cutoff:
            continue

        # AI Analysis
        analysis = get_ai_score(entry.title, getattr(entry, 'description', ''))
        
        # --- THRESHOLD: Adjust this number to filter strictly or loosely ---
        if analysis['score'] >= 75:
            new_hits.append({
                "title": entry.title,
                "link": entry.link,
                "score": analysis['score'],
                "summary": analysis['summary'],
                "abstract": getattr(entry, 'description', ''),
                "published": pub_date.isoformat()
            })

    if new_hits:
        print(f"Found {len(new_hits)} new papers.")
        # Combine new hits with history
        updated_history = new_hits + history
        save_history(updated_history)
        generate_rss(updated_history)
    else:
        print("No new papers found today.")

if __name__ == "__main__":
    main()