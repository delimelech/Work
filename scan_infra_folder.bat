@echo off
REM =========================================================================
REM Infrastructure Scan - Scan Specific Folder
REM =========================================================================
REM This script scans console logs in a specific folder for infrastructure issues.
REM Only scans files modified/created in the last 7 days.
REM
REM CONFIGURATION:
REM   - Edit FOLDER_PATH below to set the folder you want to scan
REM
REM USAGE:
REM   1. Edit FOLDER_PATH below
REM   2. Double-click this batch file or run from command line
REM
REM OUTPUT:
REM   - HTML report: infra_<foldername>.html
REM   - Console output showing infrastructure issues summary
REM =========================================================================

REM -------------------------------------------------------------------------
REM CONFIGURATION - Edit this section
REM -------------------------------------------------------------------------

REM Set the folder path to scan (example: Z:\console_logs\MyJob)
set FOLDER_PATH=Z:\console_logs\MyJob

REM -------------------------------------------------------------------------
REM Execution (do not modify below this line)
REM -------------------------------------------------------------------------

echo =========================================================================
echo Infrastructure Scan - Folder Mode
echo =========================================================================
echo.
echo Scanning folder: %FOLDER_PATH%
echo Filtering to last 7 days
echo.

REM Run the scanner
python scan_infra.py --folder "%FOLDER_PATH%"

echo.
echo =========================================================================
echo Scan complete!
echo =========================================================================
echo.
pause
