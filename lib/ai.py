import json
import logging
from openai import OpenAI
from typing import List, Dict, Any, Union

def get_client(api_key: str) -> OpenAI:
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "https://alexandrechampagne.io", 
            "X-Title": "OOL Digest Agent",
        }
    )

def analyze_paper(client: OpenAI, model_name: str, prompt_template: Union[str, List[str]], title: str, abstract: str, found_links: List[str], all_keywords: List[str], custom_instructions: str, temperature: float = 0.1) -> Dict[str, Any]:
    if found_links is None: found_links = []
    
    keywords_str = ", ".join(all_keywords)
    links_str = ", ".join(found_links) if found_links else "None found."

    # Handle prompt template (list or string)
    if isinstance(prompt_template, list):
        prompt_template = "\n".join(prompt_template)
        
    # Inject variables using replace to avoid issues with JSON braces in the prompt
    prompt = prompt_template.replace("{title}", title).replace("{abstract}", abstract).replace("{links_str}", links_str).replace("{keywords_str}", keywords_str).replace("{custom_instructions}", custom_instructions)
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=temperature
        )
        result = json.loads(response.choices[0].message.content)
        
        # Attach usage stats if available
        if response.usage:
            result['usage'] = {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens
            }
        return result
    except Exception as e:
        logging.error(f"LLM Error ({model_name}): {e}")
        return {"score": 0, "summary": "Error"}