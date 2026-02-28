# Paper Digest

AI-powered curation of scientific papers using RSS feeds, keyword filtering, and LLM scoring.

Define your own **Lines of Investigation (LOIs)** — research topics with custom keywords and scoring prompts — and Paper Digest will monitor 90+ RSS feeds, filter relevant papers, score them with an LLM, and generate Atom feeds for your feed reader.

## One-Line Install

```bash
curl -sL https://raw.githubusercontent.com/champagnealexandre/paperdigest/main/scripts/install.sh | bash
```

This clones the repo, sets up remotes for syncing, and creates an example LOI structure.

## Quick Start

### 1. Create Your Instance (manual alternative)

```bash
git clone https://github.com/champagnealexandre/paperdigest.git my-paperdigest
cd my-paperdigest
git remote rename origin upstream
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### 2. Create Your First LOI

```bash
cp config/loi/_example.yaml config/loi/my-topic.yaml
mkdir -p data/my-topic
echo "[]" > data/my-topic/papers.json
echo -e "| Status | Score | Paper |\n|--------|-------|-------|" > data/my-topic/decisions.md
```

Edit `config/loi/my-topic.yaml` — set `name`, `slug`, `base_url`, `output_feed`, add `keywords`, and customize `model_prompt` and `custom_instructions`.

### 3. Run Locally

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
LLM_API_KEY="your_key" python main.py
```

### 4. Deploy with GitHub Actions

> GitHub Actions is disabled in the template. Enable it in your personal instance.

1. **Settings → Actions → General** → Allow all actions
2. Add `LLM_API_KEY` as a repository secret (Settings → Secrets → Actions)
3. **Settings → Pages → Source** → "GitHub Actions"
4. **Actions → Hourly Scan → Run workflow** to trigger the first run

The workflow runs hourly and deploys feeds to GitHub Pages.

> ⚠️ GitHub disables scheduled workflows after 60 days of inactivity. Manually trigger or push a commit to restart.

## Configuration

### LOI (`config/loi/{slug}.yaml`)

```yaml
name: My Research Digest
slug: my-topic
base_url: https://example.com
output_feed: my-topic.xml

keywords:
  - exact-match
  - prefix*          # prefix, prefixed, etc.
  - word(s)          # word or words

model_prompt: |
  Role: Senior Researcher.
  Task: Score this paper...

custom_instructions: |
  - Prioritize papers about X
```

### Shared Settings

**`config.yaml`** — retention thresholds:

```yaml
retention:
  feed_hours: 168          # Papers stay in feed (1 week)
  fetch_hours: 168         # Fetch window (1 week)
  stale_feed_days: 30      # Days before a feed is flagged as stalled
  error_alert_days: 7      # Days of errors before ❌ action-required
  log_retention_days: 7
```

Per-feed stale override in `feeds.yaml`: add `stale_days: 365` to any feed entry.

**`ai.yaml`** — model selection:

```yaml
model_tier: 4              # 1-4 (tier 1 = cheapest, tier 4 = best)
model_temperature: 0.1
max_workers: 4
```

### Feed Health

Feed status is tracked in `data/feed_state.json` across runs. Logs use severity tiers: **❌** for persistent issues needing attention, **⚠️** for transient problems that usually self-resolve, and silent for healthy feeds.

## Scripts

```bash
./scripts/update.sh              # Sync updates from template
./scripts/update.sh --check      # Check without merging
./scripts/trigger-scan.sh        # Trigger scan via GitHub CLI
./scripts/trigger-scan.sh --watch
```

## License

GNU Affero General Public License v3.0 (AGPL-3.0). See [LICENSE](LICENSE).
