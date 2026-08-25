@echo off
REM Sobe o dashboard META em modo dev, auto-bootstrap.
REM Uso (PowerShell ou cmd): .\dev.bat [--kill-robots] [--help]
REM
REM O que faz sozinho, na ordem, sempre idempotente:
REM   1. Cria .venv se faltar (usa `python` do sistema)
REM   2. Sincroniza requirements.txt so quando o hash muda
REM   3. Inicializa db/journal.sqlite se ausente
REM   4. Baixa historico de mercado se data/raw/ vazio
REM   5. Sobe uvicorn com hot-reload em http://127.0.0.1:8000
REM   Ctrl+C encerra uvicorn e todos os workers do reloader
REM
REM --kill-robots: flag OPT-IN. Por padrao, os robos (`run_live.py loop` dos
REM slots de swing/day trade) sao processos INDEPENDENTES do dashboard --
REM `dashboard/live_control.py::start()` os sobe de proposito pra sobreviver
REM ao dashboard fechar, pra reiniciar o servidor de dev (o que acontece toda
REM hora, editando codigo) nao parar uma operacao real/sombra em andamento.
REM So passe esta flag quando VOCE quer matar os robos tambem ao encerrar --
REM tipico de sessao de ajuste no proprio feed/robo, onde ficar reiniciando
REM manualmente (ou pedindo pra matar por fora) so' pra testar e' ruido.
REM
REM --help / -h / /?: so mostra este resumo e sai, sem bootstrap nenhum.

setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

if /i "%~1"=="--help" goto show_help
if /i "%~1"=="-h" goto show_help
if "%~1"=="/?" goto show_help

set "KILL_ROBOTS=0"
if /i "%~1"=="--kill-robots" set "KILL_ROBOTS=1"

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

REM --kill-robots: mata TODO processo run_live.py, rastreado ou orfao (o
REM bug de double-Popen documentado em live_control.py::start() deixa
REM duplicados que nao aparecem em db/live_process.json). Casa pela LINHA
REM DE COMANDO, nao pelo nome do processo -- "python.exe" pegaria qualquer
REM python do usuario, inclusive este shell/venv. So roda se a flag foi
REM passada (ver topo do arquivo): sem ela, robo sobrevive ao dashboard
REM fechar, que e' o comportamento padrao.
if "%KILL_ROBOTS%"=="1" (
    echo ==^> --kill-robots: encerrando processos run_live.py ^(rastreados e orfaos^)...
    powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'run_live\.py' } | ForEach-Object { Write-Host ('  matando PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
)

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
goto :eof

:show_help
echo Uso: .\dev.bat [--kill-robots] [--help]
echo.
echo Sobe o dashboard META em modo dev (auto-bootstrap: venv, deps, banco,
echo dados de mercado) e o uvicorn com hot-reload em http://127.0.0.1:8000.
echo Ctrl+C encerra o uvicorn e os workers do reloader.
echo.
echo   --kill-robots   Ao encerrar (Ctrl+C), tambem mata TODO processo
echo                    run_live.py (robos de swing/day trade), rastreado
echo                    ou orfao. Sem esta flag (padrao), os robos NAO sao
echo                    afetados -- eles sao processos independentes do
echo                    dashboard de proposito (ver live_control.py::start()),
echo                    pra reiniciar o servidor de dev nao parar uma
echo                    operacao real/sombra em andamento. So use esta flag
echo                    numa sessao de ajuste no proprio feed/robo, onde
echo                    voce QUER derrubar tudo junto pra testar de novo.
echo.
echo   --help, -h, /?  Mostra esta ajuda e sai.
endlocal
exit /b 0
