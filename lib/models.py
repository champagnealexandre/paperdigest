"""Data models for the Paper Digest pipeline."""

from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class RetentionConfig(BaseModel):
    """Retention settings for various pipeline stages."""
    feed_hours: int = 24           # How long papers stay in output feed
    fetch_hours: int = 24          # How far back to fetch new papers
    stale_feed_days: int = 30      # Days before a feed is marked as stalled
    history_max_entries: int = 100000  # Max papers to keep in history file
    log_retention_days: int = 7    # Days to keep log files


class LOIConfig(BaseModel):
    """Configuration for a Line of Investigation."""
    name: str                      # Display name (e.g., "OOL Digest")
    slug: str                      # Short identifier (e.g., "ool")
    base_url: str                  # Base URL for feed links
    output_feed: str               # Output feed filename (e.g., "ooldigest-ai.xml")
    keywords: List[str]            # Keywords for filtering
    model_prompt: str              # LLM prompt template
    custom_instructions: str       # Custom instructions for LLM
    
    @property
    def history_path(self) -> str:
        """Path to history file: data/{slug}/papers.json"""
        return f"data/{self.slug}/papers.json"
    
    @property
    def decisions_path(self) -> str:
        """Path to decisions file: data/{slug}/decisions.md"""
        return f"data/{self.slug}/decisions.md"


class Config(BaseModel):
    """Application configuration loaded from config files."""
    # Shared settings
    model_tier: int
    model_temperature: float
    models: List[str]
    academic_domains: List[str]
    max_workers: int = 10
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    
    # Lines of Investigation
    lois: List[LOIConfig] = Field(default_factory=list)


class Paper(BaseModel):
    """A paper flowing through the pipeline."""
    title: str
    summary: str
    url: str
    published_date: datetime
    source_feed: str = ""
    stage: str = "keyword_rejected"  # "keyword_rejected" | "ai_scored" | "ai_error" | "ai_failed"
    retry_count: int = 0
    hunted_links: List[str] = Field(default_factory=list)
    matched_keywords: List[str] = Field(default_factory=list)
    analysis_result: Optional[Dict[str, Any]] = None
