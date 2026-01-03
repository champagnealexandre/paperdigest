# OOL Digest

AI-powered curation of **Origins of Life** and **Astrobiology** papers.

## How It Works

1. **Fetch** — Monitor 70+ RSS feeds from journals & preprint servers
2. **Filter** — Match papers against OoL/Astrobiology keywords
3. **Hunt** — Scrape source URLs for DOIs and academic links
4. **Analyze** — LLM scores relevance (0-100) via OpenRouter
5. **Publish** — Generate Atom XML feeds

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export OPENROUTER_API_KEY="your_key"
python main.py
```

## Configuration

All config lives in `config/`:

| File | Purpose |
|------|---------|
| `config.yaml` | LLM settings, keywords, scoring prompt |
| `feeds.yaml` | RSS feed sources by category |

### Keyword Syntax

```yaml
# Keyword matching supports three modes:
word       # exact word match (word boundaries)
word*      # prefix match (e.g., eukaryo* → eukaryote, eukaryotic)
word(s)    # optional plural (e.g., origin(s) → origin or origins)
```

### Model Tiers

Set `model_tier` in config.yaml (1-4):

| Tier | Model |
|------|-------|
| 1 | `google/gemini-2.5-flash-lite` |
| 2 | `openai/gpt-4o-mini` |
| 3 | `google/gemini-2.5-pro` |
| 4 | `openai/gpt-5.2` |

## Project Structure

```
main.py              # Pipeline orchestrator
config/
  config.yaml        # LLM & keyword settings
  feeds.yaml         # RSS sources
lib/
  models.py          # Config + Paper data models
  ai.py              # OpenRouter LLM client
  hunter.py          # DOI/link scraper
  feed.py            # Atom feed generator
  utils.py           # History & logging
data/
  papers.json        # All papers (keyword_rejected + ai_scored, 100k max)
  decisions.md       # Decision log with status (100k max)
  last_feeds-status.md  # Feed health from last run
  logs/              # Timestamped run logs
public/
  ooldigest-ai.xml   # Output feed (AI-scored papers only)
```

## Outputs

| File | Description |
|------|-------------|
| `public/ooldigest-ai.xml` | Atom feed of AI-scored papers |
| `data/papers.json` | All papers history (100,000 max) |
| `data/decisions.md` | Decision log with status (100,000 max) |
| `data/last_feeds-status.md` | Feed health report |
| `data/logs/` | Timestamped run logs |

### Paper Stages

Papers in `papers.json` have a `stage` field:

| Stage | Description |
|-------|-------------|
| `keyword_rejected` | Didn't match any keywords |
| `ai_scored` | Matched keywords, scored by AI |

## License

GNU Affero General Public License v3.0 (AGPL-3.0). See `LICENSE`.
