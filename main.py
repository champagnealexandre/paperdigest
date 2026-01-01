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


def load_feeds() -> List[dict]:
    with open("config/feeds.yaml") as f:
        data = yaml.safe_load(f)
    # Flatten all categories into a single list
    feeds = []
    for category in data.get('feed_categories', {}).values():
        feeds.extend(category)
    return feeds


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1: FETCH & KEYWORD FILTER
# ─────────────────────────────────────────────────────────────────────────────

def matches_keywords(entry: feedparser.FeedParserDict, keywords: List[str]) -> bool:
    """Check if entry matches any keyword."""
    text = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()
    if 'tags' in entry:
        text += " " + " ".join(t.term.lower() for t in entry.tags)
    return any(kw.lower() in text for kw in keywords)


def fetch_feed(feed_cfg: dict, seen: set, keywords: List[str], cutoff: datetime.datetime) -> List[Paper]:
    """Fetch a single RSS feed and return papers matching keywords."""
    url, title = feed_cfg['url'], feed_cfg['title']
    papers = []
    
    try:
        parsed = feedparser.parse(url)
        for entry in parsed.entries:
            link = entry.get('link')
            if not link or link in seen:
                continue
            
            # Parse date
            pub = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub = datetime.datetime.fromtimestamp(mktime(entry.published_parsed), datetime.timezone.utc)
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                pub = datetime.datetime.fromtimestamp(mktime(entry.updated_parsed), datetime.timezone.utc)
            
            if pub and pub < cutoff:
                continue
            
            entry_title = entry.get('title', 'No Title')
            if matches_keywords(entry, keywords):
                papers.append(Paper(
                    title=entry_title,
                    summary=entry.get('summary', ''),
                    url=link,
                    published_date=pub or datetime.datetime.now(datetime.timezone.utc),
                ))
    except Exception as e:
        logging.warning(f"Failed to fetch {title}: {e}")
    
    return papers


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
    # Quiet logs: only show our messages, suppress httpx
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%H:%M:%S')
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    config = load_config()
    client = ai.get_client(os.getenv("OPENROUTER_API_KEY"))
    keywords = list(set(config.keywords_astro + config.keywords_ool))
    
    # Load history
    history = utils.load_history(config.history_file)
    seen = {p.get('url') for p in history}
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
    
    # STAGE 1: Fetch feeds concurrently
    logging.info("Fetching RSS feeds...")
    feeds = load_feeds()
    candidates: List[Paper] = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        futures = [ex.submit(fetch_feed, f, seen, keywords, cutoff) for f in feeds]
        for fut in concurrent.futures.as_completed(futures):
            candidates.extend(fut.result())
    
    logging.info(f"Found {len(candidates)} candidates")
    
    # STAGE 2 & 3: Process papers (hunt + analyze)
    processed: List[Paper] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.max_workers) as ex:
        futures = {ex.submit(process_paper, p, config, client, keywords): p for p in candidates}
        for fut in concurrent.futures.as_completed(futures):
            try:
                paper = fut.result()
                score = paper.analysis_result.get('score', 0)
                action = "✅ Accept" if score >= 0 else "❌ Reject"
                logging.info(f"{action} [{score}]: {paper.title[:50]}")
                utils.log_decision("data/log.md", paper.title, score, action, paper.url)
                processed.append(paper)
            except Exception as e:
                logging.error(f"Error: {e}")
    
    # Update history
    if processed:
        new_history = [p.model_dump(mode='json') for p in processed] + history
        utils.save_history(new_history, config.history_file)
        all_papers = new_history
    else:
        all_papers = history
        logging.info("No new papers found.")
    
    # STAGE 4: Generate feeds
    logging.info("Generating feeds...")
    feed.generate_feed(all_papers, config.model_dump(), "ooldigest-ai.xml")


if __name__ == "__main__":
    main()
