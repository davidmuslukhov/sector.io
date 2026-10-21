@echo off
setlocal
cd /d "%~dp0"

set "ENV_NAME=city3d"
set "MAMBA_ROOT_PREFIX=%USERPROFILE%\micromamba"
set "CONDA_PKGS_DIRS=%USERPROFILE%\micromamba\pkgs"
set "MM=%LOCALAPPDATA%\micromamba\micromamba.exe"

if exist "%MM%" goto :micromamba

where conda >nul 2>&1
if %ERRORLEVEL%==0 goto :conda

echo Could not find Micromamba or conda.
echo Install Micromamba, or add conda to PATH, then run this script again.
exit /b 1

:micromamba
if exist "%MAMBA_ROOT_PREFIX%\envs\%ENV_NAME%\python.exe" (
  "%MM%" install -y -n %ENV_NAME% -f environment.yml -c conda-forge
) else (
  "%MM%" create -y -n %ENV_NAME% -f environment.yml -c conda-forge
)
if errorlevel 1 exit /b 1
goto :ready

:conda
call conda env list | findstr /B /C:"%ENV_NAME% " >nul
if %ERRORLEVEL%==0 (
  call conda env update -n %ENV_NAME% -f environment.yml --prune
) else (
  call conda env create -f environment.yml
)
if errorlevel 1 exit /b 1

:ready
echo.
echo Environment %ENV_NAME% is ready.
echo Launch the city with run_city.bat
exit /b 0
