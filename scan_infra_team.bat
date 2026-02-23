@echo off
REM =========================================================================
REM Infrastructure Scan - Scan Team's Console Logs
REM =========================================================================
REM This script scans console logs for a specific team's jobs.
REM Team configuration is read from teams.json
REM Only scans files modified/created in the last 7 days.
REM
REM CONFIGURATION:
REM   - Edit TEAM_ID below to set the team you want to scan
REM
REM USAGE:
REM   1. Edit TEAM_ID below (must match a team_id in teams.json)
REM   2. Double-click this batch file or run from command line
REM
REM OUTPUT:
REM   - HTML report: infra_<teamid>_<timestamp>.html
REM   - Console output showing infrastructure issues summary
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
echo Infrastructure Scan - Team Mode
echo =========================================================================
echo.
echo Scanning team: %TEAM_ID%
echo Filtering to last 7 days
echo.

REM Run the scanner
python scan_infra.py --team %TEAM_ID%

echo.
echo =========================================================================
echo Scan complete!
echo =========================================================================
echo.
pause
