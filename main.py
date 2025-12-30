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

# --- TOGGLES ---
SHADOW_MODE = False        
PRIMARY_MODEL = "gpt-4o"   
SHADOW_MODEL = "gpt-4o-mini" 

# --- CUSTOM INSTRUCTIONS ---
CUSTOM_INSTRUCTIONS = """
- EXOPLANET FILTER: Deprioritize generic exoplanet discoveries (e.g., new TESS candidates, hot Jupiters) unless they significantly advance Astrobiology.
- EXCEPTION 1: Always prioritize papers related to the TRAPPIST-1 system.
- EXCEPTION 2: Prioritize atmospheric observations specifically relevant to life detection (biosignatures) or habitability.
"""

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
def log_decision(title, score_primary, score_shadow, action, link):
    os.makedirs("logs", exist_ok=True)
    month_str = datetime.datetime.now().strftime("%Y-%m")
    log_file = f"logs/decisions-{month_str}.md"
    timestamp = datetime.datetime.now().strftime("%d %H:%M")
    
    if score_shadow is not None:
        delta = score_primary - score_shadow
        delta_str = f"+{delta}" if delta > 0 else str(delta)
        shadow_val = score_shadow
    else:
        delta_str = "N/A"
        shadow_val = "N/A"
    
    entry = f"| {timestamp} | {shadow_val} | **{score_primary}** | {delta_str} | {action} | [{title}]({link}) |\n"
    
    if not os.path.exists(log_file):
        with open(log_file, 'w') as f:
            f.write(f"# Decision Log: {month_str}\n\n")
            f.write("| Date (UTC) | Mini (Shadow) | 4o (Primary) | Diff | Action | Paper |\n")
            f.write("|---|---|---|---|---|---|\n")
            
    with open(log_file, 'a') as f:
        f.write(entry)

def analyze_paper(title, abstract, model_name):
    keywords_str = ", ".join(ALL_KEYWORDS)
    
    prompt = f"""
    Role: Senior Astrobiologist.
    Task: Score this paper for an 'Origins of Life' digest based on relevance, keywords, and specific constraints.
    
    Paper: "{title}"
    Abstract: "{abstract}"
    
    Target Keywords:
    {keywords_str}
    
    CUSTOM INSTRUCTIONS (Override standard scoring):
    {CUSTOM_INSTRUCTIONS}
    
    SCORING RUBRIC (Total /100):
    
    1. BASE RELEVANCE (Max 50 pts):
       - +0: Unrelated field.
       - +25: Broad context.
       - +50: Core OoL focus.
       * PENALTY: If paper violates "Custom Instructions" (e.g. generic exoplanet), cap this section at 10 pts.
       * BONUS: If paper hits an "Exception" in instructions, ensure this section is at least 40 pts.
       
    2. KEYWORD BONUS (Max 50 pts):
       - Count occurrences of Target Keywords in the Title/Abstract.
       - Add +10 points for EACH occurrence.
       - Cap this bonus at 50 points.
    
    CALCULATION: Sum (Base Relevance + Keyword Bonus).
    Output JSON ONLY: {{"score": int, "summary": "1 sentence summary"}}
    """
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"LLM Error ({model_name}): {e}")
        return {"score": 0, "summary": "Error"}

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    return []

def save_history(data):
    # Increased limit to 200 to accommodate storing rejected papers
    with open(HISTORY_FILE, 'w') as f:
        json.dump(data[:200], f, indent=2)

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
        # FILTER: Only include Accepted papers in the public feed
        score = p.get('score', 0)
        if score < 40:
            continue

        title = html.escape(clean_text(p.get('title', 'Untitled')))
        summary = html.escape(clean_text(p.get('summary', 'No summary')))
        abstract = html.escape(clean_text(p.get('abstract', '')))
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
            
            # --- INTELLIGENT SCORING ---
            analysis_primary = analyze_paper(entry.title, getattr(entry, 'description', ''), PRIMARY_MODEL)
            score_primary = analysis_primary['score']
            
            score_shadow = None
            if SHADOW_MODE:
                analysis_shadow = analyze_paper(entry.title, getattr(entry, 'description', ''), SHADOW_MODEL)
                score_shadow = analysis_shadow['score']

            # Create Paper Object
            paper_obj = {
                "title": entry.title,
                "link": entry.link, 
                "score": score_primary,
                "summary": analysis_primary['summary'],
                "abstract": getattr(entry, 'description', ''),
                "published": pub_date.isoformat()
            }

            # SAVE ALL (Accepted & Rejected) so we don't re-process them
            new_hits.append(paper_obj)
            existing_titles.add(entry.title)

            if score_primary >= 40:
                print(f"✅ ACCEPTED [{score_primary}]: {entry.title}")
                log_decision(entry.title, score_primary, score_shadow, "✅ Accepted", entry.link)
            else:
                print(f"❌ REJECTED [{score_primary}]: {entry.title}")
                log_decision(entry.title, score_primary, score_shadow, "❌ Rejected", entry.link)

    if new_hits:
        print(f"Processed {len(new_hits)} papers.")
        # Prepend new hits to history
        updated_history = new_hits + history
        save_history(updated_history)
        # Generate Feed (The function now handles the filtering internally)
        generate_manual_atom(updated_history)
    else:
        generate_manual_atom(history)
        print("No new papers, but feed regenerated.")

if __name__ == "__main__":
    main()