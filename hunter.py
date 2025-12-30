import requests
import re
from bs4 import BeautifulSoup

def hunt_paper_links(url, academic_domains):
    found_links = set()
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        
        # 1. Regex DOI Scan
        doi_pattern = r'10\.\d{4,9}/[-._;()/:A-Z0-9a-z]+'
        dois = re.findall(doi_pattern, response.text)
        for doi in dois:
            clean_doi = doi.rstrip('.,)')
            found_links.add(f"https://doi.org/{clean_doi}")

        # 2. Standard Domain Scan
        soup = BeautifulSoup(response.text, 'html.parser')
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if not href.startswith('http'): continue
            if url in href: continue 
            if any(domain in href for domain in academic_domains):
                found_links.add(href)

    except Exception as e:
        print(f"   [Hunter] Failed to scrape {url}: {e}")
    
    return list(found_links)