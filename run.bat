@echo off
setlocal
chcp 65001 > nul
title Claude Code 대화 뷰어
cd /d "%~dp0"

rem ---- 1) 파이썬 찾기 (py 런처 또는 python). 윈도우 스토어 안내용 가짜 python 은 걸러진다.
set "PYEXE="
for %%C in (py python) do (
  if not defined PYEXE (
    %%C -c "import sys" >nul 2>nul && set "PYEXE=%%C"
  )
)
if not defined PYEXE goto nopython

rem ---- 2) 화면 라이브러리(pywebview) 확인
%PYEXE% -c "import webview" >nul 2>nul
if errorlevel 1 goto nowebview

:launch
rem ---- 3) 검은 창 없이 실행 (pythonw). 없으면 일반 python 으로 실행
set "PYW="
for /f "delims=" %%P in ('%PYEXE% -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do set "PYW=%%P"
if defined PYW if not exist "%PYW%" set "PYW="
if defined PYW (
  start "" "%PYW%" chat_export.py
) else (
  start "" %PYEXE% chat_export.py
)
exit /b 0

:nowebview
echo.
echo  화면을 그리는 pywebview 가 아직 설치되어 있지 않습니다.
set "ANS="
set /p ANS= 지금 설치하시겠습니까? (Y/N):
if /i not "%ANS%"=="Y" (
  echo  설치하지 않아 종료합니다.
  pause
  exit /b 1
)
%PYEXE% -m pip install pywebview || %PYEXE% -m pip install --user pywebview
if errorlevel 1 (
  echo.
  echo  설치하지 못했습니다. 인터넷 연결을 확인하거나 아래 명령을 직접 실행해 보십시오.
  echo    pip install pywebview
  pause
  exit /b 1
)
goto launch

:nopython
echo.
echo  이 PC에서 파이썬을 찾지 못했습니다.
echo   1. https://www.python.org/downloads/ 에서 파이썬 3 을 설치하십시오.
echo      설치 첫 화면에서 "Add python.exe to PATH" 를 꼭 체크하십시오.
echo   2. 설치가 끝나면 이 파일(run.bat)을 다시 실행하십시오.
echo.
set "ANS="
set /p ANS= 파이썬 내려받기 페이지를 여시겠습니까? (Y/N):
if /i "%ANS%"=="Y" start "" https://www.python.org/downloads/
pause
exit /b 1
