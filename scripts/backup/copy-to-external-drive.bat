@echo off
setlocal EnableExtensions
title Todira - copy backups to this drive
rem Copies the Todira backups from Google Drive (through the "Google Drive for desktop" app) to THIS drive.
rem Put this file in the main folder of the external drive and double-click it whenever the drive is connected.
rem Only new files are copied and nothing is ever deleted here, so the drive also keeps copies older than 30 days.
rem Setup and restore steps: docs/offsite-backup.md (also in the Drive folder as HOW-TO-RESTORE.md).

set "DEST=%~d0\Todira-backups"
set "SRC="
for %%D in (C D E F G H I J K L M N O P Q R S T U V W X Y Z) do (
  if /I not "%%D:"=="%~d0" if exist "%%D:\" (
    for /d %%F in ("%%D:\*") do (
      if exist "%%F\Todira-backups\HOW-TO-RESTORE.md" set "SRC=%%F\Todira-backups"
    )
  )
)

if not defined SRC (
  echo.
  echo Could not find the Todira-backups folder of Google Drive on this computer.
  echo Install "Google Drive for desktop", sign in with the same Google account,
  echo wait until "My Drive" shows the Todira-backups folder, then run this again.
  echo.
  pause
  exit /b 1
)

echo.
echo From: %SRC%
echo To:   %DEST%
echo.
robocopy "%SRC%" "%DEST%" /E /XO /R:2 /W:5 /NP /NDL
if %ERRORLEVEL% GEQ 8 (
  echo.
  echo FAILED - nothing was deleted; see the messages above.
  pause
  exit /b 1
)

echo.
echo Done. Database copies on this drive:
dir /b "%DEST%\todira-db-*.7z" 2>nul | find /c /v ""
echo.
pause
