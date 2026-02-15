#!/usr/bin/env python3
"""
Paper Digest - AI-powered scientific paper curation.

Pipeline: Fetch RSS → For each LOI: Keyword Filter → Hunt Links → AI Score → Generate Feed

Lines of Investigation (LOIs) are defined in config/loi/*.yaml
Each LOI has its own keywords, LLM prompt, history, and output feed.
"""

import os
import sys
import glob
import yaml
import logging
import datetime
import concurrent.futures
import feedparser
from time import mktime
from typing import List, Dict, Any

MAX_CROSS_RUN_RETRIES = 3  # After this many failed runs, paper becomes ai_failed

from lib.models import Config, LOIConfig, Paper
from lib import utils, hunter, ai, feed


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

def load_config() -> Config:
    """Load config from shared files and LOI-specific files."""
    config_data = {}
    
    # Load shared config files
    for filename in ["config.yaml", "ai.yaml", "domains.yaml"]:
        filepath = f"config/{filename}"
        if os.path.exists(filepath):
            with open(filepath) as f:
                data = yaml.safe_load(f)
                if data:
                    config_data.update(data)
    
    # Load LOI configs from config/loi/*.yaml
    loi_configs = []
    for loi_file in sorted(glob.glob("config/loi/*.yaml")):
        # Skip files starting with _ (templates/examples)
        if os.path.basename(loi_file).startswith('_'):
            continue
        with open(loi_file) as f:
            loi_data = yaml.safe_load(f)
            if loi_data:
                loi_configs.append(LOIConfig(**loi_data))
    
    config_data['lois'] = loi_configs
    return Config(**config_data)


def load_feeds() -> dict:
    """Load feeds grouped by category."""
    with open("config/feeds.yaml") as f:
        data = yaml.safe_load(f)
    return data.get('feed_categories', {})


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1: FETCH RSS FEEDS
# ─────────────────────────────────────────────────────────────────────────────

def fetch_feed(feed_cfg: dict, cutoff: datetime.datetime, category: str, stale_days: int = 30) -> dict:
    """Fetch a single RSS feed. Returns status dict with raw entries and metadata."""
    url, title = feed_cfg['url'], feed_cfg['title']
    feed_stale_days = feed_cfg.get('stale_days', stale_days)
    result = {
        'title': title,
        'url': url,
        'category': category,
        'entries': [],          # raw feedparser entries
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
        
        # Find latest post date and collect entries
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
            if not link:
                continue
            if pub and pub < cutoff:
                continue
            
            result['total'] += 1
            result['entries'].append({
                'entry': entry,
                'published': pub,
                'link': link,
                'feed_title': title
            })
        
        result['latest_date'] = latest
        
        # Check if stalled
        if latest:
            age = datetime.datetime.now(datetime.timezone.utc) - latest
            if age.days > feed_stale_days:
                result['status'] = 'stalled'
                
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)[:50]
    
    return result


def log_feed_status(feed_results: List[dict], stale_days: int = 30):
    """Log feed health summary to the run log."""
    errors = [r for r in feed_results if r['status'] == 'error']
    stalled = [r for r in feed_results if r['status'] == 'stalled']
    empty = [r for r in feed_results if r['status'] == 'empty']
    healthy = len(feed_results) - len(errors) - len(stalled) - len(empty)

    logging.info(f"Feed status: {len(feed_results)} total, {healthy} ok, {len(errors)} errors, {len(stalled)} stalled, {len(empty)} empty")

    for r in errors:
        logging.warning(f"  ERROR: {r['title']} ({r['url']}) — {r['error']}")

    for r in stalled:
        age = (datetime.datetime.now(datetime.timezone.utc) - r['latest_date']).days if r['latest_date'] else '?'
        logging.warning(f"  STALLED: {r['title']} — last post {age}d ago")

    for r in empty:
        logging.warning(f"  EMPTY: {r['title']} ({r['url']})")


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2: KEYWORD FILTERING (per LOI)
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
            if 's?' in kw_processed:
                parts = kw_processed.split('s?')
                escaped_parts = [re.escape(p) for p in parts]
                inner = 's?'.join(escaped_parts)
                pattern = r'\b' + inner + r'\b'
            else:
                pattern = r'\b' + re.escape(kw_processed) + r'\b'
        
        if re.search(pattern, text):
            matched.append(kw)
    return matched


def filter_entries_for_loi(raw_entries: List[dict], loi: LOIConfig, seen_urls: set) -> tuple:
    """Filter raw entries against LOI keywords.
    
    Returns (candidates, rejected) where:
      - candidates: Papers that matched keywords (for AI scoring)
      - rejected: Papers that didn't match (for history only)
    """
    candidates = []
    rejected = []
    
    for item in raw_entries:
        entry = item['entry']
        link = item['link']
        pub = item['published']
        feed_title = item['feed_title']
        
        # Skip if already seen for this LOI (normalize URL to ignore query params)
        if utils.normalize_url(link) in seen_urls:
            continue
        
        # Use RSS date if available, otherwise use current time (rounded to hour)
        if pub:
            item_date = pub
        else:
            now = datetime.datetime.now(datetime.timezone.utc)
            item_date = now.replace(minute=0, second=0, microsecond=0)
        
        matched_kws = find_matching_keywords(entry, loi.keywords)
        
        paper = Paper(
            title=entry.get('title', 'No Title'),
            summary=entry.get('summary', ''),
            url=link,
            published_date=item_date,
            source_feed=feed_title,
            matched_keywords=matched_kws,
        )
        
        if matched_kws:
            paper.stage = "keyword_matched"
            candidates.append(paper)
        else:
            paper.stage = "keyword_rejected"
            rejected.append(paper)
    
    return candidates, rejected


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 3: HUNT LINKS & AI SCORE (per LOI)
# ─────────────────────────────────────────────────────────────────────────────

def process_paper(paper: Paper, config: Config, loi: LOIConfig, client) -> Paper:
    """Hunt links and score with AI for a specific LOI."""
    # Skip hunting if paper URL is already from an academic domain
    if any(domain in paper.url for domain in config.academic_domains):
        paper.hunted_links = [paper.url]
    else:
        paper.hunted_links = hunter.hunt_paper_links(paper.url, config.academic_domains)
    
    model = config.models[config.model_tier - 1]
    paper.analysis_result = ai.analyze_paper(
        client, model, loi.model_prompt,
        paper.title, paper.summary, paper.hunted_links,
        loi.keywords, loi.custom_instructions, config.model_temperature
    )
    return paper


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def process_loi(loi: LOIConfig, raw_entries: List[dict], config: Config, client) -> int:
    """Process all entries for a single LOI.
    
    Returns the number of papers newly promoted to ai_failed this run.
    """
    logging.info(f"[{loi.slug}] Processing LOI: {loi.name}")
    
    # Ensure data directory exists
    os.makedirs(f"data/{loi.slug}", exist_ok=True)
    
    # Load history for this LOI
    history = utils.load_history(loi.history_path)
    
    # Promote ai_error papers that have exhausted cross-run retries to ai_failed
    newly_failed = []
    for p in history:
        if p.get('stage') == 'ai_error' and p.get('retry_count', 0) >= MAX_CROSS_RUN_RETRIES:
            p['stage'] = 'ai_failed'
            newly_failed.append(p)
    
    if newly_failed:
        logging.warning(f"[{loi.slug}] {len(newly_failed)} paper(s) permanently failed after {MAX_CROSS_RUN_RETRIES} retries")
        for p in newly_failed:
            utils.log_decision(loi.decisions_path, p.get('title', '?'), "ai_failed", "-", p.get('url', ''))
    
    # Build seen_urls: exclude ai_error papers so they can be retried
    seen_urls = {
        utils.normalize_url(p.get('url', ''))
        for p in history
        if p.get('stage') != 'ai_error'
    }
    
    # Collect retryable ai_error papers from history as candidates
    retry_candidates: List[Paper] = []
    for p in history:
        if p.get('stage') == 'ai_error' and p.get('retry_count', 0) < MAX_CROSS_RUN_RETRIES:
            paper = Paper(**{k: v for k, v in p.items() if k in Paper.model_fields})
            paper.retry_count = p.get('retry_count', 0) + 1
            paper.stage = 'keyword_matched'  # reset for re-processing
            paper.analysis_result = None
            retry_candidates.append(paper)
    
    if retry_candidates:
        logging.info(f"[{loi.slug}] Retrying {len(retry_candidates)} previously errored paper(s)")
    
    # Remove retryable ai_error entries from history (they'll be re-added after processing)
    history = [p for p in history if not (p.get('stage') == 'ai_error' and p.get('retry_count', 0) < MAX_CROSS_RUN_RETRIES)]
    
    # Filter entries against this LOI's keywords
    candidates, rejected = filter_entries_for_loi(raw_entries, loi, seen_urls)
    
    # Add retry candidates
    candidates.extend(retry_candidates)
    
    logging.info(f"[{loi.slug}] {len(candidates)} match keywords, {len(rejected)} rejected")
    
    # Convert rejected papers to dict for history
    rejected_dicts = [p.model_dump(mode='json') for p in rejected]
    
    # Log keyword-rejected papers
    for p in rejected:
        utils.log_decision(loi.decisions_path, p.title, "keyword_rejected", "-", p.url)
    
    if not candidates:
        logging.info(f"[{loi.slug}] No new keyword matches. Saving rejected papers and regenerating feed.")
        new_history = rejected_dicts + history
        utils.save_history(new_history, loi.history_path, config.retention.history_max_entries)
        ai_scored = [p for p in history if p.get('stage') == 'ai_scored']
        feed.generate_feed(ai_scored, config.model_dump(), loi.output_feed, 
                          loi_name=loi.name, loi_base_url=loi.base_url)
        return len(newly_failed)
    
    # Process papers (hunt + analyze)
    processed: List[Paper] = []
    errors = 0
    logging.info(f"[{loi.slug}] Processing {len(candidates)} papers...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.max_workers) as ex:
        futures = {ex.submit(process_paper, p, config, loi, client): p for p in candidates}
        for fut in concurrent.futures.as_completed(futures):
            try:
                paper = fut.result()
                processed.append(paper)
            except Exception as e:
                errors += 1
                failed_paper = futures[fut]
                logging.warning(f"[{loi.slug}] Error processing '{failed_paper.title[:50]}': {e}")
    
    # Separate successful scores from AI errors
    ai_errors = 0
    for p in processed:
        if p.analysis_result and p.analysis_result.get('error'):
            p.stage = 'ai_error'
            ai_errors += 1
            utils.log_decision(loi.decisions_path, p.title, "ai_error", "-", p.url)
        else:
            p.stage = 'ai_scored'
            score = p.analysis_result.get('score', 0) if p.analysis_result else 0
            utils.log_decision(loi.decisions_path, p.title, "ai_scored", score, p.url)
    
    # Stats
    scored_papers = [p for p in processed if p.stage == 'ai_scored']
    scores = [p.analysis_result.get('score', 0) for p in scored_papers]
    avg_score = sum(scores) / len(scores) if scores else 0
    error_total = errors + ai_errors
    logging.info(f"[{loi.slug}] Processed {len(processed)} papers (avg score: {avg_score:.0f}, errors: {error_total})")
    
    # Update history: processed first, then rejected, then old history
    processed_dicts = [p.model_dump(mode='json') for p in processed]
    new_history = processed_dicts + rejected_dicts + history
    utils.save_history(new_history, loi.history_path, config.retention.history_max_entries)
    
    # Generate feed (only ai_scored papers)
    ai_scored = [p for p in new_history if p.get('stage') == 'ai_scored']
    feed.generate_feed(ai_scored, config.model_dump(), loi.output_feed,
                      loi_name=loi.name, loi_base_url=loi.base_url)
    logging.info(f"[{loi.slug}] Done. History has {len(new_history)} papers ({len(ai_scored)} AI-scored).")
    
    return len(newly_failed)


def cleanup_old_logs(retention_days: int = 7):
    """Delete log files older than retention_days.
    
    Parses dates from filenames (YYYY-MM-DD_HHMM.txt) instead of using
    filesystem mtime, which is unreliable on GitHub Actions (checkout
    resets all mtimes to the current time).
    """
    log_dir = "data/logs"
    if not os.path.exists(log_dir):
        return
    
    cutoff = datetime.datetime.now() - datetime.timedelta(days=retention_days)
    deleted = 0
    for filename in os.listdir(log_dir):
        if not filename.endswith('.txt'):
            continue
        filepath = os.path.join(log_dir, filename)
        try:
            date_str = filename.replace('.txt', '')
            file_date = datetime.datetime.strptime(date_str, '%Y-%m-%d_%H%M')
            if file_date < cutoff:
                os.remove(filepath)
                deleted += 1
        except (OSError, ValueError):
            pass
    return deleted


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
    
    # Cleanup old log files
    log_retention = getattr(config.retention, 'log_retention_days', 7)
    deleted_logs = cleanup_old_logs(log_retention)
    if deleted_logs:
        logging.info(f"Cleaned up {deleted_logs} old log file(s)")
    
    if not config.lois:
        logging.error("No LOI configs found in config/loi/. Exiting.")
        return
    
    logging.info(f"Loaded {len(config.lois)} LOIs: {', '.join(loi.name for loi in config.lois)}")
    
    # STAGE 1: Fetch all feeds once (shared across all LOIs)
    feed_categories = load_feeds()
    all_feeds = [(f, cat) for cat, feeds in feed_categories.items() for f in feeds]
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=config.retention.fetch_hours)
    
    logging.info(f"Fetching {len(all_feeds)} RSS feeds...")
    
    feed_results: List[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        futures = [ex.submit(fetch_feed, f, cutoff, cat, config.retention.stale_feed_days) for f, cat in all_feeds]
        for fut in concurrent.futures.as_completed(futures):
            feed_results.append(fut.result())
    
    # Log feed status
    log_feed_status(feed_results, config.retention.stale_feed_days)
    
    # Aggregate all raw entries
    raw_entries: List[dict] = []
    total_fetched = 0
    for r in feed_results:
        raw_entries.extend(r['entries'])
        total_fetched += r['total']
    
    errors_count = len([r for r in feed_results if r['status'] == 'error'])
    logging.info(f"Fetched {total_fetched} papers from {len(all_feeds)} feeds ({errors_count} errors)")
    
    # Initialize AI client (shared across all LOIs)
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        logging.error("LLM_API_KEY environment variable not set. Exiting.")
        return
    client = ai.get_client(api_key)
    
    # Process each LOI
    total_failed = 0
    for loi in config.lois:
        total_failed += process_loi(loi, raw_entries, config, client)
    
    logging.info("All LOIs processed.")
    
    # Alert on permanent failures (triggers GitHub Actions email notification)
    if total_failed > 0:
        logging.error(f"{total_failed} paper(s) permanently failed AI scoring after {MAX_CROSS_RUN_RETRIES} retries.")
        print(f"::warning::{total_failed} paper(s) permanently failed AI scoring. Check logs for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
