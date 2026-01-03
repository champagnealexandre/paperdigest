"""Data models for the OOL Digest pipeline."""

from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class Config(BaseModel):
    """Application configuration loaded from config.yaml."""
    model_prompt: str
    model_tier: int
    model_temperature: float
    models: List[str]
    base_url: str
    history_file: str
    custom_instructions: str
    keywords_astro: List[str]
    keywords_ool: List[str]
    academic_domains: List[str]
    max_workers: int = 10


class Paper(BaseModel):
    """A paper flowing through the pipeline."""
    title: str
    summary: str
    url: str
    published_date: datetime
    source_feed: str = ""
    stage: str = "keyword_rejected"  # "keyword_rejected" | "ai_scored"
    hunted_links: List[str] = Field(default_factory=list)
    analysis_result: Optional[Dict[str, Any]] = None
