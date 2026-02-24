# QA Scanning Tools - Refactored Documentation

🐳 **NEW: Docker Support Available!** See [DOCKER_README.md](DOCKER_README.md) for containerized deployment with conversational interface.

This document describes the refactored QA scanning codebase, which has been simplified for better maintainability and clarity.

## Overview

The QA scanning tools consist of two main scanners:

1. **Stability Scanner** (`scan_stability.py`) - Analyzes Allure test reports for test failures
2. **Infrastructure Scanner** (`scan_infra.py`) - Scans console logs for infrastructure errors

## Key Changes in Refactoring

### Simplified Structure
- **Removed notification code** - Paused Teams notification feature to reduce complexity
- **Single configuration file** - All team mappings consolidated into `teams.json`
- **Clean command-line interface** - Simple, intuitive parameters
- **Maintained performance** - Kept 100 workers for stability scan, 40 for infra scan
- **Better documentation** - Clear comments and usage instructions

### New Files
- `teams.json` - Single, clean team configuration file
- `scan_stability.py` - Refactored Allure scanner (replaces `scan_allure_failures.py`)
- `scan_infra.py` - Refactored console log scanner (replaces `scan_console_logs.py`)
- Updated batch files for easy execution

## Configuration File: teams.json

Simple, clean configuration format:

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

### Adding a New Team
1. Open `teams.json`
2. Add a new entry under `teams`:
```json
"my_new_team": {
  "name": "My New Team",
  "jobs": [
    "JobName1",
    "JobName2"
  ]
}
```

## Stability Scanner (scan_stability.py)

Scans Allure test reports for failures and generates HTML reports.

### Usage

#### Scan a Specific Folder
```bash
python scan_stability.py --folder "Z:\allure_reports\MyJob"
```

#### Scan All Jobs for a Team
```bash
python scan_stability.py --team servicedesk_team
```

### Options
- `--folder PATH` - Scan a specific folder
- `--team TEAM_ID` - Scan all jobs for a team (from teams.json)
- `--teams-config PATH` - Path to teams.json (default: teams.json)
- `-v, --verbose` - Show detailed per-report failure information
- `-o, --output PATH` - Write JSON report to file
- `--html PATH` - Specify HTML report path (auto-generated if not provided)
- `--no-cache` - Force fresh scan, ignore cached results

### Features
- **Fast parallel processing** - 100 worker threads for network drives
- **Smart caching** - Avoids re-scanning unchanged data (24-hour cache)
- **Skip optimization** - Skips full parsing of reports with no failures
- **Multiple formats** - Reads Allure HTML, JSON, and ZIP archives
- **Team filtering** - Filters results to specific team's jobs

### Batch Files

**scan_stability_folder.bat**
- Edit `FOLDER_PATH` variable at top of file
- Double-click to run

**scan_stability_team.bat**
- Edit `TEAM_ID` variable at top of file
- Double-click to run

## Infrastructure Scanner (scan_infra.py)

Scans console logs for infrastructure failures (Selenium crashes, browser errors, etc.).

### Usage

#### Scan All Logs (Last 7 Days)
```bash
python scan_infra.py --all
```

#### Scan Team's Logs (Last 7 Days)
```bash
python scan_infra.py --team servicedesk_team
```

#### Scan Specific Folder (Last 7 Days)
```bash
python scan_infra.py --folder "Z:\console_logs\MyJob"
```

### Options
- `--all` - Scan all console logs
- `--team TEAM_ID` - Scan team's logs only (from teams.json)
- `--folder PATH` - Scan specific folder
- `--teams-config PATH` - Path to teams.json (default: teams.json)
- `--patterns PATH` - Path to patterns JSON (default: console_log_patterns.json)
- `-o, --output PATH` - Write JSON report to file
- `--html PATH` - Specify HTML report path (auto-generated if not provided)

**Note:** All scans automatically filter to files modified/created in the last 7 days.

### Features
- **Configurable patterns** - Edit `console_log_patterns.json` to add/modify error patterns
- **Parallel processing** - 40 worker threads for fast scanning
- **Time filtering** - Always scans last 7 days only
- **Team filtering** - Scans only team's job folders when using `--team`
- **Severity levels** - Critical, high, medium severity classifications

### Batch Files

**scan_infra_all.bat**
- No configuration needed
- Double-click to run

**scan_infra_team.bat**
- Edit `TEAM_ID` variable at top of file
- Double-click to run

**scan_infra_folder.bat**
- Edit `FOLDER_PATH` variable at top of file
- Double-click to run

## Error Patterns Configuration

Edit `console_log_patterns.json` to customize infrastructure error detection:

```json
{
  "patterns": [
    {
      "name": "Error Name",
      "search_strings": [
        "Error message pattern 1",
        "Error message pattern 2"
      ],
      "severity": "critical",
      "category": "Category/Type",
      "description": "Description of the error"
    }
  ],
  "settings": {
    "case_sensitive": false,
    "max_line_length": 500,
    "context_lines_before": 2,
    "context_lines_after": 2
  }
}
```

### Adding New Error Pattern
1. Open `console_log_patterns.json`
2. Add new pattern object under `patterns` array:
```json
{
  "name": "My Custom Error",
  "search_strings": ["error text to search"],
  "severity": "high",
  "category": "Custom/Category",
  "description": "What this error means"
}
```

## Reports

Both scanners generate HTML reports with:
- Summary metrics (cards at top)
- Failure/issue frequency tables
- Detailed results tables
- Visual bar charts for frequency

### Report Locations
- **Stability reports**: `stability_<name>.html` or `stability_<teamid>_<timestamp>.html`
- **Infrastructure reports**: `infra_<name>.html` or `infra_<teamid>_<timestamp>.html`

## Performance

### Stability Scanner
- **100 worker threads** - Optimized for network drive scanning
- **Smart caching** - 24-hour cache avoids re-scanning
- **Skip-no-failure optimization** - Skips full parse for clean reports
- Typical scan time: 2-5 minutes for 1000+ reports

### Infrastructure Scanner
- **40 worker threads** - Balanced for I/O and CPU
- **7-day time filter** - Reduces files scanned significantly
- **Team filtering** - Scans only relevant job folders
- Typical scan time: 1-3 minutes for 1000+ log files

## Migration Guide

### From Old to New Scripts

**Old Command:**
```bash
python scan_allure_failures.py --folder "Z:\reports\Job" --notify
```

**New Command:**
```bash
python scan_stability.py --folder "Z:\reports\Job"
```

**Old Command:**
```bash
python scan_console_logs.py --team myteam --days 7
```

**New Command:**
```bash
python scan_infra.py --team myteam
```
(Note: 7 days is now the default and only option)

### Configuration Migration

Old files like `teams_mapping.json` and `monitor_config.json` are replaced by the single `teams.json` file. The structure is simpler:

**Old (teams_mapping.json):**
```json
{
  "teams": {
    "myteam": {
      "team_name": "My Team",
      "owned_jobs": ["Job1", "Job2"],
      "notification_emails": ["..."],
      "teams_webhook": "...",
      "alert_thresholds": {...}
    }
  }
}
```

**New (teams.json):**
```json
{
  "teams": {
    "myteam": {
      "name": "My Team",
      "jobs": ["Job1", "Job2"]
    }
  }
}
```

## Common Tasks

### Quick Scan a Single Job
```bash
python scan_stability.py --folder "Z:\allure_reports\MyJob"
```

### Daily Team Scan
```bash
python scan_stability.py --team servicedesk_team
python scan_infra.py --team servicedesk_team
```

### Check for Infrastructure Issues Across All Teams
```bash
python scan_infra.py --all
```

### Force Fresh Scan (Ignore Cache)
```bash
python scan_stability.py --team myteam --no-cache
```

### Get Detailed Failure Information
```bash
python scan_stability.py --folder "Z:\allure_reports\MyJob" -v
```

## Troubleshooting

### "Team not found in teams.json"
- Check that the team ID matches exactly (case-sensitive)
- Verify `teams.json` exists in the current directory
- Ensure `teams.json` has valid JSON syntax

### "Path does not exist"
- Verify the network path is accessible
- Check `base_paths` in `teams.json` for correct paths
- Ensure you have read permissions on the network share

### Slow Scanning
- **Stability scan**: Cache is working? Check `.cache` directory
- **Infra scan**: Too many old files? 7-day filter should help
- Network drive slow? Check network connection speed

### No Results Found
- **Stability**: Ensure Allure reports exist in the folder
- **Infra**: Check that log files have correct extensions (.log, .txt, etc.)
- **Team mode**: Verify job names match folder names (substring matching)

## File Structure

```
Scan_Allure_Reports/
├── teams.json                      # Single team configuration file
├── console_log_patterns.json       # Infrastructure error patterns
├── scan_stability.py               # Refactored stability scanner
├── scan_infra.py                   # Refactored infrastructure scanner
├── scan_stability_folder.bat       # Batch: scan folder (stability)
├── scan_stability_team.bat         # Batch: scan team (stability)
├── scan_infra_all.bat             # Batch: scan all logs (infra)
├── scan_infra_team.bat            # Batch: scan team logs (infra)
├── scan_infra_folder.bat          # Batch: scan folder (infra)
├── .cache/                         # Cached scan results
└── REFACTORED_README.md           # This file
```

## What Was Removed

To simplify the codebase, the following features were removed:

1. **Teams notification integration** - `NotificationService` and `--notify` flag
2. **Multiple config files** - Consolidated into single `teams.json`
3. **Complex alert thresholds** - Simplified team configuration
4. **Email configuration** - Removed notification-related settings
5. **Webhook configuration** - Removed Teams webhook URLs

These features can be re-added later if needed, but for now, the focus is on clean, maintainable scanning functionality.

## Future Enhancements

Potential improvements (not implemented yet):

1. **Re-add notifications** - Clean implementation of Teams/email notifications
2. **Configuration validation** - Validate teams.json structure on load
3. **Progress indicators** - Better visual feedback during scanning
4. **Results comparison** - Compare current vs. previous scan results
5. **Scheduled scanning** - Built-in scheduler for automated scans
6. **Web dashboard** - Web UI for viewing historical scan results

## Support

For questions or issues:
1. Check this README first
2. Review the command help: `python scan_stability.py --help`
3. Check console output for error messages
4. Verify configuration files are valid JSON

---

**Version:** 2.0 (Refactored)
**Last Updated:** 2026-02-22
**Maintainer:** QA Team
