@echo off
rem AIT Skill entry point - self-installing Windows wrapper.
rem Lazy-creates a venv inside the skill directory on first run, then forwards
rem all args to `python -m ait.cli`.
rem
rem Stdout MUST stay pristine for the JSON contract -- all setup messages go to
rem stderr.

setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%.." >nul
set "SKILL_DIR=%CD%"
popd >nul

set "VENV_DIR=%SKILL_DIR%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import ait" >nul 2>nul
    if not errorlevel 1 goto :run
)

echo [ait] First-time setup: creating venv in %VENV_DIR% ... 1>&2

set "SYS_PY="
for %%P in (python3.13 python3.12 python3.11 python3.10 python3 python) do (
    if not defined SYS_PY (
        where %%P >nul 2>nul
        if not errorlevel 1 (
            %%P -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)" >nul 2>nul
            if not errorlevel 1 set "SYS_PY=%%P"
        )
    )
)

if not defined SYS_PY (
    echo {"ok":false,"error":"Python 3.10+ not found on PATH. Install Python 3.10 or newer and try again.","code":"PYTHON_MISSING"}
    exit /b 1
)

if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%"
%SYS_PY% -m venv "%VENV_DIR%" 1>&2
if errorlevel 1 (
    echo {"ok":false,"error":"Failed to create venv.","code":"VENV_CREATE_FAILED"}
    exit /b 1
)

"%VENV_PY%" -m pip install --quiet --disable-pip-version-check --upgrade pip 1>&2
"%VENV_PY%" -m pip install --quiet --disable-pip-version-check "%SKILL_DIR%" 1>&2
if errorlevel 1 (
    echo {"ok":false,"error":"Failed to install ait package. Check internet connectivity for the first install.","code":"PIP_INSTALL_FAILED"}
    exit /b 1
)

echo [ait] Setup complete. 1>&2

:run
"%VENV_PY%" -m ait.cli %*
