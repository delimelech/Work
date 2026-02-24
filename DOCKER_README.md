# QA Scanner - Docker Deployment Guide

## Overview

The QA Scanner is now fully dockerized with a conversational interface that accepts natural language queries for running stability and infrastructure scans.

## Quick Start

### 1. Build the Docker Image

```bash
docker build -t qa-scanner:latest .
```

### 2. Configure Volume Mounts

Edit `docker-compose.yml` and update the volume paths to point to your network drives:

```yaml
volumes:
  # Replace these paths with your actual network drives
  - /path/to/allure_reports:/data/allure_reports:ro
  - /path/to/console_logs:/data/console_logs:ro
  - ./output:/output
```

**Windows Example:**
```yaml
volumes:
  - Z:/allure_reports:/data/allure_reports:ro
  - Z:/console_logs:/data/console_logs:ro
  - ./output:/output
```

**Linux/Mac Example:**
```yaml
volumes:
  - /mnt/network/allure_reports:/data/allure_reports:ro
  - /mnt/network/console_logs:/data/console_logs:ro
  - ./output:/output
```

### 3. Run Scans

**Using docker-compose:**

```bash
# Stability scan for a specific folder
docker-compose run --rm scanner "Scan stability for Data-Flow-Pipeline for 30 days"

# Infrastructure scan for a specific folder
docker-compose run --rm scanner "Run infra scan for Data-Flow-Pipeline for 7 days"

# Team-based scan
docker-compose run --rm scanner "Scan stability for servicedesk team for 14 days"

# All folders (be patient - this takes a while!)
docker-compose run --rm scanner "Stability scan all for 30 days"
```

**Using docker run:**

```bash
docker run --rm \
  -v /path/to/allure_reports:/data/allure_reports:ro \
  -v /path/to/console_logs:/data/console_logs:ro \
  -v ./output:/output \
  qa-scanner:latest "Scan stability for Data-Flow-Pipeline for 30 days"
```

## Natural Language Query Examples

The agent understands natural language queries. Here are examples:

### Stability Scans (Allure Reports)

```bash
"Scan stability for Data-Flow-Pipeline for 30 days"
"Run stability scan for my-job for 14 days"
"Stability scan for servicedesk team"
"Scan all stability for 30 days"
```

### Infrastructure Scans (Console Logs)

```bash
"Run infra scan for Data-Flow-Pipeline for 7 days"
"Infrastructure scan for servicedesk team for 14 days"
"Infra scan all for 30 days"
"Scan console logs for my-job"
```

## Query Parsing

The agent extracts the following from your query:

1. **Scan Type:** `stability` or `infra`
   - Keywords: stability, stable, allure, test → Stability scan
   - Keywords: infra, infrastructure, console, log → Infrastructure scan

2. **Target:** `folder`, `team`, or `all`
   - `team <name>` → Scans all jobs for that team
   - `folder <name>` or `job <name>` → Scans specific folder
   - `all` → Scans everything

3. **Time Period:** Number of days
   - Extracted from phrases like "30 days", "last 14 days", "past 7 days"
   - **Defaults:**
     - Stability: 30 days
     - Infrastructure: 7 days

## Output

### HTML Reports

Reports are saved to the `./output` directory (mapped volume):

```
output/
├── stability_Data-Flow-Pipeline.html
├── infra_Data-Flow-Pipeline.html
├── stability_servicedesk_team_20260224_143022.html
└── ...
```

### Historical Data

The scanner maintains historical snapshots for anomaly detection:

```
.history/
├── stability_Data-Flow-Pipeline_8b57c2f04973.json
├── infra_Data-Flow-Pipeline_1077d09211a6.json
└── ...
```

### Cache

Scan cache (24-hour TTL for stability) is stored in:

```
.cache/
└── scan_8b57c2f0_1771855213.json
```

## Advanced Usage

### Custom Paths

You can override default paths when running:

```bash
docker run --rm \
  -v /custom/allure:/data/allure_reports:ro \
  -v /custom/console:/data/console_logs:ro \
  -v ./output:/output \
  qa-scanner:latest \
  --allure-base /data/allure_reports \
  --console-base /data/console_logs \
  --output-dir /output \
  "Scan stability for my-job for 30 days"
```

### Direct Scanner Access

You can also run the scanners directly (bypassing the agent):

```bash
# Stability scan
docker run --rm \
  -v /path/to/allure_reports:/data/allure_reports:ro \
  -v ./output:/output \
  --entrypoint python \
  qa-scanner:latest \
  scan_stability.py --folder /data/allure_reports/Data-Flow-Pipeline --days 30 --output-dir /output

# Infrastructure scan
docker run --rm \
  -v /path/to/console_logs:/data/console_logs:ro \
  -v ./output:/output \
  --entrypoint python \
  qa-scanner:latest \
  scan_infra.py --folder /data/console_logs/Data-Flow-Pipeline --days 7 --output-dir /output
```

## Automated Scheduling

### Using cron (Linux/Mac)

Add to your crontab:

```bash
# Run stability scan daily at 2 AM
0 2 * * * cd /path/to/scanner && docker-compose run --rm scanner "Scan stability for Data-Flow-Pipeline for 30 days"

# Run infra scan every 6 hours
0 */6 * * * cd /path/to/scanner && docker-compose run --rm scanner "Run infra scan for Data-Flow-Pipeline for 7 days"
```

### Using Windows Task Scheduler

Create a batch file `run_stability_scan.bat`:

```batch
@echo off
cd "C:\path\to\scanner"
docker-compose run --rm scanner "Scan stability for Data-Flow-Pipeline for 30 days"
```

Schedule it in Task Scheduler to run daily.

## Troubleshooting

### Volume Mount Issues

**Symptom:** "Path does not exist" errors

**Solution:** Verify your volume mounts are correct:

```bash
docker run --rm -v /path/to/allure_reports:/data/allure_reports:ro qa-scanner:latest ls -la /data/allure_reports
```

### Permission Issues

**Symptom:** Cannot write to output directory

**Solution:** Ensure the output directory is writable:

```bash
chmod -R 777 ./output
```

### Network Drive Access (Windows)

**Symptom:** Cannot access Z: drive from Docker

**Solution:** Use UNC paths instead:

```yaml
volumes:
  - //server/share/allure_reports:/data/allure_reports:ro
```

Or mount the network drive inside Docker Desktop settings.

## Environment Variables

You can configure the scanner using environment variables:

```yaml
environment:
  - TZ=America/New_York  # Set timezone
  - PYTHONUNBUFFERED=1   # Unbuffered output (already set)
```

## Health Check

To verify the scanner is working:

```bash
docker run --rm qa-scanner:latest --help
```

Expected output:
```
usage: agent.py [-h] [--allure-base ALLURE_BASE] [--console-base CONSOLE_BASE]
                [--output-dir OUTPUT_DIR]
                query

Conversational Agent for QA Scanners
...
```

## Updating the Scanner

To update to the latest version:

```bash
# Pull latest code
git pull

# Rebuild image
docker build -t qa-scanner:latest .

# Restart services
docker-compose down
docker-compose up -d
```

## Performance Tips

1. **Use Cache:** The stability scanner caches results for 24 hours. Don't use `--no-cache` unless necessary.

2. **Limit Scope:** Scan specific folders instead of "all" for faster results.

3. **Resource Allocation:** For large scans, allocate more memory to Docker:
   ```bash
   docker run --rm -m 4g -v ... qa-scanner:latest "..."
   ```

4. **Parallel Scanning:** The scanners already use parallel processing (100 threads for stability, 40 for infra).

## Support

For issues, questions, or feature requests:
- GitHub: https://github.com/delimelech/Work
- Bitbucket: https://bitbucket.org/atny/automation_scanner

---

**Generated:** 2026-02-24
**Version:** 2.0 (Docker Edition)
