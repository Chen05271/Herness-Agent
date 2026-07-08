@echo off
setlocal

call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 (
  echo Failed to load Visual Studio build tools.
  exit /b 1
)

set "PGROOT=D:\develop\PostgreSQL18"
set "WORKDIR=%TEMP%\pgvector-build"

if exist "%WORKDIR%" rmdir /s /q "%WORKDIR%"
mkdir "%WORKDIR%"
cd /d "%WORKDIR%"

git clone --branch v0.8.4 --depth 1 https://github.com/pgvector/pgvector.git
if errorlevel 1 exit /b 1

cd pgvector
nmake /F Makefile.win
if errorlevel 1 exit /b 1

nmake /F Makefile.win install
if errorlevel 1 exit /b 1

echo.
echo pgvector installed. Enable with:
echo   psql -d herness -c "CREATE EXTENSION IF NOT EXISTS vector;"
