"""Data models for the OOL Digest pipeline."""

from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class RetentionConfig(BaseModel):
    """Retention settings for various pipeline stages."""
    feed_hours: int = 24           # How long papers stay in output feed
    fetch_hours: int = 24          # How far back to fetch new papers
    stale_feed_days: int = 30      # Days before a feed is marked as stalled
    history_max_entries: int = 100000  # Max papers to keep in history file


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
    retention: RetentionConfig = Field(default_factory=RetentionConfig)


class Paper(BaseModel):
    """A paper flowing through the pipeline."""
    title: str
    summary: str
    url: str
    published_date: datetime
    source_feed: str = ""
    stage: str = "keyword_rejected"  # "keyword_rejected" | "ai_scored"
    hunted_links: List[str] = Field(default_factory=list)
    matched_keywords: List[str] = Field(default_factory=list)
    analysis_result: Optional[Dict[str, Any]] = None
