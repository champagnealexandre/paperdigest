# Paper Digest

AI-powered curation of scientific papers using RSS feeds, keyword filtering, and LLM scoring.

Define your own **Lines of Investigation (LOIs)** — research topics with custom keywords and scoring prompts — and Paper Digest will monitor 90+ RSS feeds, filter relevant papers, score them with an LLM, and generate Atom feeds for your feed reader.

## Features

- 📡 **Multi-source**: Monitors journals, preprint servers, and press releases
- 🔑 **Keyword filtering**: Prefix matching, optional plurals, exact matches
- 🤖 **LLM scoring**: Configurable prompts via OpenRouter (GPT, Gemini, etc.)
- 📊 **Multiple LOIs**: Track different research topics independently
- 📰 **Atom feeds**: Subscribe in any feed reader
- 🔄 **GitHub Actions**: Automated scheduled runs
- 🧹 **Log rotation**: Automatic cleanup of old logs

## One-Line Install

```bash
curl -sL https://raw.githubusercontent.com/champagnealexandre/paperdigest/main/scripts/install.sh | bash
```

This will clone the repo, set up remotes for syncing, and create an example LOI structure.

## Quick Start

Alternatively, set up manually:

### 1. Create Your Instance

```bash
# Clone this repo (creates a "manual fork" that can sync updates)
git clone https://github.com/champagnealexandre/paperdigest.git my-paperdigest
cd my-paperdigest

# Set up upstream for future updates
git remote rename origin upstream
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### 2. Create Your First LOI

```bash
# Copy the example template
cp config/loi/_example.yaml config/loi/my-topic.yaml

# Create the data directory
mkdir -p data/my-topic
echo "[]" > data/my-topic/papers.json
echo "| Status | Score | Paper |" > data/my-topic/decisions.md
echo "|--------|-------|-------|" >> data/my-topic/decisions.md
```

Edit `config/loi/my-topic.yaml`:
- Set `name`, `slug`, `base_url`, `output_feed`
- Add your `keywords`
- Customize `model_prompt` and `custom_instructions`

### 3. Run Locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export LLM_API_KEY="your_key"
python main.py
```

### 4. Deploy with GitHub Actions

> **Note:** GitHub Actions is disabled in the template repo. You must enable it in your personal instance.

1. Go to your repo's **Settings → Actions → General**
2. Under "Actions permissions", select **Allow all actions**
3. Add your `LLM_API_KEY` as a repository secret (Settings → Secrets → Actions)
4. Enable GitHub Pages: **Settings → Pages → Source → "GitHub Actions"**
5. Manually trigger the workflow once (Actions → Hourly Scan → Run workflow)
6. The workflow will then run hourly and deploy feeds to GitHub Pages

> ⚠️ **Important:** GitHub disables scheduled workflows after 60 days of repository inactivity. If your scans stop running, manually trigger the workflow or push a commit to restart the schedule.

### Workflow Options

When manually triggering the workflow (Actions → Run workflow), you can set:

- **Skip scan**: Deploy existing feeds without running the scanner (useful for testing Pages)
- **Reset all data**: Delete all `papers.json`, `decisions.md`, logs, and feed status to start fresh

## Configuration

### Directory Structure

```
config/
  config.yaml        # Shared: retention settings
  ai.yaml            # Shared: model settings
  domains.yaml       # Shared: academic domains for link hunting
  feeds.yaml         # Shared: RSS feed sources
  loi/
    _example.yaml    # Template for new LOIs
    my-topic.yaml    # Your LOI configs

data/
  logs/              # Run logs
  my-topic/
    papers.json      # Paper history
    decisions.md     # Decision log

public/
  my-topic.xml       # Output Atom feed
```

Each run also generates `data/last_feeds-status.md` with feed health (healthy, stalled, errors).

### LOI Configuration

Each LOI is defined in `config/loi/{slug}.yaml`:

```yaml
name: My Research Digest           # Display name
slug: my-topic                     # Identifier (used for data folder)
base_url: https://example.com      # Feed base URL
output_feed: my-topic.xml          # Output filename

keywords:
  - exact-match
  - prefix*                        # Matches prefix, prefixed, etc.
  - word(s)                        # Matches word or words

model_prompt: |
  Role: Senior Researcher.
  Task: Score this paper...
  # Full prompt template with {title}, {abstract}, {keywords_str}, etc.

custom_instructions: |
  - Prioritize papers about X
  - Deprioritize papers about Y
```

### Shared Settings

**config.yaml** — Retention:
```yaml
retention:
  feed_hours: 168          # Papers stay in feed for 1 week
  fetch_hours: 168         # Fetch papers from last week
  stale_feed_days: 30      # Mark feed as stalled after 30 days without entries
  history_max_entries: 100000
  log_retention_days: 7    # Auto-delete logs older than 7 days
```

**ai.yaml** — Model:
```yaml
model_tier: 4              # 1-4 (see models list)
model_temperature: 0.1
max_workers: 10
models:
  - google/gemini-2.5-flash-lite  # tier 1
  - openai/gpt-4o-mini            # tier 2
  - google/gemini-2.5-pro         # tier 3
  - openai/gpt-5.2                # tier 4
```

## Syncing Updates from Template

To pull updates from the main Paper Digest repo:

```bash
./scripts/update.sh          # Fetch, merge, and push
./scripts/update.sh --check  # Check for updates without merging
```

Or manually:

```bash
git fetch upstream
git merge upstream/main
# Resolve any conflicts (usually only in your LOI configs)
```

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│  FETCH: 90+ RSS feeds (journals, preprints, press releases)    │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        ┌─────────┐     ┌─────────┐     ┌─────────┐
        │  LOI 1  │     │  LOI 2  │     │  LOI N  │
        ├─────────┤     ├─────────┤     ├─────────┤
        │ Filter  │     │ Filter  │     │ Filter  │
        │ Score   │     │ Score   │     │ Score   │
        │ Output  │     │ Output  │     │ Output  │
        └─────────┘     └─────────┘     └─────────┘
              │               │               │
              ▼               ▼               ▼
          feed1.xml       feed2.xml       feedN.xml
```

1. **Fetch** — Download entries from all RSS feeds
2. **Filter** — Match against each LOI's keywords
3. **Hunt** — Scrape source URLs for DOIs and academic links
4. **Score** — LLM evaluates relevance (0-100)
5. **Output** — Generate Atom feed with scored papers

## Output Format

Feed entries include:
- Score emoji: 🟢 ≥80, 🟡 ≥60, 🟠 ≥40, 🔴 ≥20, 🟤 <20
- Numeric score `[85]`
- Source feed name
- Matched keywords
- AI summary
- Abstract
- Academic links found

## License

GNU Affero General Public License v3.0 (AGPL-3.0). See [LICENSE](LICENSE).
