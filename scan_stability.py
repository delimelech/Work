#!/usr/bin/env python3
"""
Stability Scanner - Allure Test Failure Analysis

Scans Allure test reports (HTML or JSON) to identify test failures and generate
comprehensive stability reports. Optimized for large network drives with parallel
processing and intelligent caching.

Usage:
    python scan_stability.py --folder "Z:\\allure_reports\\MyJob"
    python scan_stability.py --team servicedesk_team

Features:
    - Parallel processing with 100 workers for fast network scanning
    - Smart caching to avoid re-scanning unchanged data
    - Extracts failures from Allure HTML reports (single-file format)
    - Extracts failures from *-result.json files
    - Supports zip archives containing reports
    - Team-based filtering using teams.json
    - Generates HTML reports with failure analysis
"""

import argparse
import base64
import hashlib
import html as html_mod
import json
import os
import re
import sys
import time
import zipfile

# Fix Windows console encoding for Unicode characters
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FAILURE_STATUSES = {"failed", "broken"}
TEAMS_CONFIG_FILE = Path("teams.json")
MAX_WORKERS = 100  # Concurrent threads for network I/O

# ---------------------------------------------------------------------------
# Fast Allure HTML Extraction
# ---------------------------------------------------------------------------
# Pre-compiled regex pattern for extracting embedded JSON from Allure HTML
_D_CALL_RE = re.compile(r"d\(\s*'([^']+)'\s*,\s*'([A-Za-z0-9+/=]+)'\s*\)")


def _find_entry(html: str, entry_name: str, start: int = 0) -> object | None:
    """
    Find a single d('entry_name', 'base64_data') call in Allure HTML.
    Returns decoded JSON object or None if not found.
    """
    needle = f"'{entry_name}'"
    pos = html.find(needle, start)
    if pos == -1:
        return None

    # Search backwards to find the d( function call
    search_start = max(0, pos - 5)
    m = _D_CALL_RE.search(html, search_start)
    if m and m.group(1) == entry_name:
        try:
            return json.loads(base64.b64decode(m.group(2)).decode("utf-8", errors="replace"))
        except (ValueError, json.JSONDecodeError):
            return None
    return None


def _quick_failure_count(html: str) -> tuple[int, int]:
    """
    Quickly extract failure count from statistic.json without parsing all test data.
    Returns (failed_count, total_count).
    """
    data = _find_entry(html, "widgets/statistic.json")
    if isinstance(data, dict):
        return data.get("failed", 0), data.get("total", 0)
    return 0, 0


def _extract_environment_url(html: str) -> str:
    """Extract the URL from allure_environment.json for environment tracking."""
    data = _find_entry(html, "widgets/allure_environment.json")
    if isinstance(data, list):
        url_entry = next((e for e in data if isinstance(e, dict) and e.get("name") == "URL"), None)
        if url_entry and url_entry.get("values"):
            return url_entry["values"][0]
    return ""


def _extract_failed_results(html: str) -> list[dict]:
    """
    Extract only test results that are failed/broken from Allure HTML.
    Uses targeted search to avoid parsing all test data.
    """
    results = []
    search_from = 0

    while True:
        pos = html.find("'data/test-results/", search_from)
        if pos == -1:
            break

        m = _D_CALL_RE.search(html, pos - 3)
        if not m:
            search_from = pos + 20
            continue

        search_from = m.end()
        try:
            data = json.loads(base64.b64decode(m.group(2)).decode("utf-8", errors="replace"))
        except (ValueError, json.JSONDecodeError):
            continue

        if isinstance(data, dict) and data.get("status", "").lower() in FAILURE_STATUSES:
            results.append(data)

    return results


def _count_total_results(html: str) -> int:
    """Count how many test-result entries exist without decoding them all."""
    count = 0
    search_from = 0
    while True:
        pos = html.find("'data/test-results/", search_from)
        if pos == -1:
            break
        count += 1
        search_from = pos + 20
    return count


# ---------------------------------------------------------------------------
# Step / Result Parsing
# ---------------------------------------------------------------------------
# Normalize retry/attempt numbering for better aggregation
_ATTEMPT_RE = re.compile(r"Attempt \d+", re.IGNORECASE)
_RETRY_RE = re.compile(r"Retry \d+", re.IGNORECASE)


def _normalize_step_name(name: str) -> str:
    """
    Normalize step names by replacing numbered attempts with 'N'.
    Example: 'Attempt 1 failed' -> 'Attempt N failed'
    This allows identical failures to be aggregated.
    """
    name = _ATTEMPT_RE.sub("Attempt N", name)
    name = _RETRY_RE.sub("Retry N", name)
    return name


def extract_failed_steps_from_obj(obj: dict, test_name: str = "") -> list[dict]:
    """
    Recursively extract failed/broken steps from a test result.
    Returns list of dicts with step name, message, test name, and status.
    """
    failed = []
    for step in obj.get("steps") or []:
        step_name = _normalize_step_name(step.get("name") or "(unnamed step)")
        status = (step.get("status") or "").lower()
        status_details = step.get("statusDetails") or {}
        message = (status_details.get("message") or "").strip() or None

        if status in FAILURE_STATUSES:
            failed.append({
                "name": step_name,
                "message": message,
                "test_name": test_name,
                "status": status
            })

        # Recursively process nested steps
        failed.extend(extract_failed_steps_from_obj(
            step, test_name=test_name or (obj.get("name") or "")))

    return failed


def parse_result_data(data: dict, source_label: str = "") -> tuple[list[dict], bool]:
    """
    Parse Allure result JSON and extract failed steps.
    Returns (failed_steps, test_has_failure).
    Deduplicates steps with the same normalized name within a single test.
    """
    test_name = data.get("name") or data.get("fullName") or source_label
    test_status = (data.get("status") or "").lower()
    test_has_failure = test_status in FAILURE_STATUSES

    # Extract all failed steps
    raw_steps = extract_failed_steps_from_obj(data, test_name=test_name)

    # Deduplicate: keep only first occurrence of each normalized step name
    seen = set()
    failed_steps = []
    for s in raw_steps:
        if s["name"] not in seen:
            seen.add(s["name"])
            failed_steps.append(s)

    # If test failed but no failed steps, capture test-level failure
    if test_has_failure and not failed_steps:
        sd = data.get("statusDetails") or {}
        failed_steps.append({
            "name": f"TEST: {test_name}",
            "message": (sd.get("message") or "").strip() or None,
            "test_name": test_name,
            "status": test_status
        })

    return failed_steps, test_has_failure


# ---------------------------------------------------------------------------
# Process HTML Report (Worker Thread)
# ---------------------------------------------------------------------------
def _process_html(html: str, source_label: str) -> dict:
    """
    Process one HTML report and extract failure information.
    Uses fast path: checks statistic.json first to skip reports with no failures.
    """
    # Quick check: does this report have failures?
    failed_count, total_count = _quick_failure_count(html)

    # Fallback: count test-result entries if statistic.json missing
    if total_count == 0:
        total_count = _count_total_results(html)

    result = {
        "source_label": source_label,
        "total_tests": total_count,
        "environment": "",
        "failures": [],  # list of (display, failed_steps, test_failed)
    }

    # Fast path: skip expensive extraction if no failures
    if failed_count == 0:
        return result

    # Extract environment and failed results
    result["environment"] = _extract_environment_url(html)
    for data in _extract_failed_results(html):
        failed_steps, test_failed = parse_result_data(data, source_label)
        name = data.get("name") or data.get("fullName") or data.get("uuid") or ""
        display = f"{source_label}#{name}"
        result["failures"].append((display, failed_steps, test_failed))

    return result


# ---------------------------------------------------------------------------
# Directory Scanning
# ---------------------------------------------------------------------------
def find_allure_sources(root: Path) -> tuple[list[Path], list[Path], list[tuple[Path, str, str]]]:
    """
    Single os.walk pass to find all Allure data sources.
    Returns (json_files, html_files, zip_entries).
    """
    json_files, html_files, zip_paths = [], [], []
    dirs_scanned = 0
    t0 = time.time()

    print(f"Scanning directory tree: {root}")

    for dirpath, _dirnames, filenames in os.walk(str(root)):
        dirs_scanned += 1
        if dirs_scanned % 500 == 0:
            elapsed = time.time() - t0
            print(f"  ... {dirs_scanned} dirs scanned ({elapsed:.1f}s)", flush=True)

        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            lower = fn.lower()

            if fn.endswith("-result.json"):
                json_files.append(Path(fp))
            elif lower.endswith(".html"):
                html_files.append(fp)
            elif lower.endswith(".zip"):
                zip_paths.append(fp)

    elapsed = time.time() - t0
    print(f"  Scan complete: {dirs_scanned} dirs, {len(json_files)} JSON, "
          f"{len(html_files)} HTML, {len(zip_paths)} ZIP ({elapsed:.1f}s)")

    # Scan zip archives for embedded reports
    zip_entries: list[tuple[Path, str, str]] = []
    for zp in zip_paths:
        try:
            with zipfile.ZipFile(zp, "r") as zf:
                for name in zf.namelist():
                    n = name.replace("\\", "/")
                    if "-result.json" in n and n.endswith(".json"):
                        zip_entries.append((Path(zp), name, "json"))
                    elif n.lower().endswith(".html"):
                        zip_entries.append((Path(zp), name, "html"))
        except (zipfile.BadZipFile, OSError):
            continue

    return json_files, html_files, zip_entries


# ---------------------------------------------------------------------------
# Worker Functions for ThreadPoolExecutor
# ---------------------------------------------------------------------------
def _worker_disk_html(filepath: str, root_str: str) -> dict:
    """Thread worker: read and process one HTML file from disk."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            html = f.read()
        # Get file modification time
        mtime = os.path.getmtime(filepath)
    except OSError:
        return {"source_label": filepath, "total_tests": 0, "environment": "", "failures": [], "mtime": None}

    # Build relative label
    try:
        label = os.path.relpath(filepath, root_str)
    except ValueError:
        label = os.path.basename(filepath)

    result = _process_html(html, label)
    result["mtime"] = mtime
    return result


def _worker_zip_html(zip_path: str, member_name: str, root_str: str) -> dict:
    """Thread worker: read and process one HTML file from a zip archive."""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            with zf.open(member_name) as f:
                html = f.read().decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, OSError, KeyError):
        return {
            "source_label": f"{zip_path}!{member_name}",
            "total_tests": 0,
            "environment": "",
            "failures": []
        }

    try:
        zrel = os.path.relpath(zip_path, root_str)
        label = f"{zrel}!{member_name}"
    except ValueError:
        label = f"{os.path.basename(zip_path)}!{member_name}"

    return _process_html(html, label)


# ---------------------------------------------------------------------------
# Cache Management
# ---------------------------------------------------------------------------
def _get_cache_key(root_path: Path) -> str:
    """Generate cache key based on path and last modified time."""
    try:
        stat = root_path.stat()
        path_hash = hashlib.md5(str(root_path).encode()).hexdigest()[:8]
        mtime = int(stat.st_mtime)
        return f"scan_{path_hash}_{mtime}"
    except (OSError, AttributeError):
        return None


def _load_cached_report(cache_key: str) -> dict:
    """Load cached report if available and fresh (less than 24 hours old)."""
    cache_dir = Path(".cache")
    cache_file = cache_dir / f"{cache_key}.json"

    if cache_file.exists():
        try:
            cache_age = time.time() - cache_file.stat().st_mtime
            if cache_age < 86400:  # 24 hours
                print(f"Loading cached scan (age: {cache_age/3600:.1f} hours)...")
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return None


def _save_cached_report(cache_key: str, report: dict) -> None:
    """Save report to cache for future use."""
    cache_dir = Path(".cache")
    cache_dir.mkdir(exist_ok=True)
    cache_file = cache_dir / f"{cache_key}.json"

    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"Cached scan results to {cache_file}")
    except OSError:
        pass  # Cache failure is not critical


# ---------------------------------------------------------------------------
# Build Report
# ---------------------------------------------------------------------------
def build_report(root_path: Path, use_cache: bool = True) -> dict:
    """
    Crawl root_path for Allure data and build failure report.
    Uses parallel processing and skip-no-failure optimization for speed.
    """
    root_str = str(root_path)

    # Try cache first
    if use_cache:
        cache_key = _get_cache_key(root_path)
        if cache_key:
            cached = _load_cached_report(cache_key)
            if cached:
                return cached

    # Find all sources
    disk_json, disk_html, zip_entries = find_allure_sources(root_path)

    # Initialize accumulators
    per_report: list[dict] = []
    step_occurrences: dict[str, int] = defaultdict(int)
    total_result_files = 0
    reports_with_failures = 0
    total_failed_steps = 0
    oldest_file_time = None
    newest_file_time = None

    # --- Process disk JSON files (usually few, sequential is fine) ---
    for path in disk_json:
        total_result_files += 1
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        failed_steps, test_failed = parse_result_data(data, path.stem)
        if failed_steps or test_failed:
            reports_with_failures += 1
            total_failed_steps += len(failed_steps)
            per_report.append({
                "file": str(path),
                "test_failed": test_failed,
                "failed_step_count": len(failed_steps),
                "failed_steps": failed_steps,
                "environment": ""
            })

            # Track step occurrences
            for s in failed_steps:
                msg = (s["message"] or "")[:80].replace("\n", " ").strip()
                key = s["name"] + (f" | {msg}" if msg else "")
                step_occurrences[key] += 1

    # --- Process HTML files (disk + zip) in parallel ---
    n_html = len(disk_html)
    n_zip_html = sum(1 for _, _, k in zip_entries if k == "html")
    total_to_process = n_html + n_zip_html

    print(f"\nProcessing {total_to_process} HTML reports with {MAX_WORKERS} threads...")

    futures = []
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        # Submit disk HTML files
        for fp in disk_html:
            futures.append(pool.submit(_worker_disk_html, fp, root_str))

        # Submit zip HTML files
        for zp, member, kind in zip_entries:
            if kind == "html":
                futures.append(pool.submit(_worker_zip_html, str(zp), member, root_str))

        # Process results as they complete
        done_count = 0
        skipped = 0

        for future in as_completed(futures):
            done_count += 1
            if done_count % 200 == 0:
                elapsed = time.time() - t0
                rate = done_count / elapsed if elapsed > 0 else 0
                eta = (total_to_process - done_count) / rate if rate > 0 else 0
                print(f"  ... {done_count}/{total_to_process} done "
                      f"({elapsed:.0f}s, ~{eta:.0f}s left, {skipped} skipped)", flush=True)

            res = future.result()
            total_result_files += res["total_tests"]

            # Track file modification times for date range
            if res.get("mtime"):
                if oldest_file_time is None or res["mtime"] < oldest_file_time:
                    oldest_file_time = res["mtime"]
                if newest_file_time is None or res["mtime"] > newest_file_time:
                    newest_file_time = res["mtime"]

            if not res["failures"]:
                skipped += 1
                continue

            env = res["environment"]
            for display, failed_steps, test_failed in res["failures"]:
                if failed_steps or test_failed:
                    reports_with_failures += 1
                    total_failed_steps += len(failed_steps)
                    per_report.append({
                        "file": display,
                        "test_failed": test_failed,
                        "failed_step_count": len(failed_steps),
                        "failed_steps": failed_steps,
                        "environment": env
                    })

                    # Track step occurrences
                    for s in failed_steps:
                        msg = (s["message"] or "")[:80].replace("\n", " ").strip()
                        key = s["name"] + (f" | {msg}" if msg else "")
                        step_occurrences[key] += 1

    # --- Process zip JSON entries (usually few) ---
    for zp, member, kind in zip_entries:
        if kind != "json":
            continue

        total_result_files += 1
        try:
            with zipfile.ZipFile(str(zp), "r") as zf:
                with zf.open(member) as f:
                    data = json.loads(f.read().decode("utf-8", errors="replace"))
        except (zipfile.BadZipFile, OSError, json.JSONDecodeError, KeyError):
            continue

        failed_steps, test_failed = parse_result_data(data, f"{zp.name}!{member}")
        if failed_steps or test_failed:
            reports_with_failures += 1
            total_failed_steps += len(failed_steps)
            per_report.append({
                "file": f"{zp.name}!{member}",
                "test_failed": test_failed,
                "failed_step_count": len(failed_steps),
                "failed_steps": failed_steps,
                "environment": ""
            })

            for s in failed_steps:
                msg = (s["message"] or "")[:80].replace("\n", " ").strip()
                key = s["name"] + (f" | {msg}" if msg else "")
                step_occurrences[key] += 1

    elapsed = time.time() - t0
    print(f"  Done: {total_to_process} reports in {elapsed:.1f}s "
          f"({skipped} had no failures, skipped full parse)")

    # Calculate date range
    date_range_days = None
    date_range_str = "N/A"
    if oldest_file_time and newest_file_time:
        date_range_days = (newest_file_time - oldest_file_time) / 86400  # Convert to days
        oldest_date = datetime.fromtimestamp(oldest_file_time).strftime("%Y-%m-%d")
        newest_date = datetime.fromtimestamp(newest_file_time).strftime("%Y-%m-%d")
        if date_range_days < 1:
            date_range_str = f"Last 24 hours ({oldest_date})"
        elif date_range_days <= 7:
            date_range_str = f"Last {int(date_range_days)+1} days ({oldest_date} to {newest_date})"
        elif date_range_days <= 30:
            date_range_str = f"Last {int(date_range_days)+1} days ({oldest_date} to {newest_date})"
        else:
            date_range_str = f"{int(date_range_days)+1} days ({oldest_date} to {newest_date})"

    # Build final report
    report = {
        "root": root_str,
        "total_result_files": total_result_files,
        "reports_with_failures": reports_with_failures,
        "total_failed_steps": total_failed_steps,
        "num_reports_scanned": total_to_process,  # Number of HTML reports scanned
        "scan_date": datetime.now().isoformat(),
        "date_range_days": date_range_days,
        "date_range_str": date_range_str,
        "per_report": per_report,
        "step_occurrences": sorted(
            [{"step": k, "count": v} for k, v in step_occurrences.items()],
            key=lambda x: -x["count"]
        ),
    }

    # Cache the result
    if use_cache:
        cache_key = _get_cache_key(root_path)
        if cache_key:
            _save_cached_report(cache_key, report)

    return report


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
# Console Output
# ---------------------------------------------------------------------------
def print_report(report: dict, verbose: bool = False) -> None:
    """Print report to console."""
    r = report
    print("\n" + "="*70)
    print("STABILITY SCAN REPORT")
    print("="*70)
    print(f"Root folder: {r['root']}")

    if r.get("team_filter"):
        print(f"Team filter: {r['team_filter']} ({len(r.get('team_jobs', []))} jobs)")

    print(f"Total result files scanned: {r['total_result_files']}")
    print()
    print("--- SUMMARY ---")
    print(f"Reports with failures: {r['reports_with_failures']}")

    if r["reports_with_failures"] > 0:
        print(f"Total failed steps: {r['total_failed_steps']}")
        failure_rate = (r['reports_with_failures'] / r['total_result_files'] * 100) if r['total_result_files'] > 0 else 0
        print(f"Failure rate: {failure_rate:.1f}%")

    print()
    print("--- FAILED STEP FREQUENCY ---")
    if not r["step_occurrences"]:
        print("(none)")
    else:
        for item in r["step_occurrences"]:
            print(f"  [{item['count']:4d}x] {item['step']}")

    print()

    if verbose and r["per_report"]:
        print("--- PER-REPORT DETAILS ---")
        for rec in r["per_report"]:
            print(f"  {rec['file']}")
            for s in rec["failed_steps"]:
                msg = f" - {s['message']}" if s["message"] else ""
                print(f"    - {s['name']}{msg}")
        print("="*70)


# ---------------------------------------------------------------------------
# HTML Report Generation
# ---------------------------------------------------------------------------
def _esc(text: str) -> str:
    """Escape HTML special characters."""
    return html_mod.escape(str(text)) if text else ""


def _env_name(url: str) -> str:
    """Extract tenant name from URL: 'https://barclays.aternity.com' -> 'BARCLAYS'."""
    m = re.match(r"https?://([^.]+)\.", url)
    return m.group(1).upper() if m else url


def _extract_build_name(file_label: str) -> str:
    """Extract build/job name from file label."""
    # Handle zip entries (format: path.zip!member)
    if "!" in file_label:
        file_label = file_label.split("!")[0]

    # Handle test result entries (format: path#testname)
    if "#" in file_label:
        file_label = file_label.split("#")[0]

    # For index.html files, get parent directory name (usually the build number)
    p = Path(file_label)
    if p.stem.lower() == "index":
        # Return parent folder name (usually build number like "12345")
        return p.parent.name if p.parent.name else p.stem

    return p.stem


def generate_html_report(report: dict, output_path: Path, anomalies: dict = None) -> None:
    """Generate HTML report from scan results with optional anomaly detection."""
    r = report
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = r["total_result_files"]
    with_fail = r["reports_with_failures"]
    pass_count = total - with_fail
    fail_pct = (with_fail / total * 100) if total else 0

    # Analyze failure environments
    failure_envs: dict[str, set] = defaultdict(set)
    failure_counts: dict[str, int] = defaultdict(int)
    builds_seen: set[str] = set()

    for rec in r["per_report"]:
        builds_seen.add(_extract_build_name(rec["file"]))
        env = rec.get("environment", "")
        for s in rec["failed_steps"]:
            failure_counts[s["name"]] += 1
            if env:
                failure_envs[s["name"]].add(env)

    # Build HTML
    parts: list[str] = []
    parts.append(f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stability Scan Report</title>
<style>
  :root {{
    --bg: #f5f7fa; --card: #fff; --accent: #4361ee; --red: #e63946;
    --green: #2a9d8f; --gray: #6c757d; --border: #dee2e6;
    --text: #212529; --light-text: #495057;
    --orange: #f77f00; --yellow: #fcbf49;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
         background: var(--bg); color: var(--text); padding: 24px; max-width: 1400px;
         margin: 0 auto; }}
  .header {{ text-align: center; margin-bottom: 12px; }}
  h1 {{ font-size: 2.5rem; margin: 0; color: var(--accent); display: inline-flex;
       align-items: center; gap: 12px; font-weight: 700; }}
  .title-icon {{ width: 42px; height: 42px; }}
  .subtitle {{ color: var(--gray); font-size: .9rem; margin-bottom: 28px; line-height: 1.5; text-align: center; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 18px; margin-bottom: 36px; }}
  .card {{ background: var(--card); border-radius: 12px; padding: 24px;
           box-shadow: 0 2px 8px rgba(0,0,0,.1); text-align: center; transition: transform 0.2s; }}
  .card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,.15); }}
  .card .value {{ font-size: 2.5rem; font-weight: 700; line-height: 1; }}
  .card .label {{ font-size: .8rem; color: var(--gray); margin-top: 8px; text-transform: uppercase;
                  letter-spacing: .6px; font-weight: 600; }}
  .card.red .value {{ color: var(--red); }}
  .card.green .value {{ color: var(--green); }}
  .card.blue .value {{ color: var(--accent); }}
  section {{ margin-bottom: 40px; }}
  h2 {{ font-size: 1.3rem; margin-bottom: 16px; border-bottom: 3px solid var(--accent);
        display: inline-block; padding-bottom: 4px; color: var(--accent); font-weight: 700; }}
  table {{ width: 100%; border-collapse: collapse; background: var(--card);
           border-radius: 10px; overflow: hidden;
           box-shadow: 0 2px 8px rgba(0,0,0,.1); margin-top: 12px; }}
  th {{ background: var(--accent); color: #fff; text-align: left; padding: 12px 16px;
       font-size: .85rem; text-transform: uppercase; letter-spacing: .5px; font-weight: 700; }}
  td {{ padding: 12px 16px; border-bottom: 1px solid var(--border); font-size: .95rem;
       vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #f8f9ff; }}
  tr.high-impact {{ background: #fff0f0; }}
  tr.high-impact:hover td {{ background: #ffe6e6; }}
  tr.medium-impact {{ background: #fff8e6; }}
  tr.medium-impact:hover td {{ background: #fff3d9; }}
  .bar-cell {{ position: relative; min-width: 140px; }}
  .bar {{ height: 24px; border-radius: 5px; background: linear-gradient(90deg, var(--red) 0%, #ff6b6b 100%);
          display: inline-block; vertical-align: middle; box-shadow: 0 2px 4px rgba(230,57,70,.3); }}
  .bar-label {{ margin-left: 10px; font-weight: 700; font-size: .9rem; color: var(--text); }}
  .pct-cell {{ text-align: center; font-size: 1rem; color: var(--red); min-width: 80px; }}
  .pct-cell strong {{ font-weight: 800; }}
  .badge {{ display: inline-block; padding: 4px 10px; border-radius: 5px;
            font-size: .75rem; font-weight: 700; text-transform: uppercase; letter-spacing: .3px; }}
  .badge.failed {{ background: #fce4e4; color: var(--red); border: 1px solid #ffcccb; }}
  .badge.broken {{ background: #fff3cd; color: #856404; border: 1px solid #ffe69c; }}
  .badge.passed {{ background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }}
  .msg {{ color: var(--light-text); font-size: .85rem; margin-top: 2px; line-height: 1.4; }}
  .no-fail {{ color: var(--green); font-weight: 700; font-size: 1.1rem; padding: 20px;
              background: #e8f5f3; border-radius: 8px; text-align: center; }}
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
      <path d="M3 13h2l2-7 4 14 4-14 2 7h4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="none"/>
    </svg>
    Stability Scan Report
  </h1>
</div>
<div class="subtitle">Generated {_esc(now)} &mdash; Root: <code>{_esc(r["root"])}</code>""")

    if r.get("team_filter"):
        parts.append(f" &mdash; Team: <strong>{_esc(r['team_filter'])}</strong>")

    if r.get("date_range_str"):
        parts.append(f" &mdash; Period: <strong>{_esc(r['date_range_str'])}</strong>")

    parts.append("</div>\n")

    # Summary cards
    parts.append(f"""\
<div class="cards">
  <div class="card blue"><div class="value">{r.get("num_reports_scanned", 0)}</div><div class="label">HTML Reports Scanned</div></div>
  <div class="card blue"><div class="value">{total}</div><div class="label">Total Tests Scanned</div></div>
  <div class="card green"><div class="value">{pass_count}</div><div class="label">Passed</div></div>
  <div class="card red"><div class="value">{with_fail}</div><div class="label">Failed</div></div>
  <div class="card red"><div class="value">{r["total_failed_steps"]}</div><div class="label">Failed Steps</div></div>
  <div class="card"><div class="value">{fail_pct:.1f}%</div><div class="label">Failure Rate</div></div>
</div>
""")

    # Anomaly detection alert
    if anomalies and anomalies.get("detected"):
        parts.append('<div class="anomaly-alert">\n')
        parts.append(f'<h3>Anomaly Detected (compared to last {anomalies["baseline_scans"]} scans)</h3>\n')
        for a in anomalies["anomalies"]:
            change_class = a["direction"]
            sign = "+" if a["change_pct"] > 0 else ""
            parts.append(f'<div class="metric"><strong>{_esc(a["metric"])}:</strong> '
                        f'{a["current"]:.1f} (baseline: {a["baseline"]:.1f}) '
                        f'<span class="{change_class}">{sign}{a["change_pct"]:.1f}% {a["direction"]}</span></div>\n')
        parts.append('</div>\n')

    # Failure Summary
    parts.append('<section>\n<h2>Failure Summary</h2>\n')
    if failure_counts:
        sorted_failures = sorted(failure_counts.items(), key=lambda x: -x[1])
        max_count = sorted_failures[0][1]
        total_failed_steps = r["total_failed_steps"]

        parts.append('<table>\n<thead><tr><th>#</th><th>Failed Test / Step</th>'
                     '<th>Count</th><th>% of Total</th><th>Environments</th></tr></thead>\n<tbody>\n')

        for i, (step_key, count) in enumerate(sorted_failures, 1):
            bar_width = count / max_count * 100  # Bar width relative to max
            pct_of_total = (count / total_failed_steps * 100) if total_failed_steps > 0 else 0  # Percentage of total
            envs = sorted(failure_envs.get(step_key, set()))
            envs_html = "<br>".join(_esc(_env_name(e)) for e in envs) if envs else "&mdash;"

            # Color coding based on percentage
            if pct_of_total >= 50:
                row_class = 'class="high-impact"'
            elif pct_of_total >= 20:
                row_class = 'class="medium-impact"'
            else:
                row_class = ''

            parts.append(f'<tr {row_class}><td>{i}</td><td>{_esc(step_key)}</td>'
                         f'<td class="bar-cell"><span class="bar" style="width:{bar_width:.0f}%"></span>'
                         f'<span class="bar-label">{count}x</span></td>'
                         f'<td class="pct-cell"><strong>{pct_of_total:.1f}%</strong></td>'
                         f'<td>{envs_html}</td></tr>\n')

        parts.append("</tbody></table>\n")
    else:
        parts.append('<p class="no-fail">No failures found.</p>\n')
    parts.append("</section>\n")

    # Failure Patterns with Examples
    if r["per_report"]:
        parts.append('<section>\n<h2>Failure Patterns with Examples</h2>\n')

        # Group failures by (step_name, message_pattern)
        patterns = defaultdict(lambda: {"count": 0, "examples": [], "environments": set(), "status": ""})

        for rec in r["per_report"]:
            for s in rec["failed_steps"]:
                step_name = s["name"]
                msg = (s.get("message") or "No error message provided").strip()

                # Truncate long messages to create a pattern key
                msg_pattern = msg[:150] if msg else "No error message"
                pattern_key = (step_name, msg_pattern)

                patterns[pattern_key]["count"] += 1
                patterns[pattern_key]["status"] = s["status"]

                # Add example file (limit to 5 examples per pattern)
                if len(patterns[pattern_key]["examples"]) < 5:
                    build_name = _extract_build_name(rec["file"])
                    patterns[pattern_key]["examples"].append(build_name)

                # Track environments
                if rec.get("environment"):
                    patterns[pattern_key]["environments"].add(rec["environment"])

        # Sort patterns by count (most frequent first)
        sorted_patterns = sorted(patterns.items(), key=lambda x: -x[1]["count"])

        # Display each pattern
        for i, ((step_name, msg_pattern), data) in enumerate(sorted_patterns, 1):
            envs = sorted(data["environments"])
            envs_str = ", ".join(_esc(_env_name(e)) for e in envs[:5])
            if len(envs) > 5:
                envs_str += f" +{len(envs)-5} more"

            parts.append(f'<div style="background: #f8f9fa; border-left: 4px solid var(--accent); '
                        f'padding: 16px; margin: 16px 0; border-radius: 6px;">\n')
            parts.append(f'<h3 style="color: var(--accent); font-size: 1.05rem; margin-bottom: 8px;">'
                        f'Pattern #{i}: {_esc(step_name)}</h3>\n')
            parts.append(f'<div style="display: grid; grid-template-columns: auto 1fr; gap: 8px 16px; '
                        f'font-size: .9rem; margin-bottom: 12px;">\n')
            parts.append(f'<strong>Occurrences:</strong><span>{data["count"]}x</span>\n')
            parts.append(f'<strong>Status:</strong><span><span class="badge {data["status"]}">'
                        f'{data["status"].upper()}</span></span>\n')
            if envs:
                parts.append(f'<strong>Environments:</strong><span>{envs_str}</span>\n')
            parts.append('</div>\n')

            # Error message
            parts.append(f'<div style="background: #fff; padding: 12px; border-radius: 4px; '
                        f'margin-bottom: 12px; border: 1px solid var(--border);">\n')
            parts.append(f'<strong style="font-size: .85rem; color: var(--gray);">Error Message:</strong><br>\n')
            parts.append(f'<code style="display: block; margin-top: 6px; white-space: pre-wrap; '
                        f'word-break: break-word;">{_esc(msg_pattern)}</code>\n')
            parts.append('</div>\n')

            # Example files
            if data["examples"]:
                parts.append(f'<details style="margin-top: 8px;"><summary style="cursor: pointer; '
                            f'font-size: .9rem; color: var(--accent); font-weight: 600;">Show Example Files '
                            f'({len(data["examples"])} examples)</summary>\n')
                parts.append('<ul style="margin-top: 8px; margin-left: 20px; font-size: .85rem;">\n')
                for example in data["examples"]:
                    parts.append(f'<li><code>{_esc(example)}</code></li>\n')
                parts.append('</ul>\n</details>\n')

            parts.append('</div>\n')

        parts.append("</section>\n")

    parts.append(f'<footer>Stability Scan Reporter &mdash; scanned {total} test results '
                 f'from {len(builds_seen)} builds</footer>\n</body></html>')

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(parts), encoding="utf-8")


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
    return history_dir / f"stability_{safe_name}_{path_hash}.json"


def save_snapshot(report: dict, root_path: Path) -> None:
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
        "timestamp": report.get("scan_date", datetime.now().isoformat()),
        "total_tests": report.get("total_result_files", 0),
        "failed_tests": report.get("reports_with_failures", 0),
        "failed_steps": report.get("total_failed_steps", 0),
        "failure_rate": (report["reports_with_failures"] / report["total_result_files"] * 100)
                       if report.get("total_result_files", 0) > 0 else 0,
        "num_reports": report.get("num_reports_scanned", 0),
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


def load_snapshots(root_path: Path) -> list[dict]:
    """Load historical snapshots for comparison."""
    snapshot_path = _get_snapshot_path(root_path)

    if not snapshot_path.exists():
        return []

    try:
        with open(snapshot_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def detect_anomalies(current_report: dict, snapshots: list[dict]) -> dict | None:
    """
    Compare current scan to historical baseline and detect anomalies.
    Returns anomaly info dict or None if no anomalies detected.
    """
    if len(snapshots) < 3:  # Need at least 3 historical scans
        return None

    # Calculate baseline from last 3-7 scans (excluding current)
    baseline_failure_rates = [s["failure_rate"] for s in snapshots[-7:-1] if "failure_rate" in s]
    baseline_failed_steps = [s["failed_steps"] for s in snapshots[-7:-1] if "failed_steps" in s]

    if not baseline_failure_rates:
        return None

    avg_failure_rate = sum(baseline_failure_rates) / len(baseline_failure_rates)
    avg_failed_steps = sum(baseline_failed_steps) / len(baseline_failed_steps)

    # Current metrics
    current_failure_rate = (current_report["reports_with_failures"] / current_report["total_result_files"] * 100) \
                          if current_report.get("total_result_files", 0) > 0 else 0
    current_failed_steps = current_report.get("total_failed_steps", 0)

    # Detect significant changes (>30% increase)
    anomalies = []

    if avg_failure_rate > 0:
        failure_rate_change = ((current_failure_rate - avg_failure_rate) / avg_failure_rate) * 100
        if abs(failure_rate_change) > 30:  # 30% threshold
            anomalies.append({
                "metric": "Failure Rate",
                "current": current_failure_rate,
                "baseline": avg_failure_rate,
                "change_pct": failure_rate_change,
                "direction": "increase" if failure_rate_change > 0 else "decrease"
            })

    if avg_failed_steps > 0:
        failed_steps_change = ((current_failed_steps - avg_failed_steps) / avg_failed_steps) * 100
        if abs(failed_steps_change) > 30:  # 30% threshold
            anomalies.append({
                "metric": "Failed Steps",
                "current": current_failed_steps,
                "baseline": avg_failed_steps,
                "change_pct": failed_steps_change,
                "direction": "increase" if failed_steps_change > 0 else "decrease"
            })

    if anomalies:
        return {
            "detected": True,
            "baseline_scans": len(baseline_failure_rates),
            "anomalies": anomalies
        }

    return None


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stability Scanner - Analyze Allure test reports for failures",
        epilog="Examples:\n"
               "  python scan_stability.py --folder \"Z:\\allure_reports\\MyJob\"\n"
               "  python scan_stability.py --team servicedesk_team\n",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Mutually exclusive: folder OR team (one required)
    location_group = parser.add_mutually_exclusive_group(required=True)
    location_group.add_argument(
        "--folder",
        type=Path,
        help="Specific folder to scan (e.g., Z:\\allure_reports\\MyJob)"
    )
    location_group.add_argument(
        "--team",
        type=str,
        help="Team ID from teams.json (scans team's job folders)"
    )

    parser.add_argument(
        "--teams-config",
        type=Path,
        default=TEAMS_CONFIG_FILE,
        help=f"Path to teams configuration file (default: {TEAMS_CONFIG_FILE})"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed per-report failure information"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Write JSON report to file"
    )
    parser.add_argument(
        "--html",
        type=Path,
        help="Output HTML report path (auto-generated if not specified)"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Force fresh scan, ignore cached results"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Filter reports by last N days (default: 30)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports"),
        help="Output directory for HTML reports (default: reports)"
    )

    args = parser.parse_args()

    # Determine scan location and mode
    if args.folder:
        # Folder mode: scan specific folder
        folder = args.folder
        scan_mode = "folder"
        scan_label = str(folder)
        team_info = None
    else:
        # Team mode: load team config and scan base path
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
        base_path = base_paths.get("allure_reports", "Z:\\allure_reports")
        folder = Path(base_path)
        scan_mode = "team"
        scan_label = f"{team_name} ({len(team_jobs)} jobs)"

    # Validate folder exists
    try:
        folder = folder.resolve()
    except OSError:
        folder = Path(str(folder))

    if not folder.is_dir():
        print(f"Error: not a directory: {folder}")
        return 1

    # Scan
    t0 = time.time()
    print(f"\nScanning: {scan_label}")
    print(f"Path: {folder}\n")

    report = build_report(folder, use_cache=not args.no_cache)

    # Filter by team if in team mode
    if scan_mode == "team":
        print(f"\nFiltering results to {team_info['name']}'s jobs...")
        team_jobs = team_info["jobs"]
        filtered_per_report = []
        step_counts = defaultdict(int)

        for rec in report.get("per_report", []):
            file_path = rec["file"].lower()
            # Check if any team job matches the file path
            if any(job.lower() in file_path for job in team_jobs):
                filtered_per_report.append(rec)
                for step in rec.get("failed_steps", []):
                    msg = (step["message"] or "")[:80].replace("\n", " ").strip()
                    key = step["name"] + (f" | {msg}" if msg else "")
                    step_counts[key] += 1

        # Update report with filtered data
        report["per_report"] = filtered_per_report
        report["reports_with_failures"] = len(filtered_per_report)
        report["total_failed_steps"] = sum(len(rec.get("failed_steps", [])) for rec in filtered_per_report)
        report["step_occurrences"] = sorted(
            [{"step": k, "count": v} for k, v in step_counts.items()],
            key=lambda x: -x["count"]
        )
        report["team_filter"] = team_info["name"]
        report["team_jobs"] = team_jobs

        print(f"Filtered: {len(filtered_per_report)} failures from {team_info['name']}'s jobs")

    # Print console report
    print_report(report, verbose=args.verbose)

    # Anomaly detection
    snapshots = load_snapshots(folder)
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
    save_snapshot(report, folder)

    # Generate HTML report
    if args.html:
        html_path = args.html.resolve()
    else:
        # Ensure output directory exists
        reports_dir = args.output_dir
        reports_dir.mkdir(parents=True, exist_ok=True)

        if scan_mode == "team":
            html_path = reports_dir / f"stability_{args.team}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        else:
            folder_name = folder.name or "allure"
            html_path = reports_dir / f"stability_{folder_name}.html"

        html_path = html_path.resolve()

    generate_html_report(report, html_path, anomalies=anomalies)
    print(f"\nHTML report: {html_path}")

    # Save JSON if requested
    if args.output:
        out = args.output.resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"JSON report: {out}")

    print(f"\nTotal time: {time.time() - t0:.1f}s")

    return 0


if __name__ == "__main__":
    sys.exit(main())
