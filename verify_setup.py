#!/usr/bin/env python3
"""
Setup Verification Script

Verifies that the refactored QA scanning tools are properly configured.
Run this script to check your setup before using the scanners.

Usage:
    python verify_setup.py
"""

import json
import sys
from pathlib import Path


def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_status(check_name, passed, message=""):
    """Print a check status."""
    status = "[PASS]" if passed else "[FAIL]"
    color = "\033[92m" if passed else "\033[91m"
    reset = "\033[0m"
    print(f"{color}{status}{reset} {check_name}")
    if message:
        print(f"       {message}")


def verify_file_exists(filepath, description):
    """Verify a file exists."""
    path = Path(filepath)
    exists = path.exists()
    if not exists:
        print_status(description, False, f"File not found: {filepath}")
    else:
        print_status(description, True, f"Found: {filepath}")
    return exists


def verify_json_file(filepath, description):
    """Verify a JSON file exists and is valid."""
    path = Path(filepath)
    if not path.exists():
        print_status(description, False, f"File not found: {filepath}")
        return False, None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print_status(description, True, f"Valid JSON: {filepath}")
        return True, data
    except json.JSONDecodeError as e:
        print_status(description, False, f"Invalid JSON: {e}")
        return False, None
    except Exception as e:
        print_status(description, False, f"Error reading file: {e}")
        return False, None


def verify_teams_config(config):
    """Verify teams.json structure."""
    print_header("Teams Configuration Validation")

    all_checks_passed = True

    # Check base_paths
    if "base_paths" not in config:
        print_status("base_paths section", False, "Missing base_paths section")
        all_checks_passed = False
    else:
        print_status("base_paths section", True)

        base_paths = config["base_paths"]
        if "allure_reports" in base_paths:
            print_status("  allure_reports path", True, base_paths["allure_reports"])
        else:
            print_status("  allure_reports path", False, "Missing allure_reports path")
            all_checks_passed = False

        if "console_logs" in base_paths:
            print_status("  console_logs path", True, base_paths["console_logs"])
        else:
            print_status("  console_logs path", False, "Missing console_logs path")
            all_checks_passed = False

    # Check teams
    if "teams" not in config:
        print_status("teams section", False, "Missing teams section")
        all_checks_passed = False
        return all_checks_passed

    teams = config["teams"]
    if not teams:
        print_status("teams section", False, "No teams defined")
        all_checks_passed = False
        return all_checks_passed

    print_status("teams section", True, f"{len(teams)} teams defined")

    # Check each team
    for team_id, team_info in teams.items():
        if not isinstance(team_info, dict):
            print_status(f"  Team: {team_id}", False, "Invalid team structure")
            all_checks_passed = False
            continue

        has_name = "name" in team_info
        has_jobs = "jobs" in team_info and isinstance(team_info["jobs"], list)

        if has_name and has_jobs:
            job_count = len(team_info["jobs"])
            print_status(
                f"  Team: {team_id}",
                True,
                f"{team_info['name']} ({job_count} jobs)"
            )
        else:
            missing = []
            if not has_name:
                missing.append("name")
            if not has_jobs:
                missing.append("jobs")
            print_status(
                f"  Team: {team_id}",
                False,
                f"Missing fields: {', '.join(missing)}"
            )
            all_checks_passed = False

    return all_checks_passed


def verify_patterns_config(config):
    """Verify console_log_patterns.json structure."""
    print_header("Console Log Patterns Validation")

    all_checks_passed = True

    # Check patterns
    if "patterns" not in config:
        print_status("patterns section", False, "Missing patterns section")
        return False

    patterns = config["patterns"]
    if not isinstance(patterns, list):
        print_status("patterns section", False, "patterns must be a list")
        return False

    if not patterns:
        print_status("patterns section", False, "No patterns defined")
        return False

    print_status("patterns section", True, f"{len(patterns)} patterns defined")

    # Check each pattern
    required_fields = ["name", "search_strings", "severity", "category", "description"]
    for i, pattern in enumerate(patterns):
        missing = [f for f in required_fields if f not in pattern]
        if missing:
            print_status(
                f"  Pattern {i+1}",
                False,
                f"Missing fields: {', '.join(missing)}"
            )
            all_checks_passed = False
        else:
            name = pattern.get("name", f"Pattern {i+1}")
            severity = pattern.get("severity", "unknown")
            print_status(
                f"  Pattern: {name}",
                True,
                f"Severity: {severity}"
            )

    # Check settings
    if "settings" in config:
        print_status("settings section", True)
    else:
        print_status("settings section", False, "Missing settings section")
        all_checks_passed = False

    return all_checks_passed


def main():
    """Run all verification checks."""
    print_header("QA Scanning Tools - Setup Verification")
    print("\nThis script verifies your refactored QA scanning setup.\n")

    all_passed = True

    # Check core Python scripts
    print_header("Core Python Scripts")
    all_passed &= verify_file_exists("scan_stability.py", "Stability Scanner")
    all_passed &= verify_file_exists("scan_infra.py", "Infrastructure Scanner")

    # Check batch files
    print_header("Batch Files")
    all_passed &= verify_file_exists("scan_stability_folder.bat", "Stability Folder Batch")
    all_passed &= verify_file_exists("scan_stability_team.bat", "Stability Team Batch")
    all_passed &= verify_file_exists("scan_infra_all.bat", "Infrastructure All Batch")
    all_passed &= verify_file_exists("scan_infra_team.bat", "Infrastructure Team Batch")
    all_passed &= verify_file_exists("scan_infra_folder.bat", "Infrastructure Folder Batch")

    # Check configuration files
    print_header("Configuration Files")

    # Verify teams.json
    teams_valid, teams_config = verify_json_file("teams.json", "Teams Configuration")
    all_passed &= teams_valid
    if teams_valid:
        all_passed &= verify_teams_config(teams_config)

    # Verify console_log_patterns.json
    patterns_valid, patterns_config = verify_json_file(
        "console_log_patterns.json",
        "Console Log Patterns"
    )
    all_passed &= patterns_valid
    if patterns_valid:
        all_passed &= verify_patterns_config(patterns_config)

    # Check cache directory
    print_header("Cache Directory")
    cache_dir = Path(".cache")
    if cache_dir.exists():
        print_status("Cache directory", True, f"Found: {cache_dir.absolute()}")
    else:
        print_status(
            "Cache directory",
            True,
            "Not found (will be created automatically)"
        )

    # Final summary
    print_header("Verification Summary")
    if all_passed:
        print("\n[SUCCESS] All checks passed! Your setup is ready to use.")
        print("\nNext steps:")
        print("  1. Edit teams.json to add your teams and jobs")
        print("  2. Update base_paths in teams.json to point to your network drives")
        print("  3. Run a test scan:")
        print("     python scan_stability.py --team <your_team_id>")
        print("     python scan_infra.py --team <your_team_id>")
        return 0
    else:
        print("\n[FAILED] Some checks failed. Please fix the issues above.")
        print("\nCommon fixes:")
        print("  - Ensure all required files are present")
        print("  - Verify JSON files have valid syntax")
        print("  - Check that teams.json has all required fields")
        return 1


if __name__ == "__main__":
    sys.exit(main())
