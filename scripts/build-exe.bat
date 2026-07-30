@echo off
title LLM Wiki - Build EXE

echo ========================================
echo   LLM Wiki - Build EXE
echo ========================================
echo.
cd /d "%~dp0.."
echo [WORKDIR] %cd%
echo.

:: --------------------------------------------------
:: 1. Build frontend
:: --------------------------------------------------
echo [1/4] Building frontend (npm run build)...
cd wiki-ui-v2
call npm run build
if %errorlevel% neq 0 (
  echo [ERROR] Frontend build failed!
  exit /b 1
)
cd ..
echo [OK] Frontend build complete
echo.

:: --------------------------------------------------
:: 2. Run tests
:: --------------------------------------------------
echo [2/4] Running tests...
call python -m pytest tests/ -x -q --no-header
if %errorlevel% neq 0 (
  echo [WARN] Tests failed, continuing anyway...
) else (
  echo [OK] All tests passed
)
echo.

:: --------------------------------------------------
:: 3. Clean previous build
:: --------------------------------------------------
echo [3/4] Cleaning previous build...
if exist "dist\LLM-Wiki.exe" del "dist\LLM-Wiki.exe"
if exist "build\LLM-Wiki" rmdir /s /q "build\LLM-Wiki"
echo [OK] Clean complete
echo.

:: --------------------------------------------------
:: 4. PyInstaller
:: --------------------------------------------------
echo [4/4] Running PyInstaller (this may take a few minutes)...
call pyinstaller wiki-llm.spec --clean --noconfirm
if %errorlevel% neq 0 (
  echo [ERROR] PyInstaller build failed!
  exit /b 1
)
echo.

:: --------------------------------------------------
:: Done
:: --------------------------------------------------
echo ========================================
echo   Build complete!
echo   Output: dist\LLM-Wiki.exe
echo ========================================

:: Show file size
for %%f in ("dist\LLM-Wiki.exe") do (
    set "SZ=%%~zf"
    set /a "MB=%%~zf / 1048576"
)
call echo   Size: %%SZ%% bytes (%%MB%% MB)
if not defined SZ echo   [WARN] dist\LLM-Wiki.exe not found

echo.
echo Press any key to exit...
pause >nul
