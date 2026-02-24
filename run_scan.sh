#!/bin/bash
#
# Quick wrapper script for running QA scans via Docker
#
# Usage:
#   ./run_scan.sh "Scan stability for Data-Flow-Pipeline for 30 days"
#   ./run_scan.sh "Run infra scan for servicedesk team"
#

if [ -z "$1" ]; then
    echo "Error: No query provided"
    echo ""
    echo "Usage: $0 \"<your scan query>\""
    echo ""
    echo "Examples:"
    echo "  $0 \"Scan stability for Data-Flow-Pipeline for 30 days\""
    echo "  $0 \"Run infra scan for servicedesk team\""
    echo "  $0 \"Infrastructure scan all for 7 days\""
    exit 1
fi

# Run the scan
docker-compose run --rm scanner "$1"

# Show where the report was saved
echo ""
echo "Reports saved to: ./output/"
ls -lh ./output/ | tail -5
