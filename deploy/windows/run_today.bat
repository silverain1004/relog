@echo off
rem Ad-hoc run: analyze today's logs and mail only to from_addr (for right after an incident)
pushd "%~dp0"
win_analyzer.exe --today --test-email
pause
