"""Simple utilities for history and logging."""

import os
import json
from typing import List, Dict, Any
from bs4 import BeautifulSoup


def load_history(path: str) -> List[Dict[str, Any]]:
    """Load paper history from JSON file."""
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def save_history(data: List[Dict[str, Any]], path: str) -> None:
    """Save paper history, keeping only last 100,000 entries."""
    with open(path, 'w') as f:
        json.dump(data[:100000], f, indent=2)


def clean_text(text: str) -> str:
    """Strip HTML and normalize whitespace."""
    if not text:
        return ""
    text = BeautifulSoup(text, "html.parser").get_text(separator=' ')
    return " ".join(text.split())


def log_decision(log_file: str, title: str, score: Any, action: str, link: str) -> None:
    """Append a decision to a markdown log file."""
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    if not os.path.exists(log_file):
        with open(log_file, 'w') as f:
            f.write("| Score | Action | Paper |\n")
            f.write("|-------|--------|-------|\n")
    
    with open(log_file, 'a') as f:
        f.write(f"| {score} | {action} | [{title[:60]}]({link}) |\n")
