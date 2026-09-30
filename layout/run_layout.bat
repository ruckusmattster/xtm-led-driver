@echo off
setlocal EnableExtensions
rem ---------------------------------------------------------------------------------------------
rem  Lay out the XTM driver boards with KiCad 9 and Freerouting.
rem
rem    run_layout.bat                         both boards: place, route, pour, check, export
rem    run_layout.bat board_b                 one board
rem    run_layout.bat board_a --stage place   one board, with any make_board.py options
rem    run_layout.bat board_a --stage export  after editing the board in KiCad: check and export
rem
rem  Needs KiCad 9.0 (default install folder, or set KICAD_BIN to its bin folder) and a Java 21
rem  runtime (java on the PATH, or set JAVA to java.exe). Results go to out\board_a and out\board_b,
rem  each with a _run.log. See README.md.
rem ---------------------------------------------------------------------------------------------

rem started by double-click (cmd /c): keep the window open at the end
set "PAUSE_AT_END="
echo %CMDCMDLINE% | find /i "/c" >nul && set "PAUSE_AT_END=1"
set "RC=0"

if not defined KICAD_BIN set "KICAD_BIN=%ProgramFiles%\KiCad\9.0\bin"
if not exist "%KICAD_BIN%\python.exe" (
    echo KiCad 9 was not found in "%KICAD_BIN%".
    echo Install KiCad 9.0 from https://www.kicad.org/download/windows/ , or set KICAD_BIN to the
    echo bin folder of your KiCad 9 installation and run this again.
    set "RC=1" & goto end
)
rem KiCad's own command-prompt setup, when present, then KiCad's bin folder first on the PATH
if exist "%KICAD_BIN%\kicad-cmd.bat" call "%KICAD_BIN%\kicad-cmd.bat" >nul 2>nul
set "PATH=%KICAD_BIN%;%PATH%"
set "KICAD_CLI=%KICAD_BIN%\kicad-cli.exe"
set "PYTHONUTF8=1"

if not defined JAVA (
    where java >nul 2>nul
    if errorlevel 1 (
        echo Java was not found. Install a Java 21 runtime, for example from a Command Prompt:
        echo     winget install EclipseAdoptium.Temurin.21.JRE
        echo then open a NEW Command Prompt window and run this again.
        set "RC=1" & goto end
    )
)

"%KICAD_BIN%\python.exe" -c "import pcbnew" >nul 2>nul
if errorlevel 1 (
    echo KiCad's Python can't load pcbnew from here. Open "KiCad 9.0 Command Prompt" from the
    echo Start menu, go to this folder, and run:  python make_board.py board_b
    set "RC=1" & goto end
)

cd /d "%~dp0"
set "ARGS="
set "BOARDS=%~1"
if "%BOARDS%"=="" (set "BOARDS=board_b board_a") else (call :collect %*)

set "FAILED="
for %%B in (%BOARDS%) do (
    echo.
    echo ===== %%B =====
    "%KICAD_BIN%\python.exe" make_board.py %%B %ARGS%
    if errorlevel 1 set "FAILED=1"
)
echo.
if defined FAILED (
    echo Finished, with something left to look at: see out\^<board^>\^<board^>_run.log and README.md.
    set "RC=1" & goto end
)
echo Finished: DRC clean and fully connected. Outputs are in out\board_a and out\board_b.

:end
if defined PAUSE_AT_END pause
exit /b %RC%

:collect
shift
:collect_next
if "%~1"=="" exit /b 0
set "ARGS=%ARGS% %1"
shift
goto collect_next
