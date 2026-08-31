@echo off
rem Start the training run console from Windows. Pin this to the taskbar.
rem
rem All it does is hand tools/train-gui.sh to WSL; every decision lives there.
rem
rem If the repository lives on the WSL filesystem rather than on a Windows drive,
rem this file is reached over \\wsl.localhost\... and wslpath cannot convert that
rem path. Set TRAIN_GUI_WSL_PATH below to the script's path *inside* WSL
rem (for example /home/you/Econsult/tools/train-gui.sh) and it is used as-is.
setlocal

set "TRAIN_GUI_WSL_PATH="

if defined TRAIN_GUI_WSL_PATH (
  wsl.exe -e bash -lc "exec bash '%TRAIN_GUI_WSL_PATH%'"
) else (
  wsl.exe -e bash -lc "exec bash \"$(wslpath -a '%~dp0train-gui.sh')\""
)

rem Keep the window up when the console refuses to start, so the reason (a
rem missing FastAPI, a port already bound) can actually be read.
if errorlevel 1 pause
endlocal
