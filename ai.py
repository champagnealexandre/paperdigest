import json
from openai import OpenAI

MODEL_MAP = {
    1: "google/gemini-flash-1.5",
    2: "openai/gpt-4o-mini",
    3: "google/gemini-pro-1.5",
    4: "openai/gpt-4o"
}

def get_client(api_key):
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "https://alexandrechampagne.io", 
            "X-Title": "OOL Digest Agent",
        }
    )

def analyze_paper(client, model_name, title, abstract, found_links, all_keywords, custom_instructions):
    if found_links is None: found_links = []
    
    keywords_str = ", ".join(all_keywords)
    links_str = ", ".join(found_links) if found_links else "None found."

    prompt = f"""
    Role: Senior Astrobiologist.
    Task: Score this paper for an 'Origins of Life' digest.
    
    Paper: "{title}"
    Abstract: "{abstract}"
    
    EVIDENCE FROM LINK HUNTER:
    The following academic links were found on the source page:
    {links_str}
    
    Target Keywords:
    {keywords_str}
    
    CUSTOM INSTRUCTIONS:
    {custom_instructions}
    
    SCORING RUBRIC (Total /100):
    
    1. BASE RELEVANCE (Max 50 pts):
       - +0: Unrelated field.
       - +25: Broad context.
       - +50: Core OoL focus.
       * BONUS: If "Link Hunter" found a DOI/Nature/Science/Elsevier link, ensure score is robust.
       
    2. KEYWORD BONUS (Max 50 pts):
       - +10 points per keyword match. Caps at 50.
    
    CALCULATION: Sum (Base Relevance + Keyword Bonus).
    Output JSON ONLY: {{"score": int, "summary": "1 sentence summary"}}
    """
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"LLM Error ({model_name}): {e}")
        return {"score": 0, "summary": "Error"}