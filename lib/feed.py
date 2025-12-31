import datetime
import html
import os
from .utils import clean_text

def get_score_emoji(score):
    if score < 20: return "🟤"
    if score < 40: return "🔴"
    if score < 60: return "🟠"
    if score < 80: return "🟡"
    return "🟢"

def shorten_source_name(feed_source):
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

def generate_entry_xml(p, academic_domains, seen_dates):
    score = p.get('score', 0)
    if score < 0: return ""

    emoji = get_score_emoji(score)
    title_raw = clean_text(p.get('title', 'Untitled'))
    category = p.get('category', 'GENERAL')
    feed_source = p.get('feed_source', 'Unknown')
    short_source = shorten_source_name(feed_source)
    
    display_title = f"{emoji} {short_source} ➤ {title_raw}"
    display_title_esc = html.escape(display_title)
    
    summary = html.escape(clean_text(p.get('summary', 'No summary')))
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
    
    return f"""
  <entry>
    <title>{display_title_esc}</title>
    <link href="{link}"/>
    <id>{link}</id>
    <updated>{pub_date}</updated>
    <summary>{summary}</summary>
    <content type="html">{html.escape(content_html)}</content>
  </entry>
"""

def generate_feed(papers, config, filename, title_suffix=""):
    os.makedirs("public", exist_ok=True)
    output_path = os.path.join("public", filename)
    feed_url = f"{config['base_url']}/{filename}"
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    full_title = "Astrobiology AI Digest"
    if title_suffix:
        full_title += f" - {title_suffix}"

    xml_content = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>{full_title}</title>
  <subtitle>Hourly AI-curated papers on Origins of Life</subtitle>
  <link href="{feed_url}" rel="self"/>
  <link href="https://github.com/champagnealexandre/ooldigest"/>
  <updated>{now_iso}</updated>
  <id>{feed_url}</id>
  <author><name>AI Agent</name></author>
"""
    seen_dates = set()
    academic_domains = config['academic_domains']

    for p in papers:
        xml_content += generate_entry_xml(p, academic_domains, seen_dates)

    xml_content += "</feed>"
    with open(output_path, "w", encoding='utf-8') as f: f.write(xml_content)