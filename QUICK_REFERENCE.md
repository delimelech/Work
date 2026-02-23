# QA Scanning Tools - Quick Reference Card

## Stability Scanner (scan_stability.py)

### Purpose
Scan Allure test reports for failures and generate HTML reports.

### Quick Commands

```bash
# Scan a specific folder
python scan_stability.py --folder "Z:\allure_reports\MyJob"

# Scan all jobs for a team
python scan_stability.py --team servicedesk_team

# Scan with verbose output
python scan_stability.py --team myteam -v

# Force fresh scan (ignore cache)
python scan_stability.py --folder "Z:\allure_reports\Job" --no-cache

# Save JSON output
python scan_stability.py --team myteam -o results.json
```

### Batch Files

```batch
# Edit and run
scan_stability_folder.bat   # Scan specific folder
scan_stability_team.bat     # Scan team's jobs
```

### Output
- HTML report: `stability_<name>.html` or `stability_<team>_<timestamp>.html`
- Console summary with failure counts and top failures

---

## Infrastructure Scanner (scan_infra.py)

### Purpose
Scan console logs for infrastructure errors (Selenium crashes, browser issues, etc.).

### Quick Commands

```bash
# Scan all logs (last 7 days)
python scan_infra.py --all

# Scan team's logs (last 7 days)
python scan_infra.py --team servicedesk_team

# Scan specific folder (last 7 days)
python scan_infra.py --folder "Z:\console_logs\MyJob"

# Save JSON output
python scan_infra.py --team myteam -o results.json
```

### Batch Files

```batch
# Edit and run
scan_infra_all.bat      # Scan all logs
scan_infra_team.bat     # Scan team's logs
scan_infra_folder.bat   # Scan specific folder
```

### Output
- HTML report: `infra_<name>.html` or `infra_<team>_<timestamp>.html`
- Console summary with issue counts and affected files

---

## Configuration

### teams.json Structure

```json
{
  "base_paths": {
    "allure_reports": "Z:\\allure_reports",
    "console_logs": "Z:\\console_logs"
  },
  "teams": {
    "team_id": {
      "name": "Team Name",
      "jobs": ["Job1", "Job2", "Job3"]
    }
  }
}
```

### Add a New Team

1. Open `teams.json`
2. Add entry under `teams`:
```json
"my_team": {
  "name": "My Team",
  "jobs": ["MyJob1", "MyJob2"]
}
```
3. Save file
4. Test: `python scan_stability.py --team my_team`

### Add New Error Pattern (Infrastructure)

1. Open `console_log_patterns.json`
2. Add pattern under `patterns`:
```json
{
  "name": "My Error Pattern",
  "search_strings": ["error text", "another pattern"],
  "severity": "high",
  "category": "Custom/Category",
  "description": "What this error means"
}
```
3. Save file
4. Test: `python scan_infra.py --folder "Z:\console_logs\TestJob"`

---

## Common Options

### Stability Scanner

| Option | Description | Example |
|--------|-------------|---------|
| `--folder PATH` | Scan specific folder | `--folder "Z:\reports\Job"` |
| `--team TEAM_ID` | Scan team's jobs | `--team servicedesk_team` |
| `-v` | Verbose output | `-v` |
| `--no-cache` | Force fresh scan | `--no-cache` |
| `-o PATH` | Save JSON | `-o results.json` |
| `--html PATH` | Custom HTML path | `--html report.html` |

### Infrastructure Scanner

| Option | Description | Example |
|--------|-------------|---------|
| `--all` | Scan all logs | `--all` |
| `--team TEAM_ID` | Scan team's logs | `--team myteam` |
| `--folder PATH` | Scan specific folder | `--folder "Z:\logs\Job"` |
| `-o PATH` | Save JSON | `-o results.json` |
| `--html PATH` | Custom HTML path | `--html report.html` |

---

## Troubleshooting

### Quick Fixes

| Problem | Solution |
|---------|----------|
| Team not found | Check team ID in `teams.json` (case-sensitive) |
| Path not found | Verify network drive mounted and path correct |
| No results | Check folder contains report files (.html, .json) |
| Slow scan | First scan is slow, subsequent scans use cache |
| Old files scanned | Infra scan always filters to last 7 days |

### Verification

```bash
# Check setup
python verify_setup.py

# Check command help
python scan_stability.py --help
python scan_infra.py --help
```

---

## File Locations

### Scripts
- `scan_stability.py` - Stability scanner
- `scan_infra.py` - Infrastructure scanner
- `verify_setup.py` - Setup verification

### Configuration
- `teams.json` - Team mappings
- `console_log_patterns.json` - Error patterns

### Batch Files
- `scan_stability_folder.bat`
- `scan_stability_team.bat`
- `scan_infra_all.bat`
- `scan_infra_team.bat`
- `scan_infra_folder.bat`

### Output
- `*.html` - HTML reports
- `.cache/` - Cached scan results

---

## Common Workflows

### Daily Team Scan
```bash
python scan_stability.py --team myteam
python scan_infra.py --team myteam
```

### Quick Job Check
```bash
python scan_stability.py --folder "Z:\allure_reports\Job123"
```

### Check Infrastructure Issues
```bash
python scan_infra.py --all
```

### Detailed Analysis
```bash
python scan_stability.py --team myteam -v -o report.json
```

---

## Performance Notes

### Stability Scanner
- **Workers:** 100 threads (fixed, optimized for network drives)
- **Cache:** 24 hours (use `--no-cache` to force refresh)
- **Speed:** ~2-5 minutes for 1000+ reports

### Infrastructure Scanner
- **Workers:** 40 threads (fixed, optimized for I/O)
- **Filter:** Last 7 days only (hardcoded)
- **Speed:** ~1-3 minutes for 1000+ log files

---

## HTML Reports

### Stability Report Contains
- Total tests scanned
- Pass/fail counts
- Failure rate
- Failed step frequency table
- Environment information
- Detailed failure list

### Infrastructure Report Contains
- Log files scanned
- Files with issues
- Total issues detected
- Issue type summary
- Top affected files
- Detailed matches (expandable)

---

## Tips

1. **Use batch files** - Easier than typing commands
2. **Cache speeds up stability scans** - Rerun for updates
3. **Infra scan auto-filters** - Always last 7 days
4. **Team mode filters** - Only shows team's jobs
5. **HTML reports are shareable** - Send to team members
6. **JSON output for automation** - Parse with scripts

---

## Getting Help

1. Run verification: `python verify_setup.py`
2. Check help: `python scan_stability.py --help`
3. Read full docs: `REFACTORED_README.md`
4. Migration guide: `MIGRATION_GUIDE.md`

---

**Version:** 2.0
**Last Updated:** 2026-02-22
