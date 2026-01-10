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
    """Load config from multiple YAML files."""
    config_data = {}
    
    for filename in ["config.yaml", "ai.yaml", "keywords.yaml", "domains.yaml"]:
        with open(f"config/{filename}") as f:
            config_data.update(yaml.safe_load(f))
    
    return Config(**config_data)


def load_feeds() -> dict:
    """Load feeds grouped by category."""
    with open("config/feeds.yaml") as f:
        data = yaml.safe_load(f)
    return data.get('feed_categories', {})


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1: FETCH & KEYWORD FILTER
# ─────────────────────────────────────────────────────────────────────────────

def find_matching_keywords(entry: feedparser.FeedParserDict, keywords: List[str]) -> List[str]:
    """Return list of keywords that match entry.
    
    Syntax:
      - 'eukaryo*' → prefix match (eukaryote, eukaryotic, etc.)
      - 'origin(s)' → optional plural (origin or origins)
      - 'RNA' → exact word boundary match
    """
    text = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()
    if 'tags' in entry:
        text += " " + " ".join(t.term.lower() for t in entry.tags)
    
    import re
    matched = []
    for kw in keywords:
        kw_lower = kw.lower()
        
        # Handle (s) optional plural syntax: "origin(s)" -> "origins?"
        kw_processed = re.sub(r'\(s\)', 's?', kw_lower)
        
        if kw_processed.endswith('*'):
            # Prefix match: word boundary at start, any continuation allowed
            prefix = kw_processed[:-1]
            pattern = r'\b' + re.escape(prefix)
        else:
            # Exact word match with boundaries on both sides
            # We need to handle the s? specially since re.escape would escape it
            if 's?' in kw_processed:
                # Build pattern preserving the s? regex
                parts = kw_processed.split('s?')
                escaped_parts = [re.escape(p) for p in parts]
                inner = 's?'.join(escaped_parts)
                pattern = r'\b' + inner + r'\b'
            else:
                pattern = r'\b' + re.escape(kw_processed) + r'\b'
        
        if re.search(pattern, text):
            matched.append(kw)
    return matched


def fetch_feed(feed_cfg: dict, seen: set, keywords: List[str], cutoff: datetime.datetime, category: str, stale_days: int = 30) -> dict:
    """Fetch a single RSS feed. Returns status dict with papers and metadata."""
    url, title = feed_cfg['url'], feed_cfg['title']
    result = {
        'title': title,
        'url': url,
        'category': category,
        'papers': [],           # keyword-matched papers
        'rejected': [],         # keyword-rejected papers (for history)
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
            
            # Use RSS date if available, otherwise use current time (rounded to hour)
            if pub:
                item_date = pub
            else:
                now = datetime.datetime.now(datetime.timezone.utc)
                item_date = now.replace(minute=0, second=0, microsecond=0)
            
            matched_kws = find_matching_keywords(entry, keywords)
            
            paper = Paper(
                title=entry.get('title', 'No Title'),
                summary=entry.get('summary', ''),
                url=link,
                published_date=item_date,
                source_feed=title,
                matched_keywords=matched_kws,
            )
            
            if matched_kws:
                paper.stage = "keyword_matched"
                result['papers'].append(paper)
            else:
                paper.stage = "keyword_rejected"
                result['rejected'].append(paper)
        
        result['latest_date'] = latest
        
        # Check if stalled (no posts in stale_days+ days)
        if latest:
            age = datetime.datetime.now(datetime.timezone.utc) - latest
            if age.days > stale_days:
                result['status'] = 'stalled'
                
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)[:50]
    
    return result


def write_feed_status(feed_results: List[dict], categories: dict, stale_days: int = 30):
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
    lines.append(f"**Legend:** ✅ Healthy | ⚠️ Stalled ({stale_days}+ days) | ❌ Error | ⬜ Empty (no entries)\n")
    
    # Summary
    errors = [r for r in feed_results if r['status'] == 'error']
    stalled = [r for r in feed_results if r['status'] == 'stalled']
    empty = [r for r in feed_results if r['status'] == 'empty']
    
    lines.append(f"## Summary")
    lines.append(f"- **Total feeds:** {len(feed_results)}")
    lines.append(f"- **Healthy:** {len(feed_results) - len(errors) - len(stalled) - len(empty)}")
    lines.append(f"- **Errors:** {len(errors)}")
    lines.append(f"- **Stalled ({stale_days}+ days):** {len(stalled)}")
    lines.append(f"- **Empty:** {len(empty)}\n")
    
    # Problem feeds first
    if errors:
        lines.append("## ❌ Errors\n")
        for r in errors:
            lines.append(f"- **{r['title']}**: {r['error']}")
            lines.append(f"  - URL: {r['url']}")
        lines.append("")
    
    if stalled:
        lines.append(f"## ⚠️ Stalled Feeds (no posts in {stale_days}+ days)\n")
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
    # Skip hunting if paper URL is already from an academic domain
    if any(domain in paper.url for domain in config.academic_domains):
        paper.hunted_links = [paper.url]
    else:
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
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=config.retention.fetch_hours)
    
    # STAGE 1: Fetch feeds concurrently
    feed_categories = load_feeds()
    all_feeds = [(f, cat) for cat, feeds in feed_categories.items() for f in feeds]
    logging.info(f"Fetching {len(all_feeds)} RSS feeds...")
    
    feed_results: List[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        futures = [ex.submit(fetch_feed, f, seen, keywords, cutoff, cat, config.retention.stale_feed_days) for f, cat in all_feeds]
        for fut in concurrent.futures.as_completed(futures):
            feed_results.append(fut.result())
    
    # Write feed status report
    write_feed_status(feed_results, feed_categories, config.retention.stale_feed_days)
    
    # Aggregate results
    candidates: List[Paper] = []
    rejected: List[Paper] = []
    total_fetched = 0
    for r in feed_results:
        candidates.extend(r['papers'])
        rejected.extend(r['rejected'])
        total_fetched += r['total']
    
    errors_count = len([r for r in feed_results if r['status'] == 'error'])
    logging.info(f"Fetched {total_fetched} papers from {len(all_feeds)} feeds ({errors_count} errors), {len(candidates)} match keywords, {len(rejected)} rejected")
    
    # Convert rejected papers to dict for history
    rejected_dicts = [p.model_dump(mode='json') for p in rejected]
    
    # Log keyword-rejected papers
    for p in rejected:
        utils.log_decision("data/decisions.md", p.title, "keyword_rejected", "-", p.url)
    
    if not candidates:
        logging.info("No new keyword matches. Saving rejected papers and regenerating feed.")
        new_history = rejected_dicts + history
        utils.save_history(new_history, config.history_file, config.retention.history_max_entries)
        ai_scored = [p for p in history if p.get('stage') == 'ai_scored']
        feed.generate_feed(ai_scored, config.model_dump(), "ooldigest-ai.xml")
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
                score = paper.analysis_result.get('score', 0)
                utils.log_decision("data/decisions.md", paper.title, "ai_scored", score, paper.url)
                processed.append(paper)
            except Exception:
                errors += 1
    
    # Mark processed papers as ai_scored
    for p in processed:
        p.stage = "ai_scored"
    
    # Stats
    scores = [p.analysis_result.get('score', 0) for p in processed]
    avg_score = sum(scores) / len(scores) if scores else 0
    logging.info(f"Processed {len(processed)} papers (avg score: {avg_score:.0f}, errors: {errors})")
    
    # Update history: AI-scored first, then rejected, then old history
    processed_dicts = [p.model_dump(mode='json') for p in processed]
    new_history = processed_dicts + rejected_dicts + history
    utils.save_history(new_history, config.history_file, config.retention.history_max_entries)
    
    # STAGE 4: Generate feeds (only ai_scored papers)
    ai_scored = [p for p in new_history if p.get('stage') == 'ai_scored']
    feed.generate_feed(ai_scored, config.model_dump(), "ooldigest-ai.xml")
    logging.info(f"Done. History has {len(new_history)} papers ({len(ai_scored)} AI-scored).")


if __name__ == "__main__":
    main()
