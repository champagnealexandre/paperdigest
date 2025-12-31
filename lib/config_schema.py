from pydantic import BaseModel
from typing import List, Dict

class Config(BaseModel):
    model_prompt: str
    rss_urls: List[str]
    model_tier: int
    model_temperature: float
    models: Dict[str, str]
    base_url: str
    history_file: str
    custom_instructions: str
    keywords_astro: List[str]
    keywords_ool: List[str]
    academic_domains: List[str]