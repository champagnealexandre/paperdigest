#!/usr/bin/env python3
"""Find a paper by title and show its AI score and decision."""

import sys
import json
import os

def find_paper(search_term: str) -> None:
    """Search for a paper by title substring."""
    # Load papers from data directory (script is in scripts/)
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'papers.json')
    
    with open(data_path) as f:
        papers = json.load(f)
    
    search_lower = search_term.lower()
    matches = []
    
    for p in papers:
        if not p:
            continue
        title = p.get('title', '')
        if search_lower in title.lower():
            result = p.get('analysis_result') or {}
            matches.append({
                'title': title,
                'score': result.get('score', 'N/A'),
                'stage': p.get('stage', 'unknown'),
                'summary': result.get('summary', ''),
                'url': p.get('url', ''),
                'published': p.get('published_date', '')
            })
    
    if not matches:
        print(f"No papers found matching: {search_term}")
        return
    
    print(f"Found {len(matches)} paper(s) matching '{search_term}':\n")
    
    for m in matches:
        print(f"## {m['title']}")
        print(f"**Score:** {m['score']} | **Stage:** {m['stage']}")
        if m['published']:
            print(f"**Published:** {m['published'][:10]}")
        if m['summary']:
            print(f"\n**AI Decision:** {m['summary']}")
        if m['url']:
            print(f"\n**URL:** {m['url']}")
        print("\n" + "-" * 60 + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: find_paper.py <title search term>")
        print("Example: find_paper.py 'prebiotic nickel'")
        sys.exit(1)
    
    search_term = " ".join(sys.argv[1:])
    find_paper(search_term)
