import datetime
import html
from .utils import clean_text

def generate_manual_atom(papers, config):
    feed_url = f"{config['base_url']}/{config['feed_file']}"
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    xml_content = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Astrobiology AI Digest</title>
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
    with open(config['feed_file'], "w", encoding='utf-8') as f: f.write(xml_content)