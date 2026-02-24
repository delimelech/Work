#!/usr/bin/env python3
"""
Conversational Agent for QA Scanners

Handles natural language queries for stability and infrastructure scans.
Parses user intent and executes the appropriate scanner.

Usage:
    python agent.py "Scan stability for Data-Flow-Pipeline for last 30 days"
    python agent.py "Run infra scan for servicedesk team"
    python agent.py "Stability scan for my-job"
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


class ScannerAgent:
    """Conversational agent for parsing scan requests."""

    def __init__(self, allure_base: str, console_base: str, output_dir: str):
        self.allure_base = Path(allure_base)
        self.console_base = Path(console_base)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def parse_query(self, query: str) -> dict:
        """
        Parse natural language query to extract scan intent.

        Returns:
            dict with keys: scan_type, target_type, target_name, days
        """
        query_lower = query.lower()

        # Determine scan type
        scan_type = None
        if any(word in query_lower for word in ["stability", "stable", "allure", "test"]):
            scan_type = "stability"
        elif any(word in query_lower for word in ["infra", "infrastructure", "console", "log"]):
            scan_type = "infra"

        if not scan_type:
            raise ValueError("Cannot determine scan type. Use 'stability' or 'infra' in your query.")

        # Determine target type (team, folder, or all)
        target_type = None
        target_name = None

        # Check for team
        team_match = re.search(r'team\s+(\S+)', query_lower)
        if team_match:
            target_type = "team"
            target_name = team_match.group(1)

        # Check for folder/job
        folder_patterns = [
            r'folder\s+([^\s,]+)',
            r'job\s+([^\s,]+)',
            r'for\s+([A-Za-z0-9_-]+(?:-[A-Za-z0-9_-]+)*)',  # Matches job names like Data-Flow-Pipeline
        ]

        if not target_type:
            for pattern in folder_patterns:
                match = re.search(pattern, query)
                if match:
                    target_type = "folder"
                    target_name = match.group(1)
                    break

        # Check for "all"
        if not target_type and any(word in query_lower for word in ["all", "everything"]):
            target_type = "all"

        if not target_type:
            raise ValueError("Cannot determine target. Specify 'team <name>', 'folder <name>', or 'all'.")

        # Extract days
        days = None
        days_patterns = [
            r'(\d+)\s*days?',
            r'last\s+(\d+)',
            r'past\s+(\d+)',
        ]

        for pattern in days_patterns:
            match = re.search(pattern, query_lower)
            if match:
                days = int(match.group(1))
                break

        # Apply defaults if no days specified
        if days is None:
            days = 30 if scan_type == "stability" else 7

        return {
            "scan_type": scan_type,
            "target_type": target_type,
            "target_name": target_name,
            "days": days
        }

    def execute_scan(self, intent: dict) -> int:
        """Execute the appropriate scanner based on parsed intent."""
        scan_type = intent["scan_type"]
        target_type = intent["target_type"]
        target_name = intent["target_name"]
        days = intent["days"]

        print(f"\n{'='*70}")
        print(f"EXECUTING SCAN")
        print(f"{'='*70}")
        print(f"Type: {scan_type.upper()}")
        print(f"Target: {target_type.upper()} - {target_name or 'ALL'}")
        print(f"Period: Last {days} days")
        print(f"Output: {self.output_dir}")
        print(f"{'='*70}\n")

        # Build command
        if scan_type == "stability":
            cmd = ["python", "scan_stability.py"]

            if target_type == "team":
                cmd.extend(["--team", target_name])
            elif target_type == "folder":
                folder_path = self.allure_base / target_name
                cmd.extend(["--folder", str(folder_path)])
            elif target_type == "all":
                # For "all", we need to specify the base allure path
                cmd.extend(["--folder", str(self.allure_base)])

            # Add days parameter
            cmd.extend(["--days", str(days)])

            # Add output directory
            cmd.extend(["--output-dir", str(self.output_dir)])

        else:  # infra
            cmd = ["python", "scan_infra.py"]

            if target_type == "team":
                cmd.extend(["--team", target_name])
            elif target_type == "folder":
                folder_path = self.console_base / target_name
                cmd.extend(["--folder", str(folder_path)])
            elif target_type == "all":
                cmd.append("--all")

            # Add days parameter
            cmd.extend(["--days", str(days)])

            # Add output directory
            cmd.extend(["--output-dir", str(self.output_dir)])

        # Execute
        print(f"Running: {' '.join(cmd)}\n")
        result = subprocess.run(cmd, cwd=Path(__file__).parent)
        return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Conversational Agent for QA Scanners",
        epilog="""
Examples:
  python agent.py "Scan stability for Data-Flow-Pipeline for last 30 days"
  python agent.py "Run infra scan for servicedesk team"
  python agent.py "Stability scan for my-job"
  python agent.py "Infrastructure scan all for 14 days"
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "query",
        type=str,
        help="Natural language scan request"
    )
    parser.add_argument(
        "--allure-base",
        type=str,
        default="/data/allure_reports",
        help="Base path for Allure reports (default: /data/allure_reports)"
    )
    parser.add_argument(
        "--console-base",
        type=str,
        default="/data/console_logs",
        help="Base path for console logs (default: /data/console_logs)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="/output",
        help="Output directory for HTML reports (default: /output)"
    )

    args = parser.parse_args()

    try:
        agent = ScannerAgent(args.allure_base, args.console_base, args.output_dir)
        intent = agent.parse_query(args.query)

        print(f"\nParsed Intent:")
        print(f"  Scan Type: {intent['scan_type']}")
        print(f"  Target Type: {intent['target_type']}")
        print(f"  Target Name: {intent['target_name']}")
        print(f"  Days: {intent['days']}")

        return agent.execute_scan(intent)

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("\nPlease specify a clear request like:", file=sys.stderr)
        print('  "Scan stability for Data-Flow-Pipeline for 30 days"', file=sys.stderr)
        print('  "Run infra scan for servicedesk team"', file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
