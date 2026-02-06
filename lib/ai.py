import json
import logging
import time
from openai import OpenAI
from typing import List, Dict, Any

MAX_RETRIES = 3
RETRY_BACKOFF = [2, 4, 8]  # seconds between retries

def get_client(api_key: str) -> OpenAI:
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "https://github.com/champagnealexandre/paperdigest", 
            "X-Title": "Paper Digest",
        }
    )

def analyze_paper(client: OpenAI, model: str, prompt_template: str, title: str, abstract: str, 
                  found_links: List[str], keywords: List[str], custom_instructions: str, 
                  temperature: float = 0.1) -> Dict[str, Any]:
    """Score a paper using LLM with retry logic."""
    links_str = ", ".join(found_links) if found_links else "None found."
    keywords_str = ", ".join(keywords)
    
    prompt = (prompt_template
        .replace("{title}", title)
        .replace("{abstract}", abstract)
        .replace("{links_str}", links_str)
        .replace("{keywords_str}", keywords_str)
        .replace("{custom_instructions}", custom_instructions))
    
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=temperature
            )
            content = response.choices[0].message.content
            if not content or not content.strip():
                raise ValueError("LLM returned empty response")
            return json.loads(content)
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF[attempt]
                logging.warning(f"LLM retry {attempt + 1}/{MAX_RETRIES} after {wait}s: {e}")
                time.sleep(wait)
    
    logging.error(f"LLM Error (after {MAX_RETRIES} retries): {last_error}")
    return {"score": 0, "summary": "Error", "error": True}