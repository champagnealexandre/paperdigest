import requests
import re
import logging
from bs4 import BeautifulSoup
from typing import List

# Publishers that block scraping - don't warn on 403s
BLOCKING_DOMAINS = {'science.org', 'nature.com', 'cell.com', 'sciencedirect.com', 'wiley.com'}

# URL patterns to skip (navigation, legal, etc)
SKIP_PATTERNS = [
    '/info/', '/about/', '/terms', '/privacy', '/accessibility', '/cookie',
    '/contact', '/help/', '/sitemap', '/siteindex', '/careers', '/advertising',
    '/partnerships', '/media-kit', 'query.fcgi?cmd=search', '/entrez/'
]

def hunt_paper_links(url: str, academic_domains: List[str]) -> List[str]:
    """Scrape a URL for academic links. Silently fails on blocked sites."""
    found_links = set()
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        
        # 1. Regex DOI Scan (prioritized - these are the real paper links)
        dois = re.findall(r'10\.\d{4,9}/[^\s"<>]+', response.text)
        for doi in dois:
            clean_doi = doi.rstrip('.,);\'"')
            # Skip DOIs with metadata suffixes
            if ';' not in clean_doi:
                found_links.add(f"https://doi.org/{clean_doi}")

        # 2. Standard Domain Scan (filter out navigation/legal pages)
        soup = BeautifulSoup(response.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('http') and url not in href:
                # Skip navigation/utility links
                if any(pattern in href.lower() for pattern in SKIP_PATTERNS):
                    continue
                if any(d in href for d in academic_domains):
                    found_links.add(href)

    except requests.HTTPError as e:
        # Only log if not a known-blocking domain
        if not any(d in url for d in BLOCKING_DOMAINS):
            logging.debug(f"[Hunter] {e}")
    except Exception:
        pass  # Timeout, connection errors - silent
    
    return list(found_links)