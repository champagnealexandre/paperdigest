import os
import json
import datetime
from bs4 import BeautifulSoup

def load_history(history_file):
    if os.path.exists(history_file):
        with open(history_file, 'r') as f: return json.load(f)
    return []

def save_history(data, history_file):
    with open(history_file, 'w') as f: json.dump(data[:200], f, indent=2)

def clean_text(text):
    if not text: return ""
    text = BeautifulSoup(text, "html.parser").get_text(separator=' ')
    return " ".join(text.split())

def log_decision(title, score_primary, score_shadow, action, link):
    os.makedirs("logs", exist_ok=True)
    month_str = datetime.datetime.now().strftime("%Y-%m")
    log_file = f"logs/decisions-{month_str}.md"
    timestamp = datetime.datetime.now().strftime("%d %H:%M")
    
    if score_shadow is not None:
        delta = score_primary - score_shadow
        delta_str = f"+{delta}" if delta > 0 else str(delta)
        shadow_val = score_shadow
    else:
        delta_str = "N/A"
        shadow_val = "N/A"
    
    title_display = title.replace(" ", "&nbsp;")
    entry = f"| {timestamp} | {shadow_val} | **{score_primary}** | {delta_str} | {action} | [{title_display}]({link}) |\n"
    
    if not os.path.exists(log_file):
        with open(log_file, 'w') as f:
            f.write(f"# Decision Log: {month_str}\n\n")
            f.write("| Date (UTC) | Shadow | Primary | Diff | Action | Paper |\n")
            f.write("|---|---|---|---|---|---|\n")
            
    with open(log_file, 'a') as f:
        f.write(entry)