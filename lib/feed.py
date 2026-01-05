"""Atom feed generation."""

import os
import html
import datetime
from typing import List, Dict, Any
from .utils import clean_text

FEED_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>OOL Digest</title>
  <subtitle>AI-curated Origins of Life papers</subtitle>
  <link href="{feed_url}" rel="self"/>
  <updated>{now}</updated>
  <id>{feed_url}</id>
{entries}
</feed>"""

ENTRY_TEMPLATE = """  <entry>
    <title>{title}</title>
    <link href="{link}"/>
    <id>{link}</id>
    <updated>{date}</updated>
    <summary>{summary}</summary>
    <content type="html"><![CDATA[{content}]]></content>
  </entry>"""


def _emoji(score: int) -> str:
    if score < 40: return "🔴"
    if score < 60: return "🟠"
    if score < 80: return "🟡"
    return "🟢"


def _build_entry(paper: Dict[str, Any]) -> str:
    """Build XML for a single feed entry."""
    result = paper.get('analysis_result') or {}
    score = result.get('score', 0)
    ai_summary = result.get('summary', '')
    if score < 0:
        return ""
    
    title = clean_text(paper.get('title', 'Untitled'))
    source_feed = paper.get('source_feed', '')
    link = paper.get('url', '')
    abstract = clean_text(paper.get('summary', ''))
    date = paper.get('published_date', datetime.datetime.now(datetime.timezone.utc).isoformat())
    
    # Title format: emoji [score] source ▶ title
    if source_feed:
        display_title = f"{_emoji(score)} [{score}] {source_feed} ▶ {html.escape(title)}"
    else:
        display_title = f"{_emoji(score)} [{score}] {html.escape(title)}"
    
    # Build HTML content
    content_parts = []
    
    # Matched Keywords
    matched_kws = paper.get('matched_keywords', [])
    if matched_kws:
        content_parts.append(f"<p><strong>Keywords matched:</strong> {html.escape(', '.join(matched_kws))}</p>")
    
    # AI Decision
    if ai_summary:
        content_parts.append(f"<p><strong>AI Decision:</strong> {html.escape(ai_summary)}</p>")
    
    # Abstract - check if it's real content or just metadata
    if abstract:
        # Some feeds only provide metadata like "Publication date: ... Source: ... Author(s): ..."
        is_metadata_only = (
            abstract.startswith('Publication date:') or 
            'Source:' in abstract[:100] and 'Author(s):' in abstract
        )
        if is_metadata_only:
            content_parts.append(f"<p><em>Abstract not available in RSS feed.</em></p>")
            content_parts.append(f"<p><strong>Metadata:</strong> {html.escape(abstract)}</p>")
        else:
            content_parts.append(f"<p><strong>Abstract:</strong> {html.escape(abstract)}</p>")
    
    # Hunted links
    links = paper.get('hunted_links', [])
    if links:
        content_parts.append("<p><strong>Links found:</strong></p><ul>")
        for u in links[:10]:
            content_parts.append(f'<li><a href="{html.escape(u)}">{html.escape(u)}</a></li>')
        content_parts.append("</ul>")
    else:
        content_parts.append("<p><strong>Links found:</strong> <em>No links found</em></p>")
    
    # Source link
    content_parts.append(f'<p><a href="{html.escape(link)}">Read source article</a></p>')
    
    content = "\n".join(content_parts)
    
    return ENTRY_TEMPLATE.format(
        title=display_title,
        link=html.escape(link),
        date=date,
        summary=html.escape(abstract[:200]) if abstract else "",
        content=content
    )


def generate_feed(papers: List[Dict[str, Any]], config: Dict[str, Any], filename: str) -> None:
    """Generate an Atom feed XML file."""
    os.makedirs("public", exist_ok=True)
    
    entries = "\n".join(e for e in (_build_entry(p) for p in papers) if e)
    
    feed_xml = FEED_TEMPLATE.format(
        feed_url=f"{config['base_url']}/{filename}",
        now=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        entries=entries
    )
    
    with open(f"public/{filename}", "w") as f:
        f.write(feed_xml)
