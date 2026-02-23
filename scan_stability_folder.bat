@echo off
REM =========================================================================
REM Stability Scan - Scan Specific Folder
REM =========================================================================
REM This script scans a specific Allure report folder for test failures.
REM
REM CONFIGURATION:
REM   - Edit FOLDER_PATH below to set the folder you want to scan
REM
REM USAGE:
REM   1. Edit FOLDER_PATH below
REM   2. Double-click this batch file or run from command line
REM
REM OUTPUT:
REM   - HTML report: stability_<foldername>.html
REM   - Console output showing failure summary
REM =========================================================================

REM -------------------------------------------------------------------------
REM CONFIGURATION - Edit this section
REM -------------------------------------------------------------------------

REM Set the folder path to scan (example: Z:\allure_reports\MyJob)
set FOLDER_PATH=Z:\allure_reports\MyJob

REM -------------------------------------------------------------------------
REM Execution (do not modify below this line)
REM -------------------------------------------------------------------------

echo =========================================================================
echo Stability Scan - Folder Mode
echo =========================================================================
echo.
echo Scanning folder: %FOLDER_PATH%
echo.

REM Run the scanner
python scan_stability.py --folder "%FOLDER_PATH%"

echo.
echo =========================================================================
echo Scan complete!
echo =========================================================================
echo.
pause
