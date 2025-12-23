# Git Panorama

> Who's shipping? What's shipping? Where's the effort going?

Your git history knows. Let's ask it.

---

## The Problem

You have questions:
- Which repos are actually maintained vs. quietly dying?
- Who are the domain experts on each project?
- Where is engineering time *actually* going?
- Is this person overloaded or coasting?

Your git history has answers. But it's scattered across dozens of repositories, thousands of commits, and multiple email addresses per person.

**Git Panorama** aggregates it all, deduplicates contributors, and surfaces insights through beautiful Grafana dashboards.

---

## Quick Start

```bash
git clone https://github.com/kibotu/git-panorama.git
cd git-panorama
./install.sh  # Once: dependencies + services
cp config.yaml.sample config.yaml
# Edit config.yaml: add your repos and email mappings
./run.sh      # Always: clone/update repos, analyze, upload
```

Open http://localhost:3000 (admin/admin).

**⚠️ SECURITY WARNING**: Change default passwords immediately! See [Security](#security-checklist) section.

Done.

---

## What You Get

### One Comprehensive Dashboard

**Repository Overview** - Everything you need in one place:

- **Key Metrics** - Total commits, lines added/removed, unique contributors
- **Contributor Statistics** - Per-person breakdown with commits, lines changed, and averages
- **Repository Statistics** - Per-repo metrics showing activity and team size
- **Time Series Charts** - Commit activity and code changes over time
- **Contribution Calendar** - GitHub-style heatmap showing daily activity patterns
- **Team Engagement** - Active contributors per period to track team growth

### Interactive Filtering

- **By Repository** - Focus on specific projects or compare multiple repos
- **By Author** - Track individual or team contributions
- **By Date Range** - Analyze any time period from days to years

Click a person → see their repos.  
Click a repo → see its contributors.  
Adjust time range → everything updates.

The power is in the cross-referencing.

---

## Installation

### Prerequisites

Before starting, ensure you have:

| Requirement | Version | Check Command |
|------------|---------|---------------|
| Docker Desktop | Latest | `docker --version && docker compose version` |
| Python | 3.12+ | `python3 --version` |
| uv (Python package manager) | Latest | `uv --version` (installed by install.sh) |
| Git | Any recent | `git --version` |
| SSH Keys | Configured | `ssh -T git@github.com` (for private repos) |

**Verify Prerequisites:**

```bash
# Check Docker is running
docker ps

# Check Python version
python3 --version  # Should be 3.12 or higher

# Check available ports
lsof -i :3000,9200,1358  # Should return nothing
```

### Setup

```bash
git clone https://github.com/kibotu/git-panorama.git
cd git-panorama

# Install dependencies and start services
./install.sh

# Configure your repositories and team
cp config.yaml.sample config.yaml
# Edit config.yaml:
#   1. Add repository URLs under 'repository_urls'
#   2. Map team member emails under 'email_mapping'
#   3. Adjust exclusion patterns if needed

# Run initial analysis
./run.sh
```

Open http://localhost:3000 (default: admin/admin).

**⚠️ IMPORTANT**: Before running in production, see [Security Checklist](#security-checklist).

---

## Configuration

### Email Mapping (Important!)

People use multiple emails. Map them or they appear as separate contributors:

```yaml
email_mapping:
  "Jane Doe":
    - "jane@company.com"
    - "jane.doe@company.com"
    - "jane@personal.com"
```

Find unmapped emails:
```bash
python3 scripts/find_unmapped_emails.py config.yaml
```

### Repository URLs

List repos to auto-clone:

```yaml
repositories:
  repository_urls:
    - "git@github.com:yourorg/repo1.git"
    - "git@github.com:yourorg/repo2.git"
```

Leave `repositories_to_analyze` empty to analyze all cloned repos.

### File Exclusions

Exclude noise:

```yaml
exclusions:
  patterns:
    - pattern: ".*\\.lock$"
      description: "Lock files"
    - pattern: ".*/node_modules/.*"
      description: "Dependencies"
    - pattern: ".*-generated\\..*"
      description: "Generated code"
```

Lock files and generated code aren't real contributions. Exclude them.

### Date Range (Optional)

Focus on recent activity:

```yaml
analysis:
  start_date: "2024-01-01"  # or empty for all time
  end_date: ""               # empty = now
```

---

## Daily Usage

### Update Everything

```bash
./run.sh
```

Idempotent. Run it as often as you want. It will:
1. Clone new repos from config
2. Fetch latest changes
3. Analyze commits
4. Upload to Elasticsearch

No duplicates. No corruption. Just fresh data.

### Automate It

```bash
# Create logs directory first
mkdir -p /absolute/path/to/git-panorama/logs

# Cron: daily at 2 AM (use absolute paths!)
# Edit crontab: crontab -e
0 2 * * * cd /absolute/path/to/git-panorama && ./run.sh >> /absolute/path/to/git-panorama/logs/run.log 2>&1

# Example with log rotation (keep last 7 days)
0 2 * * * cd /absolute/path/to/git-panorama && ./run.sh >> /absolute/path/to/git-panorama/logs/run-$(date +\%Y\%m\%d).log 2>&1 && find /absolute/path/to/git-panorama/logs -name "run-*.log" -mtime +7 -delete

# Verify cron job is registered
crontab -l

# Test the cron command manually first
cd /absolute/path/to/git-panorama && ./run.sh
```

**Important**: Replace `/absolute/path/to/git-panorama` with your actual installation path (e.g., `/Users/yourname/git-panorama`).

### Check Data

```bash
# Document count
curl http://localhost:9200/git-commits/_count
# Expected output: {"count":12345,...}

# View sample documents
curl http://localhost:9200/git-commits/_search?size=5 | jq

# Check index health
curl http://localhost:9200/_cat/indices/git-*?v

# Browse data visually
open http://localhost:1358  # Dejavu - Elasticsearch browser

# Check specific repository
curl "http://localhost:9200/git-commits/_search?q=repository:your-repo-name&size=1" | jq

# Check date range
curl "http://localhost:9200/git-commits/_search" -H 'Content-Type: application/json' -d'
{
  "query": {
    "range": {
      "commit_date": {
        "gte": "2024-01-01",
        "lte": "2024-12-31"
      }
    }
  },
  "size": 0
}' | jq .hits.total.value
```

---

## Architecture

### System Requirements

| Resource | Minimum | Recommended | Notes |
|----------|---------|-------------|-------|
| CPU | 2 cores | 4+ cores | More cores = faster parallel analysis |
| RAM | 4 GB | 8 GB | Elasticsearch needs 2GB, analysis varies by repo size |
| Disk | 5 GB | 20+ GB | ~100MB per 10k commits in Elasticsearch |
| Docker Memory | 4 GB | 6 GB | Configure in Docker Desktop settings |

**Performance Estimates:**

| Repository Size | Commits | Analysis Time | Disk Usage |
|----------------|---------|---------------|------------|
| Small | < 1,000 | < 1 min | ~10 MB |
| Medium | 1,000-10,000 | 1-5 min | ~100 MB |
| Large | 10,000-100,000 | 5-30 min | ~1 GB |
| Very Large | 100,000+ | 30+ min | ~5+ GB |

*Times assume 4 CPU cores with `max_workers: null` (auto-detect)*

### Services

| Service | Port | Purpose | Memory Limit |
|---------|------|---------|--------------|
| Grafana | 3000 | Dashboards | 512 MB |
| Elasticsearch | 9200 | Data storage | 2.5 GB |
| Dejavu | 1358 | Data browser (optional) | Minimal |

**Note**: Dejavu is optional. To disable it, remove the `dejavu` service from `docker-compose.yml`.

### Data Flow

```
Git Repos
    ↓
Python (parallel analysis)
    ↓
Elasticsearch (idempotent upsert)
    ↓
Grafana (real-time queries)
```

### Idempotency

Each commit gets a unique document ID in Elasticsearch: `{repository}_{commit_hash}`

Running `./run.sh` multiple times safely updates existing data instead of creating duplicates. This means you can:
- Run it as often as you want
- Interrupt and restart without corruption
- Update config and re-run to refresh data

**How it works**: Elasticsearch upserts documents by ID. Same commit hash = same document ID = update instead of insert.

### Smart Caching

Analysis results are cached in `./git-stats/` to avoid re-processing unchanged repositories.

**Cache invalidation**: The system detects changes by comparing git refs (branch heads). If a repository's refs haven't changed since last analysis, cached results are reused.

**When to clear cache:**
- After changing exclusion patterns in config.yaml
- After modifying email mappings (to reprocess author names)
- If you suspect cache corruption

```bash
# Clear analysis cache (forces full re-analysis on next run)
./scripts/clear-cache.sh

# Or manually
rm -rf ./git-stats/

# Cache location: ./git-stats/*.json (one file per repo)
```

---

## Troubleshooting

### No Data in Dashboards

```bash
# 1. Verify data exists
curl http://localhost:9200/git-commits/_count
# Expected: {"count":1234,"_shards":{"total":1,"successful":1,"skipped":0,"failed":0}}
# If count is 0, run ./run.sh to analyze and upload data

# 2. Check if data is actually there
curl http://localhost:9200/git-commits/_search?size=1 | jq
# Should show at least one commit document

# 3. Clear Grafana cache
./scripts/clear-grafana-cache.sh

# 4. Hard refresh browser
# Cmd+Shift+R (Mac) / Ctrl+Shift+R (Windows/Linux)
```

### Common Errors

**Error: "Permission denied (publickey)"**
```bash
# Problem: SSH keys not configured for git repositories
# Solution: Add SSH key to your git provider
ssh-keygen -t ed25519 -C "your_email@example.com"
cat ~/.ssh/id_ed25519.pub  # Add this to GitHub/GitLab
ssh -T git@github.com  # Test connection
```

**Error: "Elasticsearch: Connection refused"**
```bash
# Problem: Elasticsearch not running or not ready
# Solution: Check service status
docker compose ps
docker compose logs elasticsearch
# Wait for "Active license is now [BASIC]" in logs
# Or check health: curl http://localhost:9200/_cluster/health
```

**Error: "Python module not found"**
```bash
# Problem: Dependencies not installed
# Solution: Reinstall dependencies
uv pip install -r requirements.txt --system
# Or: pip3 install -r requirements.txt
```

**Error: "fatal: not a git repository"**
```bash
# Problem: Repository path in config doesn't exist or isn't a git repo
# Solution: Check repository paths
ls -la repositories/
# Manually clone missing repos or fix paths in config.yaml
```

**Error: "Elasticsearch: index_not_found_exception"**
```bash
# Problem: Indices not created yet
# Solution: Run setup script or let run.sh create them
./scripts/setup-elasticsearch-indices.sh
# Or just run ./run.sh which auto-creates indices
```

**Error: "Docker: port already allocated"**
```bash
# Problem: Port conflict with existing service
# Solution: See "Port Conflicts" section above
lsof -i :3000,9200,1358  # Find what's using the ports
# Kill the process or change ports via docker-compose.override.yml
```

**Error: "Out of memory" during analysis**
```bash
# Problem: Large repositories consuming too much RAM
# Solution: Reduce parallelization or increase Docker memory
# In config.yaml:
# parallelization:
#   max_workers: 2  # Reduce from default
# Or increase Docker Desktop memory: Settings → Resources → Memory
```

### Services Won't Start

```bash
# Check Docker
docker ps

# View logs
docker compose logs elasticsearch
docker compose logs grafana

# Restart
docker compose restart
```

### Analysis Fails

```bash
# Check Python environment
python3 --version  # Must be 3.12+

# Check dependencies (uv is the recommended package manager)
python3 -c "import yaml; import dateutil; import git"

# Reinstall dependencies using uv (10-100x faster than pip)
uv pip install -r requirements.txt --system

# Alternative: use pip if uv is not available
# pip3 install -r requirements.txt

# Validate config syntax
python3 -c "import yaml; yaml.safe_load(open('config.yaml'))"

# Test git access
python3 scripts/analyze_git_commits.py --help
```

**Note**: The `install.sh` script automatically installs `uv` if not present. All Python scripts run in system Python (no virtual environment required).

### Port Conflicts

If ports 3000, 9200, or 1358 are already in use, override them with environment variables:

```bash
# Check which ports are in use
lsof -i :3000,9200,1358

# Override ports via environment variables (recommended)
export GRAFANA_PORT=3001
export ELASTICSEARCH_PORT=9201
export DEJAVU_PORT=1359

# Update docker-compose.yml to use these variables, or create docker-compose.override.yml:
cat > docker-compose.override.yml <<EOF
services:
  grafana:
    ports:
      - "\${GRAFANA_PORT:-3000}:3000"
  elasticsearch:
    ports:
      - "\${ELASTICSEARCH_PORT:-9200}:9200"
      - "9300:9300"
  dejavu:
    ports:
      - "\${DEJAVU_PORT:-1358}:1358"
EOF

docker compose up -d

# Update config.yaml to match new Elasticsearch port
# elasticsearch:
#   port: 9201
```

**Note**: If you change the Elasticsearch port, update `config.yaml` accordingly.

---

## Advanced

### Multiple Teams

Use separate configs:

```bash
CONFIG_FILE=config-team-a.yaml ./run.sh
CONFIG_FILE=config-team-b.yaml ./run.sh
```

### Custom Dashboards

1. Create in Grafana UI
2. Export as JSON
3. Save to `config/grafana/provisioning/dashboards/`
4. Restart: `docker restart gitstats-grafana`

### Performance Tuning

For large repos:

```yaml
# Limit date range
analysis:
  start_date: "2024-01-01"

# Exclude merge commits
analysis:
  exclude_merge_commits: true

# More parallelism
parallelization:
  max_workers: 8  # increase for more CPU cores
```

### External Elasticsearch

To use an existing Elasticsearch instance instead of the Docker one:

```bash
# Set environment variables
export ES_HOST=elasticsearch.example.com
export ES_PORT=9200
export ES_USER=elastic  # if authentication enabled
export ES_PASSWORD=your-password

# Or update config.yaml directly
# elasticsearch:
#   host: "elasticsearch.example.com"
#   port: 9200

# Run analysis (will skip starting local Elasticsearch)
./run.sh

# Note: You may want to stop the local Elasticsearch container
docker compose stop elasticsearch
```

**Authentication**: If your external Elasticsearch requires authentication, you'll need to modify the Python scripts to include credentials. See `scripts/upload-to-elasticsearch.sh` for connection details.

---

## Production

### Security Checklist

**⚠️ CRITICAL**: The default configuration has security disabled for ease of local development. Before deploying to production or exposing to a network:

- [ ] **Change default Grafana password** (default: admin/admin)
  ```bash
  # Via environment variable
  export GF_ADMIN_PASSWORD="your-secure-password-here"
  docker compose up -d grafana
  
  # Or via Grafana UI: Configuration → Users → admin → Change Password
  ```

- [ ] **Set Elasticsearch password** (currently disabled in docker-compose.yml)
  ```bash
  # Create .env file
  cat > .env <<EOF
  ELASTIC_PASSWORD=your-secure-elasticsearch-password
  GF_ADMIN_PASSWORD=your-secure-grafana-password
  EOF
  
  # Enable security in docker-compose.yml:
  # Change: xpack.security.enabled=false
  # To:     xpack.security.enabled=true
  
  # Update config.yaml with credentials
  ```

- [ ] **Use HTTPS for external access** (nginx reverse proxy or similar)
- [ ] **Restrict network access** (firewall rules, Docker network isolation)
- [ ] **Regular backups** of Docker volumes (see Backup & Restore section)
- [ ] **Monitor disk usage** (Elasticsearch can grow large)
- [ ] **Review file exclusion patterns** (ensure sensitive files are excluded)
- [ ] **Audit email mappings** (no sensitive data in config.yaml if committed)

**Hardcoded Password Warning**: The docker-compose.yml contains a default Elasticsearch password (`QdKgBPQqCyicNr3WNzYnvAXobj8StnvL`). This is only used when security is disabled (current default). If enabling security, use environment variables instead.

### Environment Variables

Create `.env`:

```bash
ELASTIC_PASSWORD=your-secure-password
GF_ADMIN_PASSWORD=your-secure-password
```

### Backup & Restore

**Important**: Elasticsearch data is stored in Docker named volumes, not in `./storage/`.

```bash
# Backup Elasticsearch data (recommended method)
docker compose stop elasticsearch
docker run --rm \
  -v gitstats_elasticsearch-data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/elasticsearch-$(date +%Y%m%d).tar.gz -C /data .
docker compose start elasticsearch

# Backup Grafana dashboards and settings
docker run --rm \
  -v gitstats_grafana-data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/grafana-$(date +%Y%m%d).tar.gz -C /data .

# Restore Elasticsearch
docker compose down
docker volume rm gitstats_elasticsearch-data
docker volume create gitstats_elasticsearch-data
docker run --rm \
  -v gitstats_elasticsearch-data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar xzf /backup/elasticsearch-YYYYMMDD.tar.gz -C /data
docker compose up -d

# Alternative: Export/Import via API (works while running)
# Export all data
curl -X GET "http://localhost:9200/git-commits/_search?scroll=1m&size=1000" > backup.json

# Re-import after fresh install
python3 scripts/upload-to-elasticsearch.sh
```

**Volume Locations:**
- Elasticsearch data: Docker volume `gitstats_elasticsearch-data`
- Grafana data: Docker volume `gitstats_grafana-data`
- Analysis cache: `./git-stats/` (can be safely deleted and regenerated)
- Cloned repos: `./repositories/` (can be re-cloned from config)

---

## Configuration Reference

The `config.yaml` file controls all aspects of analysis. For a complete, commented example, see `config.yaml.sample`.

**Key sections:**

```yaml
# Email mapping (recommended) - consolidate multiple emails per person
email_mapping:
  "Person Name":
    - "email1@company.com"
    - "email2@company.com"

# Repositories
repositories:
  base_directory: "./repositories"
  repositories_to_analyze: []  # empty = analyze all in base_directory
  repository_urls:  # auto-clone these repos
    - "git@github.com:org/repo.git"
  include_all_files:  # repos where exclusions don't apply
    - "build-tools-repo"

# Analysis settings
analysis:
  start_date: ""  # YYYY-MM-DD or empty for all time
  end_date: ""  # empty = now
  all_branches: true
  exclude_merge_commits: true
  output_directory: "./git-stats"

# File exclusions (focus on real code, not generated/lock files)
exclusions:
  patterns:  # always exclude
    - pattern: ".*\\.lock$"
      description: "Lock files"
    - pattern: ".*/node_modules/.*"
      description: "Dependencies"
  always_include:  # exceptions to exclusions
    - pattern: ".*/package\\.json$"
      description: "Package configs"
  repository_specific:  # per-repo overrides
    repo-name:
      include_patterns:
        - pattern: ".*\\.xml$"

# Elasticsearch
elasticsearch:
  host: "localhost"
  port: 9200
  commit_index: "git-commits"
  bulk_batch_size: 1000

# Parallelization
parallelization:
  max_workers: null  # null = auto-detect CPU count, or set to 1-8
```

**Full reference**: See `config.yaml.sample` for all 300+ lines with detailed comments and examples.

---

## Tech Stack

- **Docker Compose** - Container orchestration
- **Elasticsearch 8.17** - Data storage and search
- **Grafana** - Visualization
- **Python 3.12+** - Analysis scripts
- **uv** - Fast Python package manager (10-100x faster than pip)

---

## Philosophy

**Simple by default.** Two commands: `./install.sh` once, `./run.sh` daily.

**Safe to experiment.** Idempotent operations. Run `./run.sh` as often as you want.

**Data-driven decisions.** Base engineering choices on actual activity, not gut feelings.

**Privacy-first.** All data stays on your infrastructure. No external services.

---

## FAQ

**Q: Why not just use GitHub Insights?**  
A: GitHub Insights is per-repo. This is cross-repo, cross-team, with custom email mapping and file exclusions. Plus it works with any git hosting (GitLab, Bitbucket, self-hosted).

**Q: Does this work with GitLab/Bitbucket/Azure DevOps?**  
A: Yes. It analyzes local git repos. Doesn't matter where they're hosted. Just clone them locally.

**Q: Can I analyze private repos?**  
A: Yes. Clone them locally (with proper SSH keys), add to config, run `./run.sh`.

**Q: How long does initial analysis take?**  
A: Depends on repo size. Small repos (< 1k commits): < 1 min. Large repos (100k+ commits): 30+ min. See [System Requirements](#system-requirements) for detailed estimates.

**Q: How much disk space do I need?**  
A: Budget ~100MB per 10k commits in Elasticsearch, plus space for cloned repositories. A typical setup with 10 repos (50k total commits) needs ~5-10GB.

**Q: Can I run this on a server?**  
A: Yes. See [Production](#production) section for security hardening. Works great on a dedicated server with cron automation.

**Q: What about monorepos?**  
A: Works fine. You might want custom file exclusions for generated code. Use `repository_specific` exclusions in config.yaml.

**Q: Can I analyze repos without cloning them?**  
A: No. The tool needs local git history to analyze commits. But cloning is automatic via `./run.sh` if you list repos in `repository_urls`.

**Q: What data is stored in Elasticsearch?**  
A: All data is stored in the `git-commits` index. Each document represents a single commit with metadata including author, timestamp, repository, files changed, and lines added/removed. The dashboard aggregates this data to show trends and statistics.

**Q: Does this track who wrote what lines currently in the codebase?**  
A: No. This tracks commit history (who changed what, when). For current code ownership, use `git blame` or tools like GitHub's code owners.

**Q: Can I exclude certain contributors or time periods?**  
A: Yes. Use `start_date`/`end_date` in config.yaml for time filtering. For contributor filtering, use Grafana dashboard filters or exclude their commits via custom scripting.

---

## Uninstall

To completely remove Git Panorama:

```bash
# Stop and remove containers
docker compose down

# Remove Docker volumes (THIS DELETES ALL DATA)
docker volume rm gitstats_elasticsearch-data gitstats_grafana-data

# Remove cloned repositories (optional)
rm -rf ./repositories

# Remove analysis cache (optional)
rm -rf ./git-stats

# Remove the project directory
cd ..
rm -rf git-panorama
```

**Selective cleanup** (keep some data):

```bash
# Stop services but keep data
docker compose down

# Remove only Elasticsearch data (keep Grafana dashboards)
docker volume rm gitstats_elasticsearch-data

# Remove only analysis cache (will regenerate on next run)
rm -rf ./git-stats
```

---

## Maintenance

### Regular Tasks

```bash
# Daily: update stats (automate via cron)
./run.sh

# Weekly: check for unmapped emails
python3 scripts/find_unmapped_emails.py config.yaml

# Monthly: backup data (see Backup & Restore section for details)
mkdir -p backups
docker compose stop elasticsearch
docker run --rm \
  -v gitstats_elasticsearch-data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/elasticsearch-$(date +%Y%m%d).tar.gz -C /data .
docker compose start elasticsearch

# Quarterly: review and update exclusion patterns
# Check what file types are being analyzed:
curl "http://localhost:9200/git-commits/_search?size=0" -H 'Content-Type: application/json' -d'
{
  "aggs": {
    "file_types": {
      "terms": { "field": "files.keyword", "size": 50 }
    }
  }
}' | jq .aggregations.file_types.buckets
```

### Monitoring

```bash
# Elasticsearch health (should be "green" or "yellow")
curl http://localhost:9200/_cluster/health | jq
# Status meanings:
#   green = all good
#   yellow = working but no replicas (normal for single-node)
#   red = problem, some data unavailable

# Index sizes and document counts
curl http://localhost:9200/_cat/indices/git-*?v
# Shows: health, status, index name, doc count, size

# Docker container health
docker compose ps
# All should show "healthy" or "running"

# Docker resource usage (live monitoring)
docker stats --no-stream

# Check disk space (Elasticsearch can grow large)
df -h
docker system df -v

# View recent logs
docker compose logs --tail=50 elasticsearch
docker compose logs --tail=50 grafana

# Check for errors in logs
docker compose logs elasticsearch | grep -i error
docker compose logs grafana | grep -i error
```

**Set up alerts** (optional):
- Monitor disk usage: `df -h | grep -E '9[0-9]%'` (alert if > 90%)
- Monitor Elasticsearch health: `curl -s http://localhost:9200/_cluster/health | jq -r .status` (alert if "red")
- Monitor container status: `docker compose ps | grep -v "Up"` (alert if any down)

---

## What's Next?

### Getting Started Checklist

1. **Start small** - Analyze 2-3 repos first to verify setup
   ```bash
   # Add just a few repos to config.yaml initially
   ./run.sh
   # Verify data: curl http://localhost:9200/git-commits/_count
   ```

2. **Refine email mappings** - Consolidate contributor identities
   ```bash
   # Find unmapped emails
   python3 scripts/find_unmapped_emails.py config.yaml
   # Add to email_mapping in config.yaml
   # Re-run to update: ./run.sh
   ```

3. **Review exclusions** - Ensure metrics focus on real code
   ```bash
   # Check what's being analyzed
   curl http://localhost:9200/git-commits/_search?size=100 | jq '.hits.hits[]._source.files'
   # Add exclusion patterns for noise (lock files, generated code, etc.)
   ```

4. **Automate updates** - Set up daily cron job
   ```bash
   # See "Automate It" section
   crontab -e
   ```

5. **Explore the dashboard** - Discover insights
   - Who's most active? Use contributor statistics and filters
   - Which repos are maintained vs stale? Check repository statistics
   - What are the commit trends? Review time series charts
   - When do people contribute? Examine the contribution calendar

6. **Share insights** - Use in team meetings
   - Sprint retrospectives: "Where did we spend time?"
   - 1-on-1s: "Here's your impact over the quarter"
   - Planning: "Which repos need attention?"

7. **Customize** - Build dashboards for your specific needs
   - Clone existing dashboards in Grafana
   - Add panels for your metrics
   - Export and save to `config/grafana/provisioning/dashboards/`

### Success Metrics

You'll know it's working when:
- ✅ Email mappings consolidate 80%+ of duplicate identities
- ✅ Dashboards update daily via cron
- ✅ Team references dashboards in meetings
- ✅ You can answer "who's the expert on X?" in 30 seconds
- ✅ Engineering decisions cite actual data, not assumptions

The goal: **understand your engineering org better**. Git Panorama gives you the data. You bring the insights.

---

*Built for engineering teams who value transparency and data-driven decisions.*

*Questions? Issues? PRs welcome.*
