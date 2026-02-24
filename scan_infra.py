#!/usr/bin/env python3
"""
Infrastructure Scanner - Console Log Analysis

Scans console log files from test runs to detect infrastructure failures
like Selenium crashes, browser issues, network errors, and resource problems.

Usage:
    python scan_infra.py --all                      # Scan all logs (last 7 days)
    python scan_infra.py --team myteam              # Scan team's logs (last 7 days)
    python scan_infra.py --folder "Z:\\console_logs\\MyJob"  # Scan specific folder (last 7 days)

Features:
    - Configurable error patterns via console_log_patterns.json
    - Parallel processing with 40 workers
    - Automatic 7-day time filter
    - Team-based filtering using teams.json
    - Generates HTML reports with issue analysis
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TEAMS_CONFIG_FILE = Path("teams.json")
PATTERNS_FILE = Path("console_log_patterns.json")
MAX_WORKERS = 40  # Concurrent threads for network I/O
DAYS_FILTER = 7  # Always filter to last 7 days

# Supported log file extensions
LOG_EXTENSIONS = [".log", ".txt", ".out", ".err", ".console"]


# ---------------------------------------------------------------------------
# Pattern Management
# ---------------------------------------------------------------------------
def load_patterns(patterns_file: Path) -> Dict:
    """Load search patterns from JSON configuration file."""
    if patterns_file.exists():
        try:
            with open(patterns_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Could not load patterns file: {e}")
            return get_default_patterns()
    else:
        print(f"Patterns file not found: {patterns_file}")
        print("Creating default patterns file...")
        patterns = get_default_patterns()
        save_patterns(patterns_file, patterns)
        return patterns


def get_default_patterns() -> Dict:
    """Get default infrastructure error patterns."""
    return {
        "patterns": [
            {
                "name": "Selenium Session Error",
                "search_strings": [
                    "Could not start a new session. Response code 500",
                    "Could not start a new session",
                    "Response code 500"
                ],
                "severity": "critical",
                "category": "Selenium/WebDriver",
                "description": "Failed to create new Selenium session"
            },
            {
                "name": "Chrome Instance Crash",
                "search_strings": [
                    "Chrome instance exited",
                    "chrome not reachable",
                    "chrome process is no longer running"
                ],
                "severity": "critical",
                "category": "Browser/Infrastructure",
                "description": "Chrome browser crashed or became unreachable"
            },
            {
                "name": "WebDriver Timeout",
                "search_strings": [
                    "WebDriver timeout",
                    "element not found timeout",
                    "page load timeout"
                ],
                "severity": "high",
                "category": "Selenium/WebDriver",
                "description": "WebDriver operation timed out"
            },
            {
                "name": "Connection Error",
                "search_strings": [
                    "Connection refused",
                    "Connection reset",
                    "Unable to connect",
                    "Network unreachable"
                ],
                "severity": "high",
                "category": "Network/Infrastructure",
                "description": "Network connection failed"
            },
            {
                "name": "Out of Memory",
                "search_strings": [
                    "OutOfMemoryError",
                    "out of memory",
                    "Cannot allocate memory"
                ],
                "severity": "critical",
                "category": "Resource/Infrastructure",
                "description": "System ran out of memory"
            },
            {
                "name": "Port Already in Use",
                "search_strings": [
                    "Address already in use",
                    "port is already allocated",
                    "bind: address already in use"
                ],
                "severity": "high",
                "category": "Resource/Infrastructure",
                "description": "Required port is already in use"
            }
        ],
        "settings": {
            "case_sensitive": False,
            "max_line_length": 500,
            "context_lines_before": 2,
            "context_lines_after": 2
        }
    }


def save_patterns(patterns_file: Path, patterns: Dict) -> None:
    """Save patterns to JSON file."""
    try:
        with open(patterns_file, "w", encoding="utf-8") as f:
            json.dump(patterns, f, indent=2, ensure_ascii=False)
        print(f"Patterns saved to: {patterns_file}")
    except OSError as e:
        print(f"Error saving patterns: {e}")


# ---------------------------------------------------------------------------
# Team Configuration
# ---------------------------------------------------------------------------
def load_teams_config(config_file: Path = TEAMS_CONFIG_FILE) -> dict:
    """Load teams configuration from teams.json."""
    if not config_file.exists():
        print(f"Warning: Teams config not found: {config_file}")
        return None

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error loading teams config: {e}")
        return None


def get_team_info(team_id: str, config: dict) -> dict:
    """Extract team information from config."""
    teams = config.get("teams", {})
    return teams.get(team_id)


# ---------------------------------------------------------------------------
# Log File Scanning
# ---------------------------------------------------------------------------
def scan_log_file(filepath: Path, patterns: List[Dict], settings: Dict) -> Dict[str, Any]:
    """
    Scan a single log file for error patterns.
    Returns dict with file path, matches, and total match count.
    """
    case_sensitive = settings.get("case_sensitive", False)
    max_line_length = settings.get("max_line_length", 500)
    context_before = settings.get("context_lines_before", 2)
    context_after = settings.get("context_lines_after", 2)

    result = {
        "file": str(filepath),
        "matches": [],
        "total_matches": 0
    }

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        # Build compiled regex patterns
        compiled_patterns = []
        for pattern in patterns:
            for search_str in pattern["search_strings"]:
                flags = 0 if case_sensitive else re.IGNORECASE
                try:
                    compiled_patterns.append({
                        "pattern": re.compile(re.escape(search_str), flags),
                        "name": pattern["name"],
                        "severity": pattern["severity"],
                        "category": pattern["category"],
                        "description": pattern["description"],
                        "search_string": search_str
                    })
                except re.error:
                    continue

        # Scan each line
        for line_num, line in enumerate(lines, 1):
            line_stripped = line.rstrip()
            if len(line_stripped) > max_line_length:
                line_stripped = line_stripped[:max_line_length] + "..."

            # Check all patterns
            for cp in compiled_patterns:
                if cp["pattern"].search(line):
                    # Collect context lines
                    context_start = max(0, line_num - context_before - 1)
                    context_end = min(len(lines), line_num + context_after)
                    context = "".join(lines[context_start:context_end])

                    result["matches"].append({
                        "pattern_name": cp["name"],
                        "severity": cp["severity"],
                        "category": cp["category"],
                        "description": cp["description"],
                        "matched_string": cp["search_string"],
                        "line_number": line_num,
                        "line_content": line_stripped,
                        "context": context[:1000]  # Limit context size
                    })
                    result["total_matches"] += 1

    except (OSError, UnicodeDecodeError) as e:
        result["error"] = str(e)

    return result


def worker_scan_log(filepath: Path, patterns: List[Dict], settings: Dict) -> Dict[str, Any]:
    """Thread worker: scan one log file."""
    return scan_log_file(filepath, patterns, settings)


# ---------------------------------------------------------------------------
# Directory Scanning
# ---------------------------------------------------------------------------
def find_log_files(root_path: Path, days: int = DAYS_FILTER, team_jobs: List[str] = None) -> List[Path]:
    """
    Find all log files in directory tree modified/created in the last N days.

    Args:
        root_path: Root directory to scan
        days: Only include files modified/created in last N days
        team_jobs: If specified, only scan these job subdirectories (team filtering)

    Returns:
        List of Path objects for log files
    """
    log_files = []
    skipped_old = 0
    dirs_scanned = 0
    t0 = time.time()

    # Calculate cutoff time (N days ago)
    cutoff_time = time.time() - (days * 24 * 60 * 60)

    print(f"Scanning directory: {root_path}")
    if team_jobs:
        print(f"Team filter: Scanning {len(team_jobs)} job folders")
    print(f"Date filter: Files modified/created in last {days} days")

    for dirpath, _, filenames in os.walk(str(root_path)):
        dirs_scanned += 1
        if dirs_scanned % 500 == 0:
            elapsed = time.time() - t0
            print(f"  ... {dirs_scanned} dirs scanned ({elapsed:.1f}s)", flush=True)

        # Team filtering: check if this directory belongs to team's jobs
        if team_jobs:
            dir_relative = os.path.relpath(dirpath, root_path)
            # Check if this directory is under any of the team's job folders
            is_team_folder = any(job.lower() in dir_relative.lower() for job in team_jobs)

            if not is_team_folder:
                continue

        # Check each file
        for fn in filenames:
            if any(fn.lower().endswith(ext) for ext in LOG_EXTENSIONS):
                filepath = Path(dirpath) / fn
                try:
                    stat = filepath.stat()
                    # Check both modification time and creation time
                    file_time = max(stat.st_mtime, stat.st_ctime)

                    if file_time >= cutoff_time:
                        log_files.append(filepath)
                    else:
                        skipped_old += 1
                except (OSError, AttributeError):
                    skipped_old += 1
                    continue

    elapsed = time.time() - t0
    msg = f"  Found {len(log_files)} recent log files"
    if skipped_old > 0:
        msg += f" (skipped {skipped_old} older files)"
    if team_jobs:
        msg += f" from team's {len(team_jobs)} job folders"
    print(msg)
    print(f"  Scanned {dirs_scanned} directories in {elapsed:.1f}s")

    return log_files


# ---------------------------------------------------------------------------
# Build Report
# ---------------------------------------------------------------------------
def build_report(
    root_path: Path,
    patterns_config: Dict,
    days: int = DAYS_FILTER,
    workers: int = MAX_WORKERS,
    team_jobs: List[str] = None
) -> Dict[str, Any]:
    """
    Scan all log files and build infrastructure issue report.

    Args:
        root_path: Root directory to scan
        patterns_config: Configuration with patterns and settings
        days: Only scan files from last N days
        workers: Number of parallel worker threads
        team_jobs: Optional list of job names for team filtering

    Returns:
        Report dictionary with scan results
    """
    patterns = patterns_config.get("patterns", [])
    settings = patterns_config.get("settings", {})

    # Find log files
    log_files = find_log_files(root_path, days=days, team_jobs=team_jobs)

    if not log_files:
        print("No log files found!")
        return {
            "root": str(root_path),
            "total_files_scanned": 0,
            "files_with_issues": 0,
            "total_issues": 0,
            "files_with_matches": [],
            "issue_summary": {},
            "all_matches": []
        }

    # Scan files in parallel
    results = []
    t0 = time.time()
    print(f"\nScanning {len(log_files)} log files with {workers} threads...")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(worker_scan_log, filepath, patterns, settings)
            for filepath in log_files
        ]

        done_count = 0
        for future in as_completed(futures):
            done_count += 1
            if done_count % 100 == 0:
                elapsed = time.time() - t0
                rate = done_count / elapsed if elapsed > 0 else 0
                eta = (len(log_files) - done_count) / rate if rate > 0 else 0
                print(f"  ... {done_count}/{len(log_files)} done ({elapsed:.0f}s, ~{eta:.0f}s left)", flush=True)

            result = future.result()
            if result["total_matches"] > 0:
                results.append(result)

    elapsed = time.time() - t0
    print(f"  Done: {len(log_files)} files in {elapsed:.1f}s")

    # Build summary
    issue_counts = defaultdict(int)
    all_matches = []

    for result in results:
        for match in result["matches"]:
            issue_counts[match["pattern_name"]] += 1
            all_matches.append({
                "file": result["file"],
                "pattern": match["pattern_name"],
                "severity": match["severity"],
                "category": match["category"],
                "description": match["description"],
                "matched_string": match["matched_string"],
                "line_number": match["line_number"],
                "line_content": match["line_content"]
            })

    return {
        "root": str(root_path),
        "scanned_at": datetime.now().isoformat(),
        "days_filter": days,
        "team_filter": team_jobs,
        "total_files_scanned": len(log_files),
        "files_with_issues": len(results),
        "total_issues": sum(issue_counts.values()),
        "files_with_matches": results,
        "issue_summary": dict(sorted(issue_counts.items(), key=lambda x: -x[1])),
        "all_matches": all_matches
    }


# ---------------------------------------------------------------------------
# Console Output
# ---------------------------------------------------------------------------
def print_report(report: Dict) -> None:
    """Print infrastructure scan report to console."""
    print("\n" + "="*70)
    print("INFRASTRUCTURE SCAN REPORT (Console Logs)")
    print("="*70)
    print(f"Root folder: {report['root']}")

    if report.get('team_filter'):
        print(f"Team filter: {len(report['team_filter'])} job folders")
    else:
        print("Team filter: All subdirectories")

    print(f"Date filter: Last {report.get('days_filter', 7)} days")
    print(f"Total log files scanned: {report['total_files_scanned']}")
    print(f"Files with infrastructure issues: {report['files_with_issues']}")
    print(f"Total issues detected: {report['total_issues']}")
    print()

    if report['total_issues'] > 0:
        print("--- ISSUE SUMMARY ---")
        for pattern_name, count in report['issue_summary'].items():
            print(f"  [{count:4d}x] {pattern_name}")
        print()

        print("--- TOP AFFECTED FILES ---")
        file_counts = defaultdict(int)
        for result in report['files_with_matches']:
            file_counts[result['file']] = result['total_matches']

        for filepath, count in sorted(file_counts.items(), key=lambda x: -x[1])[:20]:
            print(f"  [{count:3d}x] {filepath}")
    else:
        print("No infrastructure issues detected in console logs!")

    print("="*70)


# ---------------------------------------------------------------------------
# HTML Report Generation
# ---------------------------------------------------------------------------
def _esc(text: str) -> str:
    """Escape HTML special characters."""
    if not text:
        return ""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;"))


def generate_html_report(report: Dict, output_path: Path, anomalies: Dict = None) -> None:
    """Generate HTML report for console log scan with optional anomaly detection."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html_parts = []
    html_parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Infrastructure Scan Report - {now}</title>
<style>
  :root {{
    --bg: #f5f7fa; --card: #fff; --accent: #4361ee; --red: #e63946;
    --green: #2a9d8f; --orange: #f77f00; --gray: #6c757d; --border: #dee2e6;
    --text: #212529; --light-text: #495057;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg);
         color: var(--text); padding: 24px; line-height: 1.6; max-width: 1400px; margin: 0 auto; }}
  .header {{ text-align: center; margin-bottom: 12px; }}
  h1 {{ font-size: 2.5rem; margin: 0; color: var(--accent); display: inline-flex;
       align-items: center; gap: 12px; font-weight: 700; }}
  .title-icon {{ width: 42px; height: 42px; }}
  h2 {{ font-size: 1.3rem; margin: 32px 0 16px 0; color: var(--accent);
        border-bottom: 3px solid var(--accent); display: inline-block; padding-bottom: 4px; font-weight: 700; }}
  .subtitle {{ color: var(--gray); font-size: .9rem; margin-bottom: 24px; line-height: 1.5; text-align: center; }}

  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 18px; margin-bottom: 36px; }}
  .card {{ background: var(--card); border-radius: 12px; padding: 24px;
           box-shadow: 0 2px 8px rgba(0,0,0,.1); text-align: center; transition: transform 0.2s; }}
  .card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,.15); }}
  .card .value {{ font-size: 2.5rem; font-weight: 700; line-height: 1; }}
  .card .label {{ font-size: .8rem; color: var(--gray); margin-top: 8px;
                  text-transform: uppercase; letter-spacing: .6px; font-weight: 600; }}
  .card.red .value {{ color: var(--red); }}
  .card.green .value {{ color: var(--green); }}
  .card.blue .value {{ color: var(--accent); }}
  .card.orange .value {{ color: var(--orange); }}

  table {{ width: 100%; border-collapse: collapse; background: var(--card);
           border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,.1);
           margin-bottom: 24px; margin-top: 12px; }}
  th {{ background: var(--accent); color: #fff; text-align: left; padding: 12px 16px;
       font-size: .85rem; text-transform: uppercase; font-weight: 700; letter-spacing: .5px; }}
  td {{ padding: 12px 16px; border-bottom: 1px solid var(--border); font-size: .95rem;
       vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #f8f9ff; }}
  tr.high-impact {{ background: #fff0f0; }}
  tr.high-impact:hover td {{ background: #ffe6e6; }}
  tr.medium-impact {{ background: #fff8e6; }}
  tr.medium-impact:hover td {{ background: #fff3d9; }}

  .badge {{ display: inline-block; padding: 4px 10px; border-radius: 5px;
            font-size: .75rem; font-weight: 700; text-transform: uppercase; letter-spacing: .3px; }}
  .badge.critical {{ background: #fce4e4; color: var(--red); border: 1px solid #ffcccb; }}
  .badge.high {{ background: #fff3cd; color: #856404; border: 1px solid #ffe69c; }}
  .badge.medium {{ background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }}

  .bar {{ height: 24px; border-radius: 5px; background: linear-gradient(90deg, var(--red) 0%, #ff6b6b 100%);
          display: inline-block; vertical-align: middle; box-shadow: 0 2px 4px rgba(230,57,70,.3); }}
  .bar-label {{ margin-left: 10px; font-weight: 700; font-size: .9rem; color: var(--text); }}
  .pct-cell {{ text-align: center; font-size: 1rem; color: var(--red); min-width: 80px; }}
  .pct-cell strong {{ font-weight: 800; }}
  .no-fail {{ color: var(--green); font-weight: 700; font-size: 1.1rem; padding: 20px;
              background: #e8f5f3; border-radius: 8px; text-align: center; }}

  code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-size: .85rem;
         font-family: 'Courier New', monospace; }}

  details {{ margin-top: 16px; }}
  summary {{ cursor: pointer; font-weight: 600; padding: 8px; background: #f8f9fa;
            border-radius: 4px; }}

  .anomaly-alert {{ background: #fff3cd; border-left: 4px solid var(--orange); padding: 16px 20px;
                    border-radius: 8px; margin: 24px 0; box-shadow: 0 2px 6px rgba(0,0,0,.1); }}
  .anomaly-alert h3 {{ color: #856404; font-size: 1.1rem; margin-bottom: 12px; }}
  .anomaly-alert .metric {{ margin: 8px 0; padding: 8px 12px; background: #fff;
                           border-radius: 5px; font-size: .9rem; }}
  .anomaly-alert .increase {{ color: var(--red); font-weight: 700; }}
  .anomaly-alert .decrease {{ color: var(--green); font-weight: 700; }}

  footer {{ margin-top: 50px; text-align: center; color: var(--gray); font-size: .8rem;
           padding: 20px; border-top: 1px solid var(--border); }}
</style>
</head>
<body>

<div class="header">
  <h1>
    <svg class="title-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 15a3 3 0 100-6 3 3 0 000 6z" stroke="currentColor" stroke-width="2"/>
      <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 114 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    Infrastructure Scan Report
  </h1>
</div>
<div class="subtitle">Generated: {now} | Scanned: {_esc(report['root'])} | Date: Last {report.get('days_filter', 7)} days""")

    if report.get('team_filter'):
        html_parts.append(f" | Team: {len(report['team_filter'])} job folders")

    html_parts.append("</div>\n")

    # Metrics cards
    total = report['total_files_scanned']
    with_issues = report['files_with_issues']
    total_issues = report['total_issues']

    html_parts.append(f"""
<div class="cards">
  <div class="card blue">
    <div class="value">{total}</div>
    <div class="label">Log Files Scanned</div>
  </div>
  <div class="card {"red" if with_issues > 0 else "green"}">
    <div class="value">{with_issues}</div>
    <div class="label">Files with Issues</div>
  </div>
  <div class="card {"red" if total_issues > 0 else "green"}">
    <div class="value">{total_issues}</div>
    <div class="label">Total Issues</div>
  </div>
  <div class="card {"red" if len(report['issue_summary']) > 5 else "orange" if len(report['issue_summary']) > 0 else "green"}">
    <div class="value">{len(report['issue_summary'])}</div>
    <div class="label">Issue Types</div>
  </div>
</div>
""")

    # Anomaly detection alert
    if anomalies and anomalies.get("detected"):
        html_parts.append('<div class="anomaly-alert">\n')
        html_parts.append(f'<h3>Anomaly Detected (compared to last {anomalies["baseline_scans"]} scans)</h3>\n')
        for a in anomalies["anomalies"]:
            change_class = a["direction"]
            sign = "+" if a["change_pct"] > 0 else ""
            html_parts.append(f'<div class="metric"><strong>{_esc(a["metric"])}:</strong> '
                            f'{a["current"]:.1f} (baseline: {a["baseline"]:.1f}) '
                            f'<span class="{change_class}">{sign}{a["change_pct"]:.1f}% {a["direction"]}</span></div>\n')
        html_parts.append('</div>\n')

    # Issue Summary
    html_parts.append('<h2>Issue Summary</h2>\n')
    if report['issue_summary']:
        html_parts.append('<table>\n<thead><tr>')
        html_parts.append('<th>#</th><th>Issue Type</th><th>Count</th><th>% of Total</th></tr></thead>\n<tbody>\n')

        max_count = max(report['issue_summary'].values()) if report['issue_summary'] else 1
        total_issues = sum(report['issue_summary'].values())

        for i, (pattern_name, count) in enumerate(report['issue_summary'].items(), 1):
            bar_width = count / max_count * 100  # Bar width relative to max
            pct_of_total = (count / total_issues * 100) if total_issues > 0 else 0  # Percentage of total

            # Color coding based on percentage
            if pct_of_total >= 50:
                row_class = 'class="high-impact"'
            elif pct_of_total >= 20:
                row_class = 'class="medium-impact"'
            else:
                row_class = ''

            html_parts.append(f'<tr {row_class}><td>{i}</td><td><strong>{_esc(pattern_name)}</strong></td>')
            html_parts.append(f'<td><span class="bar" style="width:{bar_width:.0f}%;"></span>')
            html_parts.append(f'<span class="bar-label">{count}x</span></td>')
            html_parts.append(f'<td class="pct-cell"><strong>{pct_of_total:.1f}%</strong></td></tr>\n')

        html_parts.append('</tbody></table>\n')
    else:
        html_parts.append('<p class="no-fail">No issues detected!</p>\n')

    # Failure Patterns with Examples
    if report['all_matches']:
        html_parts.append('<h2>Failure Patterns with Examples</h2>\n')

        # Group by pattern and matched string
        patterns = defaultdict(lambda: {"count": 0, "examples": [], "severity": "", "category": "", "line_samples": []})

        for match in report['all_matches']:
            pattern_name = match["pattern"]
            matched_str = match["matched_string"]
            pattern_key = (pattern_name, matched_str)

            patterns[pattern_key]["count"] += 1
            patterns[pattern_key]["severity"] = match["severity"]
            patterns[pattern_key]["category"] = match["category"]

            # Add example file (limit to 5)
            if len(patterns[pattern_key]["examples"]) < 5:
                filename = match["file"].split("\\")[-1] if "\\" in match["file"] else match["file"].split("/")[-1]
                patterns[pattern_key]["examples"].append(filename)

            # Add line sample (limit to 3)
            if len(patterns[pattern_key]["line_samples"]) < 3:
                patterns[pattern_key]["line_samples"].append(match["line_content"][:120])

        # Sort patterns by count
        sorted_patterns = sorted(patterns.items(), key=lambda x: -x[1]["count"])

        # Display each pattern
        for i, ((pattern_name, matched_str), data) in enumerate(sorted_patterns, 1):
            html_parts.append(f'<div style="background: #f8f9fa; border-left: 4px solid var(--accent); '
                            f'padding: 16px; margin: 16px 0; border-radius: 6px;">\n')
            html_parts.append(f'<h3 style="color: var(--accent); font-size: 1.05rem; margin-bottom: 8px;">'
                            f'Pattern #{i}: {_esc(pattern_name)}</h3>\n')
            html_parts.append(f'<div style="display: grid; grid-template-columns: auto 1fr; gap: 8px 16px; '
                            f'font-size: .9rem; margin-bottom: 12px;">\n')
            html_parts.append(f'<strong>Occurrences:</strong><span>{data["count"]}x</span>\n')
            html_parts.append(f'<strong>Severity:</strong><span><span class="badge {data["severity"]}">'
                            f'{data["severity"].upper()}</span></span>\n')
            html_parts.append(f'<strong>Category:</strong><span>{_esc(data["category"])}</span>\n')
            html_parts.append(f'<strong>Matched String:</strong><span><code>{_esc(matched_str)}</code></span>\n')
            html_parts.append('</div>\n')

            # Example log lines
            if data["line_samples"]:
                html_parts.append(f'<div style="background: #fff; padding: 12px; border-radius: 4px; '
                                f'margin-bottom: 12px; border: 1px solid var(--border);">\n')
                html_parts.append(f'<strong style="font-size: .85rem; color: var(--gray);">Example Log Lines:</strong>\n')
                for line in data["line_samples"]:
                    html_parts.append(f'<pre style="margin: 6px 0; padding: 8px; background: #f4f4f4; '
                                    f'border-radius: 3px; font-size: .8rem; overflow-x: auto;">{_esc(line)}</pre>\n')
                html_parts.append('</div>\n')

            # Example files
            if data["examples"]:
                html_parts.append(f'<details style="margin-top: 8px;"><summary style="cursor: pointer; '
                                f'font-size: .9rem; color: var(--accent); font-weight: 600;">Show Example Files '
                                f'({len(data["examples"])} examples)</summary>\n')
                html_parts.append('<ul style="margin-top: 8px; margin-left: 20px; font-size: .85rem;">\n')
                for example in data["examples"]:
                    html_parts.append(f'<li><code>{_esc(example)}</code></li>\n')
                html_parts.append('</ul>\n</details>\n')

            html_parts.append('</div>\n')

    html_parts.append(f"""
<footer>
  Console Log Infrastructure Scanner | Generated {now}
</footer>
</body>
</html>
""")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(html_parts), encoding="utf-8")


# ---------------------------------------------------------------------------
# Historical Snapshot Management (Anomaly Detection)
# ---------------------------------------------------------------------------
def _get_snapshot_path(root_path: Path) -> Path:
    """Get the snapshot file path for a given scan root."""
    history_dir = Path(".history")
    history_dir.mkdir(exist_ok=True)

    # Create a safe filename from the path
    path_hash = hashlib.md5(str(root_path).encode()).hexdigest()[:12]
    safe_name = re.sub(r'[^\w\-]', '_', root_path.name or "root")
    return history_dir / f"infra_{safe_name}_{path_hash}.json"


def save_snapshot(report: Dict, root_path: Path) -> None:
    """Save current scan as a snapshot for historical comparison."""
    snapshot_path = _get_snapshot_path(root_path)

    # Load existing snapshots
    snapshots = []
    if snapshot_path.exists():
        try:
            with open(snapshot_path, "r", encoding="utf-8") as f:
                snapshots = json.load(f)
        except (json.JSONDecodeError, OSError):
            snapshots = []

    # Create new snapshot with key metrics
    snapshot = {
        "timestamp": report.get("scanned_at", datetime.now().isoformat()),
        "total_files": report.get("total_files_scanned", 0),
        "files_with_issues": report.get("files_with_issues", 0),
        "total_issues": report.get("total_issues", 0),
        "issue_rate": (report["files_with_issues"] / report["total_files_scanned"] * 100)
                     if report.get("total_files_scanned", 0) > 0 else 0,
    }

    # Add new snapshot and keep only last 7
    snapshots.append(snapshot)
    snapshots = snapshots[-7:]  # Keep last 7 snapshots

    # Save back to file
    try:
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(snapshots, f, indent=2, ensure_ascii=False)
    except OSError:
        pass  # Snapshot failure is not critical


def load_snapshots(root_path: Path) -> List[Dict]:
    """Load historical snapshots for comparison."""
    snapshot_path = _get_snapshot_path(root_path)

    if not snapshot_path.exists():
        return []

    try:
        with open(snapshot_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def detect_anomalies(current_report: Dict, snapshots: List[Dict]) -> Dict | None:
    """
    Compare current scan to historical baseline and detect anomalies.
    Returns anomaly info dict or None if no anomalies detected.
    """
    if len(snapshots) < 3:  # Need at least 3 historical scans
        return None

    # Calculate baseline from last 3-7 scans (excluding current)
    baseline_issue_rates = [s["issue_rate"] for s in snapshots[-7:-1] if "issue_rate" in s]
    baseline_total_issues = [s["total_issues"] for s in snapshots[-7:-1] if "total_issues" in s]

    if not baseline_issue_rates:
        return None

    avg_issue_rate = sum(baseline_issue_rates) / len(baseline_issue_rates)
    avg_total_issues = sum(baseline_total_issues) / len(baseline_total_issues)

    # Current metrics
    current_issue_rate = (current_report["files_with_issues"] / current_report["total_files_scanned"] * 100) \
                        if current_report.get("total_files_scanned", 0) > 0 else 0
    current_total_issues = current_report.get("total_issues", 0)

    # Detect significant changes (>30% increase)
    anomalies = []

    if avg_issue_rate > 0:
        issue_rate_change = ((current_issue_rate - avg_issue_rate) / avg_issue_rate) * 100
        if abs(issue_rate_change) > 30:  # 30% threshold
            anomalies.append({
                "metric": "Issue Rate",
                "current": current_issue_rate,
                "baseline": avg_issue_rate,
                "change_pct": issue_rate_change,
                "direction": "increase" if issue_rate_change > 0 else "decrease"
            })

    if avg_total_issues > 0:
        total_issues_change = ((current_total_issues - avg_total_issues) / avg_total_issues) * 100
        if abs(total_issues_change) > 30:  # 30% threshold
            anomalies.append({
                "metric": "Total Issues",
                "current": current_total_issues,
                "baseline": avg_total_issues,
                "change_pct": total_issues_change,
                "direction": "increase" if total_issues_change > 0 else "decrease"
            })

    if anomalies:
        return {
            "detected": True,
            "baseline_scans": len(baseline_issue_rates),
            "anomalies": anomalies
        }

    return None


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Infrastructure Scanner - Analyze console logs for infrastructure failures",
        epilog="Examples:\n"
               "  python scan_infra.py --all\n"
               "  python scan_infra.py --team servicedesk_team\n"
               "  python scan_infra.py --folder \"Z:\\console_logs\\MyJob\"\n",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Mutually exclusive: all OR team OR folder (one required)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--all",
        action="store_true",
        help="Scan all logs (last 7 days)"
    )
    mode_group.add_argument(
        "--team",
        type=str,
        help="Team ID from teams.json (scans team's logs, last 7 days)"
    )
    mode_group.add_argument(
        "--folder",
        type=Path,
        help="Specific folder to scan (last 7 days)"
    )

    parser.add_argument(
        "--teams-config",
        type=Path,
        default=TEAMS_CONFIG_FILE,
        help=f"Path to teams configuration file (default: {TEAMS_CONFIG_FILE})"
    )
    parser.add_argument(
        "--patterns",
        type=Path,
        default=PATTERNS_FILE,
        help=f"Path to patterns JSON file (default: {PATTERNS_FILE})"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON file path"
    )
    parser.add_argument(
        "--html",
        type=Path,
        help="Output HTML report path (auto-generated if not specified)"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Filter logs by last N days (default: 7)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports"),
        help="Output directory for HTML reports (default: reports)"
    )

    args = parser.parse_args()

    # Determine scan mode and path
    team_info = None
    team_jobs = None

    if args.all:
        # Scan all mode
        config = load_teams_config(args.teams_config)
        if config:
            base_paths = config.get("base_paths", {})
            base_path = base_paths.get("console_logs", "Z:\\console_logs")
            scan_path = Path(base_path)
        else:
            scan_path = Path("Z:\\console_logs")
        scan_mode = "all"
        scan_label = "All console logs"

    elif args.team:
        # Team mode
        print(f"\nLoading team configuration: {args.team}")
        config = load_teams_config(args.teams_config)
        if not config:
            print(f"Error: Cannot load teams config from {args.teams_config}")
            return 1

        team_info = get_team_info(args.team, config)
        if not team_info:
            print(f"Error: Team '{args.team}' not found in {args.teams_config}")
            return 1

        team_name = team_info.get("name", args.team)
        team_jobs = team_info.get("jobs", [])

        if not team_jobs:
            print(f"Error: Team '{team_name}' has no jobs defined")
            return 1

        print(f"Team: {team_name}")
        print(f"Jobs: {len(team_jobs)}")

        # Get base path from config
        base_paths = config.get("base_paths", {})
        base_path = base_paths.get("console_logs", "Z:\\console_logs")
        scan_path = Path(base_path)
        scan_mode = "team"
        scan_label = f"{team_name} ({len(team_jobs)} jobs)"

    else:
        # Folder mode
        scan_path = args.folder
        scan_mode = "folder"
        scan_label = str(scan_path)

    # Validate path exists
    if not scan_path.exists():
        print(f"Error: Path does not exist: {scan_path}")
        return 1

    # Load patterns
    print(f"\nLoading patterns from: {args.patterns}")
    patterns_config = load_patterns(args.patterns)
    print(f"Loaded {len(patterns_config.get('patterns', []))} search patterns")

    # Build report
    t0 = time.time()
    print(f"\nScanning: {scan_label}")
    print(f"Path: {scan_path}\n")

    report = build_report(
        scan_path,
        patterns_config,
        days=args.days,
        workers=MAX_WORKERS,
        team_jobs=team_jobs
    )

    # Print console report
    print_report(report)

    # Anomaly detection
    snapshots = load_snapshots(scan_path)
    anomalies = detect_anomalies(report, snapshots)

    if anomalies and anomalies.get("detected"):
        print("\n" + "!"*70)
        print("ANOMALY DETECTED")
        print("!"*70)
        print(f"Compared to last {anomalies['baseline_scans']} scans:")
        for a in anomalies["anomalies"]:
            sign = "+" if a["change_pct"] > 0 else ""
            print(f"  {a['metric']}: {a['current']:.1f} (baseline: {a['baseline']:.1f}) "
                  f"{sign}{a['change_pct']:.1f}% {a['direction']}")
        print("!"*70 + "\n")

    # Save snapshot for future comparison
    save_snapshot(report, scan_path)

    # Generate HTML report
    if args.html:
        html_path = args.html.resolve()
    else:
        # Ensure output directory exists
        reports_dir = args.output_dir
        reports_dir.mkdir(parents=True, exist_ok=True)

        if scan_mode == "team":
            html_path = reports_dir / f"infra_{args.team}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        elif scan_mode == "all":
            html_path = reports_dir / f"infra_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        else:
            folder_name = scan_path.name or "console"
            html_path = reports_dir / f"infra_{folder_name}.html"

        html_path = html_path.resolve()

    generate_html_report(report, html_path, anomalies=anomalies)
    print(f"\nHTML report: {html_path}")

    # Save JSON if requested
    if args.output:
        print(f"Saving JSON report: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    elapsed = time.time() - t0
    print(f"\nTotal time: {elapsed:.1f}s")

    return 0


if __name__ == "__main__":
    sys.exit(main())
