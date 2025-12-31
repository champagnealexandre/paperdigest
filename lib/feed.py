import datetime
import html
import os
from typing import List, Dict, Any, Set
from jinja2 import Environment, FileSystemLoader, select_autoescape
from .utils import clean_text

def get_score_emoji(score: int) -> str:
    if score < 20: return "🟤"
    if score < 40: return "🔴"
    if score < 60: return "🟠"
    if score < 80: return "🟡"
    return "🟢"

def shorten_source_name(feed_source: str) -> str:
    short_source = feed_source
    for sep in [" - ", " | ", ": "]:
        if sep in short_source:
            parts = short_source.split(sep)
            if parts[0].strip().lower() == "master feed" and len(parts) > 1:
                short_source = parts[1].strip()
            else:
                short_source = parts[0].strip()
            break
    return short_source

def prepare_entry_data(p: Dict[str, Any], academic_domains: List[str], seen_dates: Set[str]) -> Dict[str, Any]:
    score = p.get('score', 0)
    if score < 0: return {}

    emoji = get_score_emoji(score)
    title_raw = clean_text(p.get('title', 'Untitled'))
    feed_source = p.get('feed_source', 'Unknown')
    short_source = shorten_source_name(feed_source)
    
    display_title = f"{emoji} {short_source} ➤ {title_raw}"
    # Jinja2 will handle escaping for the title
    
    summary = clean_text(p.get('summary', 'No summary'))
    abstract = html.escape(clean_text(p.get('abstract', '')))
    link = html.escape(p.get('link', ''))
    
    extracted_links = p.get('extracted_links', [])
    doi_html = ""
    
    is_direct_paper = any(domain in link for domain in academic_domains)
    
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
    
    # Handle date deduplication
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    pub_date = p.get('published', now_iso)
    while pub_date in seen_dates:
        try:
            dt = datetime.datetime.fromisoformat(pub_date)
            dt += datetime.timedelta(seconds=1)
            pub_date = dt.isoformat()
        except: break
    seen_dates.add(pub_date)
    
    content_html = f"""
    <hr/>
    <strong>Abstract:</strong><br/>
    {abstract}
    {doi_html}
    <br/><br/>
    <a href="{link}">Read Full Article</a>
    """
    
    return {
        "display_title": display_title,
        "link": link,
        "pub_date": pub_date,
        "summary": summary,
        "content_html": html.escape(content_html)
    }

def generate_feed(papers: List[Dict[str, Any]], config: Dict[str, Any], filename: str, title_suffix: str = ""):
    os.makedirs("public", exist_ok=True)
    output_path = os.path.join("public", filename)
    feed_url = f"{config['base_url']}/{filename}"
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    full_title = "Astrobiology AI Digest"
    if title_suffix:
        full_title += f" - {title_suffix}"

    seen_dates = set()
    academic_domains = config['academic_domains']
    
    entries = []
    for p in papers:
        entry_data = prepare_entry_data(p, academic_domains, seen_dates)
        if entry_data:
            entries.append(entry_data)

    env = Environment(
        loader=FileSystemLoader("templates"),
        autoescape=select_autoescape(['xml'])
    )
    template = env.get_template("feed.xml")
    
    with open(output_path, "w", encoding='utf-8') as f:
        f.write(template.render(
            full_title=full_title,
            feed_url=feed_url,
            now_iso=now_iso,
            entries=entries
        ))