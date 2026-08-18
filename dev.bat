@echo off
REM Sobe o dashboard META em modo dev, auto-bootstrap.
REM Uso (PowerShell ou cmd): .\dev.bat
REM
REM O que faz sozinho, na ordem, sempre idempotente:
REM   1. Cria .venv se faltar (usa `python` do sistema)
REM   2. Sincroniza requirements.txt so quando o hash muda
REM   3. Inicializa db/journal.sqlite se ausente
REM   4. Baixa historico de mercado se data/raw/ vazio
REM   5. Sobe uvicorn com hot-reload em http://127.0.0.1:8000
REM   Ctrl+C encerra uvicorn e todos os workers do reloader

setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "VENV=%~dp0.venv"
set "PY=%VENV%\Scripts\python.exe"
set "REQS=requirements.txt"
set "MARKER=%VENV%\.reqs.sha256"

REM 1) venv
if not exist "%PY%" (
    echo ==^> Criando .venv...
    python -m venv .venv
    if not exist "%PY%" (
        echo ERRO: nao consegui criar .venv. Verifique se `python` esta no PATH.
        exit /b 1
    )
    "%PY%" -m pip install --disable-pip-version-check -q --upgrade pip
)

REM 2) deps (checa hash de requirements.txt)
if exist "%REQS%" (
    set "CURR="
    for /f "delims=" %%h in ('certutil -hashfile "%REQS%" SHA256 ^| findstr /r "^[0-9a-fA-F]"') do set "CURR=%%h"
    set "STORED="
    if exist "%MARKER%" set /p STORED=<"%MARKER%"
    if not "!CURR!"=="!STORED!" (
        echo ==^> Sincronizando dependencias...
        "%PY%" -m pip install --disable-pip-version-check -q -r "%REQS%"
        > "%MARKER%" echo !CURR!
    )
)

REM 3) banco
if not exist "db\journal.sqlite" (
    echo ==^> Inicializando banco...
    "%PY%" scripts\init_db.py
)

REM 4) dados
dir /b "data\raw\*.parquet" >nul 2>&1
if errorlevel 1 (
    echo ==^> Baixando historico de mercado...
    "%PY%" scripts\download_data.py
)

REM 5) dashboard — Ctrl+C mata uvicorn; tree-kill defensivo abaixo apanha o que sobreviver
echo ==^> Dashboard META em http://127.0.0.1:8000 ^(Ctrl+C para parar^)
echo ==^> Hot-reload ativo: edicoes em src/ recarregam automaticamente

"%PY%" -m uvicorn --app-dir src dashboard.app:app --reload --host 127.0.0.1 --port 8000

REM Ao voltar (Ctrl+C ou saida normal), garante que nada ficou orfao na porta 8000.
REM Uvicorn --reload cria master + filho spawn: quando o master morre, o filho
REM herda o socket. Precisamos matar em loop ate a porta liberar (o `netstat`
REM sempre reporta o PID do binder original, que pode ja estar morto; e nesse
REM caso `taskkill /T` nao acha filhos. Loop resolve: mata o vivo, netstat troca
REM pro proximo owner, mata de novo, ate liberar).
set /a _tries=0
:cleanup_loop
set "_pid="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /r "TCP.*127.0.0.1:8000.*LISTENING"') do set "_pid=%%a"
if not defined _pid goto cleanup_done
"%SystemRoot%\System32\taskkill.exe" /F /T /PID %_pid% >nul 2>&1
set /a _tries+=1
if %_tries% GEQ 10 goto cleanup_done
timeout /t 1 /nobreak >nul
goto cleanup_loop
:cleanup_done
echo ==^> Encerrado.
endlocal
