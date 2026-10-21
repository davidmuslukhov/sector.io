@echo off
setlocal
cd /d "%~dp0"

set "ENV=%USERPROFILE%\micromamba\envs\city3d"
if exist "%ENV%\python.exe" (
  set "PATH=%ENV%;%ENV%\Library\bin;%ENV%\Scripts;%PATH%"
) else (
  goto :try_conda
)
"%ENV%\python.exe" city.py %*
exit /b %ERRORLEVEL%

:try_conda

where conda >nul 2>&1
if %ERRORLEVEL%==0 (
  call conda run -n city3d python city.py %*
  exit /b %ERRORLEVEL%
)

echo city3d is not installed. Run setup_env.bat first.
exit /b 1
