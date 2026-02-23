@echo off
REM =========================================================================
REM Stability Scan - Scan Team's Jobs
REM =========================================================================
REM This script scans all jobs owned by a specific team for test failures.
REM Team configuration is read from teams.json
REM
REM CONFIGURATION:
REM   - Edit TEAM_ID below to set the team you want to scan
REM
REM USAGE:
REM   1. Edit TEAM_ID below (must match a team_id in teams.json)
REM   2. Double-click this batch file or run from command line
REM
REM OUTPUT:
REM   - HTML report: stability_<teamid>_<timestamp>.html
REM   - Console output showing failure summary
REM =========================================================================

REM -------------------------------------------------------------------------
REM CONFIGURATION - Edit this section
REM -------------------------------------------------------------------------

REM Set the team ID from teams.json (e.g., servicedesk_team, frontend_team)
set TEAM_ID=servicedesk_team

REM -------------------------------------------------------------------------
REM Execution (do not modify below this line)
REM -------------------------------------------------------------------------

echo =========================================================================
echo Stability Scan - Team Mode
echo =========================================================================
echo.
echo Scanning team: %TEAM_ID%
echo.

REM Run the scanner
python scan_stability.py --team %TEAM_ID%

echo.
echo =========================================================================
echo Scan complete!
echo =========================================================================
echo.
pause
