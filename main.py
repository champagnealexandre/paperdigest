#!/usr/bin/env python3
"""
OOL Digest - AI-powered Origins of Life paper curation.

Pipeline: Fetch RSS → Keyword Filter → Hunt Links → AI Score → Generate Feeds
"""

import os
import yaml
import logging
import datetime
import concurrent.futures
import feedparser
from time import mktime
from typing import List

from lib.models import Config, Paper
from lib import utils, hunter, ai, feed


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

def load_config() -> Config:
    with open("config/config.yaml") as f:
        return Config(**yaml.safe_load(f))


def load_feeds() -> dict:
    """Load feeds grouped by category."""
    with open("config/feeds.yaml") as f:
        data = yaml.safe_load(f)
    return data.get('feed_categories', {})


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1: FETCH & KEYWORD FILTER
# ─────────────────────────────────────────────────────────────────────────────

def matches_keywords(entry: feedparser.FeedParserDict, keywords: List[str]) -> bool:
    """Check if entry matches any keyword.
    
    Supports wildcard syntax: 'eukaryo*' matches eukaryote, eukaryotic, etc.
    Without wildcard: exact word boundary match to avoid false positives.
    """
    text = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()
    if 'tags' in entry:
        text += " " + " ".join(t.term.lower() for t in entry.tags)
    
    import re
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower.endswith('*'):
            # Prefix match: word boundary at start, any continuation allowed
            prefix = kw_lower[:-1]
            pattern = r'\b' + re.escape(prefix)
        else:
            # Exact word match with boundaries on both sides
            pattern = r'\b' + re.escape(kw_lower) + r'\b'
        if re.search(pattern, text):
            return True
    return False


def fetch_feed(feed_cfg: dict, seen: set, keywords: List[str], cutoff: datetime.datetime, category: str) -> dict:
    """Fetch a single RSS feed. Returns status dict with papers and metadata."""
    url, title = feed_cfg['url'], feed_cfg['title']
    result = {
        'title': title,
        'url': url,
        'category': category,
        'papers': [],
        'total': 0,
        'status': 'ok',
        'error': None,
        'latest_date': None
    }
    
    try:
        parsed = feedparser.parse(url)
        
        # Check for HTTP errors
        if hasattr(parsed, 'status'):
            if parsed.status == 404:
                result['status'] = 'error'
                result['error'] = '404 Not Found'
                return result
            elif parsed.status >= 400:
                result['status'] = 'error'
                result['error'] = f'HTTP {parsed.status}'
                return result
        
        # Check if feed has entries
        if not parsed.entries:
            result['status'] = 'empty'
            return result
        
        # Find latest post date across all entries
        latest = None
        for entry in parsed.entries:
            pub = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub = datetime.datetime.fromtimestamp(mktime(entry.published_parsed), datetime.timezone.utc)
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                pub = datetime.datetime.fromtimestamp(mktime(entry.updated_parsed), datetime.timezone.utc)
            
            if pub and (latest is None or pub > latest):
                latest = pub
            
            link = entry.get('link')
            if not link or link in seen:
                continue
            if pub and pub < cutoff:
                continue
            
            result['total'] += 1
            if matches_keywords(entry, keywords):
                # Use RSS date if available, otherwise use current time (rounded to hour)
                if pub:
                    item_date = pub
                else:
                    now = datetime.datetime.now(datetime.timezone.utc)
                    item_date = now.replace(minute=0, second=0, microsecond=0)
                
                result['papers'].append(Paper(
                    title=entry.get('title', 'No Title'),
                    summary=entry.get('summary', ''),
                    url=link,
                    published_date=item_date,
                    source_feed=title,
                ))
        
        result['latest_date'] = latest
        
        # Check if stalled (no posts in 30+ days)
        if latest:
            age = datetime.datetime.now(datetime.timezone.utc) - latest
            if age.days > 30:
                result['status'] = 'stalled'
                
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)[:50]
    
    return result


def write_feed_status(feed_results: List[dict], categories: dict):
    """Write feed health report to data/last_feeds-status.md."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Group results by category
    by_category = {}
    for r in feed_results:
        cat = r['category']
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(r)
    
    lines = [f"# Feed Status Report", f"Generated: {now}\n"]
    
    # Legend
    lines.append("**Legend:** ✅ Healthy | ⚠️ Stalled (30+ days) | ❌ Error | ⬜ Empty (no entries)\n")
    
    # Summary
    errors = [r for r in feed_results if r['status'] == 'error']
    stalled = [r for r in feed_results if r['status'] == 'stalled']
    empty = [r for r in feed_results if r['status'] == 'empty']
    
    lines.append(f"## Summary")
    lines.append(f"- **Total feeds:** {len(feed_results)}")
    lines.append(f"- **Healthy:** {len(feed_results) - len(errors) - len(stalled) - len(empty)}")
    lines.append(f"- **Errors:** {len(errors)}")
    lines.append(f"- **Stalled (30+ days):** {len(stalled)}")
    lines.append(f"- **Empty:** {len(empty)}\n")
    
    # Problem feeds first
    if errors:
        lines.append("## ❌ Errors\n")
        for r in errors:
            lines.append(f"- **{r['title']}**: {r['error']}")
            lines.append(f"  - URL: {r['url']}")
        lines.append("")
    
    if stalled:
        lines.append("## ⚠️ Stalled Feeds (no posts in 30+ days)\n")
        for r in stalled:
            age = (datetime.datetime.now(datetime.timezone.utc) - r['latest_date']).days if r['latest_date'] else '?'
            lines.append(f"- **{r['title']}**: last post {age} days ago")
        lines.append("")
    
    if empty:
        lines.append("## ⬜ Empty Feeds (no entries returned)\n")
        for r in empty:
            lines.append(f"- **{r['title']}**")
            lines.append(f"  - URL: {r['url']}")
        lines.append("")
    
    # By category
    lines.append("## Feeds by Category\n")
    for cat_name in categories.keys():
        if cat_name not in by_category:
            continue
        results = by_category[cat_name]
        ok_count = len([r for r in results if r['status'] == 'ok'])
        lines.append(f"### {cat_name} ({ok_count}/{len(results)} healthy)")
        for r in results:
            icon = {"ok": "✅", "stalled": "⚠️", "error": "❌", "empty": "⬜"}.get(r['status'], "?")
            lines.append(f"- {icon} {r['title']}")
        lines.append("")
    
    with open("data/last_feeds-status.md", "w") as f:
        f.write("\n".join(lines))


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2 & 3: PROCESS PAPER (Hunt + Analyze)
# ─────────────────────────────────────────────────────────────────────────────

def process_paper(paper: Paper, config: Config, client, keywords: List[str]) -> Paper:
    """Hunt links and score with AI."""
    paper.hunted_links = hunter.hunt_paper_links(paper.url, config.academic_domains)
    model = config.models[config.model_tier - 1]
    paper.analysis_result = ai.analyze_paper(
        client, model, config.model_prompt,
        paper.title, paper.summary, paper.hunted_links,
        keywords, config.custom_instructions, config.model_temperature
    )
    return paper


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    # Setup logging: console + timestamped file
    os.makedirs("data/logs", exist_ok=True)
    log_file = f"data/logs/{datetime.datetime.now().strftime('%Y-%m-%d_%H%M')}.txt"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(message)s',
        datefmt='%H:%M:%S',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file)
        ]
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    config = load_config()
    keywords = list(set(config.keywords_astro + config.keywords_ool))
    
    # Load history
    history = utils.load_history(config.history_file)
    seen = {p.get('url') for p in history}
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
    
    # STAGE 1: Fetch feeds concurrently
    feed_categories = load_feeds()
    all_feeds = [(f, cat) for cat, feeds in feed_categories.items() for f in feeds]
    logging.info(f"Fetching {len(all_feeds)} RSS feeds...")
    
    feed_results: List[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        futures = [ex.submit(fetch_feed, f, seen, keywords, cutoff, cat) for f, cat in all_feeds]
        for fut in concurrent.futures.as_completed(futures):
            feed_results.append(fut.result())
    
    # Write feed status report
    write_feed_status(feed_results, feed_categories)
    
    # Aggregate results
    candidates: List[Paper] = []
    total_fetched = 0
    for r in feed_results:
        candidates.extend(r['papers'])
        total_fetched += r['total']
    
    errors_count = len([r for r in feed_results if r['status'] == 'error'])
    logging.info(f"Fetched {total_fetched} papers from {len(all_feeds)} feeds ({errors_count} errors), {len(candidates)} match keywords")
    
    if not candidates:
        logging.info("No new papers. Regenerating feed from history.")
        feed.generate_feed(history, config.model_dump(), "ooldigest-ai.xml")
        return
    
    # STAGE 2 & 3: Process papers (hunt + analyze)
    client = ai.get_client(os.getenv("OPENROUTER_API_KEY"))
    processed: List[Paper] = []
    errors = 0
    logging.info(f"Processing {len(candidates)} papers...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.max_workers) as ex:
        futures = {ex.submit(process_paper, p, config, client, keywords): p for p in candidates}
        for fut in concurrent.futures.as_completed(futures):
            try:
                paper = fut.result()
                utils.log_decision("data/last_decisions.md", paper.title, 
                                   paper.analysis_result.get('score', 0), 
                                   "Accept", paper.url)
                processed.append(paper)
            except Exception:
                errors += 1
    
    # Stats
    scores = [p.analysis_result.get('score', 0) for p in processed]
    avg_score = sum(scores) / len(scores) if scores else 0
    logging.info(f"Processed {len(processed)} papers (avg score: {avg_score:.0f}, errors: {errors})")
    
    # Update history
    new_history = [p.model_dump(mode='json') for p in processed] + history
    utils.save_history(new_history, config.history_file)
    
    # STAGE 4: Generate feeds
    feed.generate_feed(new_history, config.model_dump(), "ooldigest-ai.xml")
    logging.info(f"Done. Feed has {len(new_history)} papers.")


if __name__ == "__main__":
    main()
