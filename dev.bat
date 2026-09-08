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

REM 5) dashboard -- via scripts/dev_server.py, que faz a limpeza no `finally`
echo ==^> Dashboard META em http://127.0.0.1:8000 ^(Ctrl+C para parar^)
echo ==^> Hot-reload ativo: edicoes em src/ recarregam automaticamente

REM A limpeza (matar robos com --kill-robots, e liberar a porta 8000) NAO mora
REM mais aqui. Ctrl+C num .bat faz o cmd perguntar "Deseja finalizar o arquivo
REM em lotes (S/N)?", e responder S mata o script NESTE ponto -- nenhuma linha
REM abaixo roda. Como "S" e' o que qualquer um responde, a flag --kill-robots
REM quase nunca disparava (queixa do dono, 2026-09-08: tres robos sobreviveram
REM ao Ctrl+C com a flag passada). Quem limpa agora e' scripts/dev_server.py,
REM que tem `finally` de Python e roda mesmo no Ctrl+C -- a semantica da flag
REM nao mudou, so' mudou quem executa. Ver a docstring dele.
if "%KILL_ROBOTS%"=="1" (
    "%PY%" scripts\dev_server.py --kill-robots
) else (
    "%PY%" scripts\dev_server.py
)

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
