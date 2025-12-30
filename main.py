import feedparser
import os
import json
import datetime
import html
from openai import OpenAI
from bs4 import BeautifulSoup

# --- Configuration ---
RSS_URL = os.getenv("RSS_URL") 
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
HISTORY_FILE = "paper_history.json"
BASE_URL = "https://alexandrechampagne.io/ooldigest"
FEED_URL = f"{BASE_URL}/feed.xml"

# KEYWORDS
KEYWORDS_ASTRO = [
    "astrobiological", "astrobiology", "astrochemistry", "biosignature", 
    "exoplanet", "habitability", "habitable", "mars", "planetesimal", "venus"
]

KEYWORDS_OOL = [
    "prebiotic", "origin of life", "autocatalysis", "autocatalytic", 
    "chirality", "protocell", "self-assembly", "nucleic acid", "eukaryo", 
    "water", "origins of life", "RNA", "DNA", "evolution", "protobiotic", 
    "multicellularity", "abiogenesis"
]

ALL_KEYWORDS = list(set(KEYWORDS_ASTRO + KEYWORDS_OOL))

client = OpenAI(api_key=OPENAI_API_KEY)

# --- LOGGING FUNCTION ---
def log_decision(title, score, action, link):
    os.makedirs("logs", exist_ok=True)
    month_str = datetime.datetime.now().strftime("%Y-%m")
    log_file = f"logs/decisions-{month_str}.md"
    timestamp = datetime.datetime.now().strftime("%d %H:%M")
    
    entry = f"| {timestamp} | **{score}** | {action} | [{title}]({link}) |\n"
    
    if not os.path.exists(log_file):
        with open(log_file, 'w') as f:
            f.write(f"# Decision Log: {month_str}\n\n")
            f.write("| Date (UTC) | Score | Action | Paper |\n")
            f.write("|---|---|---|---|\n")
            
    with open(log_file, 'a') as f:
        f.write(entry)

def analyze_paper(title, abstract):
    keywords_str = ", ".join(ALL_KEYWORDS)
    
    prompt = f"""
    Role: Senior Astrobiologist.
    Task: Score this paper for an 'Origins of Life' digest based ONLY on relevance and keywords.
    
    Paper: "{title}"
    Abstract: "{abstract}"
    
    Target Keywords:
    {keywords_str}
    
    SCORING RUBRIC (Total /100):
    
    1. BASE RELEVANCE (Max 50 pts):
       - +0: Unrelated field (e.g., medicine, galaxy formation, dark matter).
       - +25: Broad context (e.g., general planetology, star formation).
       - +50: Core OoL focus (abiogenesis, prebiotic chemistry, biosignatures).
       
    2. KEYWORD BONUS (Max 50 pts):
       - Count occurrences of Target Keywords in the Title/Abstract.
       - Add +10 points for EACH occurrence.
       - Cap this bonus at 50 points.
    
    CALCULATION: Sum (Base Relevance + Keyword Bonus).
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
        print(f"LLM Error: {e}")
        return {"score": 0, "summary": "Error"}

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    return []

def save_history(data):
    with open(HISTORY_FILE, 'w') as f:
        json.dump(data[:60], f, indent=2)

def clean_text(text):
    if not text: return ""
    text = BeautifulSoup(text, "html.parser").get_text(separator=' ')
    return " ".join(text.split())

def generate_manual_atom(papers):
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    xml_content = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Astrobiology AI Digest</title>
  <subtitle>Hourly AI-curated papers on Origins of Life</subtitle>
  <link href="{FEED_URL}" rel="self"/>
  <link href="https://github.com/champagnealexandre/ooldigest"/>
  <updated>{now_iso}</updated>
  <id>{FEED_URL}</id>
  <author><name>AI Agent</name></author>
"""
    seen_dates = set()

    for p in papers:
        title = html.escape(clean_text(p.get('title', 'Untitled')))
        summary = html.escape(clean_text(p.get('summary', 'No summary')))
        abstract = html.escape(clean_text(p.get('abstract', '')))
        score = p.get('score', 0)
        link = html.escape(p.get('link', ''))
        
        pub_date = p.get('published', now_iso)
        while pub_date in seen_dates:
            try:
                dt = datetime.datetime.fromisoformat(pub_date)
                dt += datetime.timedelta(seconds=1)
                pub_date = dt.isoformat()
            except: break
        seen_dates.add(pub_date)
        
        content_html = f"""
        <strong>Score:</strong> {score}/100<br/>
        <strong>AI Summary:</strong> {summary}<br/>
        <hr/>
        <strong>Abstract:</strong><br/>
        {abstract}<br/>
        <br/>
        <a href="{link}">Read Full Paper</a>
        """
        content_escaped = html.escape(content_html)
        
        entry = f"""
  <entry>
    <title>[{score}] {title}</title>
    <link href="{link}"/>
    <id>{link}</id>
    <updated>{pub_date}</updated>
    <summary>{summary}</summary>
    <content type="html">{content_escaped}</content>
  </entry>
"""
        xml_content += entry

    xml_content += "</feed>"
    
    with open("feed.xml", "w", encoding='utf-8') as f:
        f.write(xml_content)

def main():
    print("Fetching RSS feeds...")
    raw_urls = os.getenv("RSS_URL", "")
    rss_links = [url.strip() for url in raw_urls.split(',') if url.strip()]
    
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
    history = load_history()
    existing_titles = {item.get('title') for item in history}
    new_hits = []

    for link in rss_links:
        print(f"-> Parsing {link[:40]}...")
        feed = feedparser.parse(link)
        
        for entry in feed.entries:
            if entry.title in existing_titles:
                continue
            
            pub_date = datetime.datetime.now(datetime.timezone.utc)
            if hasattr(entry, 'published_parsed'):
                 pub_date = datetime.datetime(*entry.published_parsed[:6]).replace(tzinfo=datetime.timezone.utc)

            if pub_date < cutoff:
                continue

            analysis = analyze_paper(entry.title, getattr(entry, 'description', ''))
            score = analysis['score']
            
            if score >= 75:
                print(f"✅ ACCEPTED [{score}]: {entry.title}")
                log_decision(entry.title, score, "✅ Accepted", entry.link)
                
                new_hits.append({
                    "title": entry.title,
                    "link": entry.link, 
                    "score": score,
                    "summary": analysis['summary'],
                    "abstract": getattr(entry, 'description', ''),
                    "published": pub_date.isoformat()
                })
                existing_titles.add(entry.title)
            else:
                print(f"❌ REJECTED [{score}]: {entry.title}")
                log_decision(entry.title, score, "❌ Rejected", entry.link)

    if new_hits:
        print(f"Found {len(new_hits)} new papers total.")
        updated_history = new_hits + history
        save_history(updated_history)
        generate_manual_atom(updated_history)
    else:
        generate_manual_atom(history)
        print("No new papers, but feed regenerated.")

if __name__ == "__main__":
    main()