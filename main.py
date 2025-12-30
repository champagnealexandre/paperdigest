import feedparser
import os
import json
import datetime
import html
import requests
import re
from openai import OpenAI
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# --- Configuration ---
RSS_URLS = [
    "https://www.inoreader.com/stream/user/1005369328/tag/keywords-ool",
    "https://www.inoreader.com/stream/user/1005369328/tag/keywords-astrobiology",
    "https://www.inoreader.com/stream/user/1005369328/tag/ool-ressources"
]
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
HISTORY_FILE = "paper_history.json"
BASE_URL = "https://alexandrechampagne.io/ooldigest"
FEED_URL = f"{BASE_URL}/feed.xml"

# --- MODEL SELECTION (OpenRouter) ---
# Select a tier (1-4) from Lightest to Most Advanced:
# 1: Google Gemini Flash 1.5 (Fastest, High Context, Very Cheap)
# 2: OpenAI GPT-4o Mini (Standard "Light" Model)
# 3: Google Gemini Pro 1.5 (High Reasoning, Large Context)
# 4: OpenAI GPT-4o (Flagship, Best Instruction Following)
MODEL_TIER = 2  # <--- CHANGED TO MINI

MODEL_MAP = {
    1: "google/gemini-flash-1.5",
    2: "openai/gpt-4o-mini",
    3: "google/gemini-pro-1.5",
    4: "openai/gpt-4o"
}

PRIMARY_MODEL = MODEL_MAP.get(MODEL_TIER, "openai/gpt-4o-mini")

# --- TOGGLES ---
SHADOW_MODE = False        
SHADOW_MODEL = MODEL_MAP[1] # Compare against the lightest model (Tier 1)

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

# --- DOMAINS TO HUNT ---
ACADEMIC_DOMAINS = [
    "doi.org", "arxiv.org", "biorxiv.org", "ncbi.nlm.nih.gov", 
    "nature.com", "science.org", "pnas.org", "acs.org", "wiley.com", 
    "springer.com", "cell.com", "oup.com", "iop.org", "aps.org",
    "sciencedirect.com", "elsevier.com", "linkinghub.elsevier.com",
    "mdpi.com", "frontiersin.org", "tandfonline.com",
    "sagepub.com", "ieee.org", "osapublishing.org", "optica.org", 
    "aanda.org", "agu.org", "geoscienceworld.org", "gsapubs.org"
]

# Initialize Client with OpenRouter Base URL
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    default_headers={
        "HTTP-Referer": "https://alexandrechampagne.io", 
        "X-Title": "OOL Digest Agent",
    }
)

# --- ACTIVE LINK HUNTER ---
def hunt_paper_links(url):
    found_links = set()
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        
        # 1. Regex DOI Scan
        doi_pattern = r'10\.\d{4,9}/[-._;()/:A-Z0-9a-z]+'
        dois = re.findall(doi_pattern, response.text)
        for doi in dois:
            clean_doi = doi.rstrip('.,)')
            found_links.add(f"https://doi.org/{clean_doi}")

        # 2. Standard Domain Scan
        soup = BeautifulSoup(response.text, 'html.parser')
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if not href.startswith('http'): continue
            
            if url in href: continue 

            if any(domain in href for domain in ACADEMIC_DOMAINS):
                found_links.add(href)

    except Exception as e:
        print(f"   [Hunter] Failed to scrape {url}: {e}")
    
    return list(found_links)

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
    
    title_display = title.replace(" ", "&nbsp;")
    entry = f"| {timestamp} | {shadow_val} | **{score_primary}** | {delta_str} | {action} | [{title_display}]({link}) |\n"
    
    if not os.path.exists(log_file):
        with open(log_file, 'w') as f:
            f.write(f"# Decision Log: {month_str}\n\n")
            f.write("| Date (UTC) | Shadow | Primary | Diff | Action | Paper |\n")
            f.write("|---|---|---|---|---|---|\n")
            
    with open(log_file, 'a') as f:
        f.write(entry)

# --- ANALYZER ---
def analyze_paper(title, abstract, model_name, found_links=None):
    if found_links is None: found_links = []
    
    keywords_str = ", ".join(ALL_KEYWORDS)
    links_str = ", ".join(found_links) if found_links else "None found."

    prompt = f"""
    Role: Senior Astrobiologist.
    Task: Score this paper for an 'Origins of Life' digest.
    
    Paper: "{title}"
    Abstract: "{abstract}"
    
    EVIDENCE FROM LINK HUNTER:
    The following academic links were found on the source page:
    {links_str}
    
    Target Keywords:
    {keywords_str}
    
    CUSTOM INSTRUCTIONS:
    {CUSTOM_INSTRUCTIONS}
    
    SCORING RUBRIC (Total /100):
    
    1. BASE RELEVANCE (Max 50 pts):
       - +0: Unrelated field.
       - +25: Broad context.
       - +50: Core OoL focus.
       * BONUS: If "Link Hunter" found a DOI/Nature/Science/Elsevier link, ensure score is robust.
       
    2. KEYWORD BONUS (Max 50 pts):
       - +10 points per keyword match. Caps at 50.
    
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
        with open(HISTORY_FILE, 'r') as f: return json.load(f)
    return []

def save_history(data):
    with open(HISTORY_FILE, 'w') as f: json.dump(data[:200], f, indent=2)

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
        score = p.get('score', 0)
        if score < 40: continue

        title_raw = clean_text(p.get('title', 'Untitled'))
        category = p.get('category', 'GENERAL')
        feed_source = p.get('feed_source', 'Unknown')
        
        display_title = f"[{score}] [{category}] [{feed_source}] {title_raw}"
        display_title_esc = html.escape(display_title)
        
        summary = html.escape(clean_text(p.get('summary', 'No summary')))
        abstract = html.escape(clean_text(p.get('abstract', '')))
        link = html.escape(p.get('link', ''))
        
        extracted_links = p.get('extracted_links', [])
        doi_html = ""
        
        is_direct_paper = any(domain in link for domain in ACADEMIC_DOMAINS)
        
        if is_direct_paper:
             doi_html = f"<br/><br/><strong>Source Paper:</strong><ul><li><a href='{link}'>Direct Journal Link (Original Article)</a></li></ul>"
        elif extracted_links:
             unique_links = sorted(list(set(extracted_links)))
             doi_html = "<br/><br/><strong>Source Paper / DOIs Found:</strong><ul>"
             for url in unique_links:
                 safe_url = html.escape(url)
                 label = "Full Paper"
                 if "doi.org" in url: label = "DOI Link"
                 elif "arxiv" in url: label = "ArXiv Preprint"
                 elif "ncbi" in url: label = "PubMed/NCBI"
                 elif "sciencedirect" in url or "elsevier" in url: label = "ScienceDirect"
                 doi_html += f'<li><a href="{safe_url}">[{label}] {safe_url}</a></li>'
             doi_html += "</ul>"
        else:
             doi_html = "<br/><br/><strong>Source Paper:</strong><br/>No direct link found."
        
        pub_date = p.get('published', now_iso)
        while pub_date in seen_dates:
            try:
                dt = datetime.datetime.fromisoformat(pub_date)
                dt += datetime.timedelta(seconds=1)
                pub_date = dt.isoformat()
            except: break
        seen_dates.add(pub_date)
        
        content_html = f"""
        <strong>Category:</strong> {html.escape(category)}<br/>
        <strong>Source:</strong> {html.escape(feed_source)}<br/>
        <strong>Score:</strong> {score}/100<br/>
        <strong>AI Summary:</strong> {summary}<br/>
        <hr/>
        <strong>Abstract:</strong><br/>
        {abstract}
        {doi_html}
        <br/><br/>
        <a href="{link}">Read Full Article</a>
        """
        
        entry = f"""
  <entry>
    <title>{display_title_esc}</title>
    <link href="{link}"/>
    <id>{link}</id>
    <updated>{pub_date}</updated>
    <summary>{summary}</summary>
    <content type="html">{html.escape(content_html)}</content>
  </entry>
"""
        xml_content += entry

    xml_content += "</feed>"
    with open("feed.xml", "w", encoding='utf-8') as f: f.write(xml_content)

def main():
    print("Fetching RSS feeds...")
    rss_links = RSS_URLS
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
    history = load_history()
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
            hunted_links = hunt_paper_links(entry.link)
            
            # --- 2. ANALYZE ---
            analysis_primary = analyze_paper(
                entry.title, 
                getattr(entry, 'description', ''), 
                PRIMARY_MODEL,
                found_links=hunted_links
            )
            score_primary = analysis_primary['score']
            
            score_shadow = None
            if SHADOW_MODE:
                analysis_shadow = analyze_paper(
                    entry.title, 
                    getattr(entry, 'description', ''), 
                    SHADOW_MODEL,
                    found_links=hunted_links
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
                log_decision(entry.title, score_primary, score_shadow, "✅ Accepted", entry.link)
            else:
                print(f"❌ REJECTED [{score_primary}]: {entry.title}")
                log_decision(entry.title, score_primary, score_shadow, "❌ Rejected", entry.link)

    if new_hits:
        print(f"Processed {len(new_hits)} papers.")
        updated_history = new_hits + history
        save_history(updated_history)
        generate_manual_atom(updated_history)
    else:
        generate_manual_atom(history)
        print("No new papers, but feed regenerated.")

if __name__ == "__main__":
    main()