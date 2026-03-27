"""Simple utilities for history and logging."""

import os
import json
import re
from typing import List, Dict, Any
from urllib.parse import urlparse, urlunparse
from bs4 import BeautifulSoup

# Regex to match invalid XML 1.0 control characters
# Valid: #x9 (tab), #xA (newline), #xD (carriage return), #x20 and above
# Invalid: 0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F
_INVALID_XML_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def load_history(path: str) -> List[Dict[str, Any]]:
    """Load paper history from JSON file."""
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def save_history(data: List[Dict[str, Any]], path: str, max_entries: int = 50000) -> None:
    """Save paper history, keeping only last max_entries entries."""
    with open(path, 'w') as f:
        json.dump(data[:max_entries], f, indent=2)


def strip_invalid_xml_chars(text: str) -> str:
    """Remove characters that are invalid in XML 1.0."""
    if not text:
        return ""
    return _INVALID_XML_CHARS.sub('', text)


def clean_text(text: str) -> str:
    """Strip HTML, normalize whitespace, and remove invalid XML characters."""
    if not text:
        return ""
    text = BeautifulSoup(text, "html.parser").get_text(separator=' ')
    text = strip_invalid_xml_chars(text)
    return " ".join(text.split())


def log_decision(decisions_path: str, title: str, status: str, score: Any, link: str, max_entries: int = 50000) -> None:
    """Append a decision to a decisions.md file, keeping last max_entries.
    
    Args:
        decisions_path: Path to the decisions.md file (e.g., 'data/ool/decisions.md')
        title: Paper title
        status: Decision status ('keyword_rejected' or 'ai_scored')
        score: AI score or '-' for rejected
        link: Paper URL
        max_entries: Maximum number of entries to keep
    """
    os.makedirs(os.path.dirname(decisions_path), exist_ok=True)
    
    header = "| Status | Score | Paper |\n|--------|-------|-------|\n"
    new_line = f"| {status} | {score if score != '-' else '-'} | [{title[:60]}]({link}) |\n"
    
    # Read existing entries (skip header)
    entries = []
    if os.path.exists(decisions_path):
        with open(decisions_path, 'r') as f:
            lines = f.readlines()
            # Skip header (first 2 lines)
            entries = lines[2:] if len(lines) > 2 else []
    
    # Prepend new entry and limit to max_entries
    entries = [new_line] + entries
    entries = entries[:max_entries]
    
    # Write back with header
    with open(decisions_path, 'w') as f:
        f.write(header)
        f.writelines(entries)


def normalize_url(url: str) -> str:
    """Normalize URL by stripping query parameters.
    
    This ensures the same paper isn't treated as different entries
    when feeds append changing parameters (e.g., PubMed's ff= timestamp,
    utm_* tracking params).
    
    Returns the URL with scheme, netloc, and path only.
    """
    if not url:
        return ""
    parsed = urlparse(url)
    # Keep only scheme, netloc, and path - drop query and fragment
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
