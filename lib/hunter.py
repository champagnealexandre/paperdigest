import requests
import re
import time
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

# Realistic browser headers (default for most sites)
BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/131.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
}

# Descriptive bot headers — some sites (e.g. phys.org) block browser-like UAs
# but allow well-identified bots, as indicated by their 403 bot-notice pages.
# Format follows the convention: BotName/version (+contact-url)
BOT_HEADERS = {
    'User-Agent': 'PaperDigest/1.0 (+https://github.com/paperdigest)',
    'Accept': 'text/html,*/*',
}

# Domains that require the descriptive bot UA instead of browser headers.
# These sites block browser-impersonating requests but welcome identified bots.
BOT_UA_DOMAINS = {'phys.org', 'physorg.com', 'sciencex.com', 'medicalxpress.com', 'techxplore.com'}

REQUEST_TIMEOUT = 15  # seconds — press-release CDNs can be slow
MAX_RETRIES = 1       # retry once on transient failures


def _headers_for(url: str) -> dict:
    """Pick headers based on the target domain's bot policy."""
    if any(d in url for d in BOT_UA_DOMAINS):
        return BOT_HEADERS
    return BROWSER_HEADERS


def _fetch_page(url: str) -> requests.Response:
    """Fetch a page with appropriate headers and retry on transient errors."""
    headers = _headers_for(url)
    last_exc = None
    for attempt in range(1 + MAX_RETRIES):
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                time.sleep(2)
        except requests.HTTPError:
            raise  # let caller handle HTTP errors immediately
    raise last_exc  # type: ignore[misc]


def _extract_links(html: str, source_url: str, academic_domains: List[str]) -> set:
    """Extract academic links from HTML via DOI regex + <a> domain scan."""
    found = set()

    # 1. Regex DOI Scan (prioritized - these are the real paper links)
    dois = re.findall(r'10\.\d{4,9}/[^\s"<>]+', html)
    for doi in dois:
        clean_doi = doi.rstrip('.,);\'"')
        # Skip DOIs with metadata suffixes
        if ';' not in clean_doi:
            found.add(f"https://doi.org/{clean_doi}")

    # 2. Standard Domain Scan (filter out navigation/legal pages)
    soup = BeautifulSoup(html, 'html.parser')
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('http') and source_url not in href:
            # Skip navigation/utility links
            if any(pattern in href.lower() for pattern in SKIP_PATTERNS):
                continue
            if any(d in href for d in academic_domains):
                found.add(href)

    return found


def hunt_paper_links(url: str, academic_domains: List[str]) -> List[str]:
    """Scrape a URL for academic links. Retries once on transient failures."""
    try:
        response = _fetch_page(url)
        return list(_extract_links(response.text, url, academic_domains))

    except requests.HTTPError as e:
        # Only log if not a known-blocking domain
        if not any(d in url for d in BLOCKING_DOMAINS):
            logging.warning(f"[Hunter] HTTP error for {url}: {e}")
    except Exception as e:
        logging.warning(f"[Hunter] Failed to fetch {url}: {e}")

    return []