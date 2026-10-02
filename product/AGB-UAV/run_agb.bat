@echo off
chcp 65001 >nul
title AGB Server Launcher
set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

echo.
echo ================================
echo   Kich hoat moi truong Python
echo ================================
echo.

if not exist "%ROOT_DIR%venv\Scripts\python.exe" (
    echo Loi: Khong tim thay "%ROOT_DIR%venv\Scripts\python.exe"
    pause
    exit /b 1
)
if not exist "%ROOT_DIR%viewer\server.py" (
    echo Loi: Khong tim thay "%ROOT_DIR%viewer\server.py"
    pause
    exit /b 1
)

call "%ROOT_DIR%venv\Scripts\activate.bat"

if errorlevel 1 (
    echo Loi: Khong the kich hoat moi truong venv.
    pause
    exit /b 1
)

echo.
echo ================================
echo   Chay viewer server
echo ================================
echo.
echo Mo trinh duyet tai http://127.0.0.1:8765/
echo Giu cua so nay mo khi dung viewer.
echo.

"%ROOT_DIR%venv\Scripts\python.exe" -u "%ROOT_DIR%viewer\server.py"
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo Loi khi chay "%ROOT_DIR%viewer\server.py"
    pause
    exit /b %RC%
)

echo.
echo ----------------
echo Server da ket thuc.
echo ----------------
pause
