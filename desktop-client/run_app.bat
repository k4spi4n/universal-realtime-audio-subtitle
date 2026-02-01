@echo off
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo Building application...
call mvn clean compile

echo.
echo Running application (Java Client + Python Backend)...
call mvn javafx:run
pause