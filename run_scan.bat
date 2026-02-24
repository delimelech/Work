@echo off
REM Quick wrapper script for running QA scans via Docker (Windows)
REM
REM Usage:
REM   run_scan.bat "Scan stability for Data-Flow-Pipeline for 30 days"
REM   run_scan.bat "Run infra scan for servicedesk team"
REM

if "%~1"=="" (
    echo Error: No query provided
    echo.
    echo Usage: %~nx0 "^<your scan query^>"
    echo.
    echo Examples:
    echo   %~nx0 "Scan stability for Data-Flow-Pipeline for 30 days"
    echo   %~nx0 "Run infra scan for servicedesk team"
    echo   %~nx0 "Infrastructure scan all for 7 days"
    exit /b 1
)

REM Run the scan
docker-compose run --rm scanner %*

REM Show where the report was saved
echo.
echo Reports saved to: .\output\
dir /O-D .\output\*.html | findstr /V "Directory"
