@echo off
REM =========================================================================
REM Infrastructure Scan - Scan All Console Logs
REM =========================================================================
REM This script scans all console logs for infrastructure issues.
REM Only scans files modified/created in the last 7 days.
REM
REM USAGE:
REM   - Double-click this batch file or run from command line
REM   - No configuration needed
REM
REM OUTPUT:
REM   - HTML report: infra_all_<timestamp>.html
REM   - Console output showing infrastructure issues summary
REM =========================================================================

echo =========================================================================
echo Infrastructure Scan - All Logs Mode
echo =========================================================================
echo.
echo Scanning all console logs (last 7 days)
echo.

REM Run the scanner
python scan_infra.py --all

echo.
echo =========================================================================
echo Scan complete!
echo =========================================================================
echo.
pause
