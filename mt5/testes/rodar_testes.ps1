# Roda a bateria de testes do WinMaestro no Testador do MT5 (Rico), um por vez.
#
# PRE-REQUISITO: o MT5 da Rico FECHADO (com ele aberto o /config so' traz a
# janela para a frente e nao testa nada). Fechar o MT5 derruba os robos Python
# que falam com ele -- feche fora do pregao / sem posicao aberta.
#
# Uso (na raiz do repo):
#   .\.venv\Scripts\python.exe mt5\testes\gera_ini.py
#   powershell -ExecutionPolicy Bypass -File mt5\testes\rodar_testes.ps1            # todos
#   powershell -ExecutionPolicy Bypass -File mt5\testes\rodar_testes.ps1 M_GB A_GB  # so' alguns
#   .\.venv\Scripts\python.exe mt5\testes\compara.py
#
# Cada teste: terminal64 /config:<ini> -> testa -> salva o relatorio em
# <pasta de dados>\testes_maestro\<nome>.htm -> fecha sozinho (ShutdownTerminal=1).
# Os relatorios e o log do agente sao copiados para mt5\testes\resultados\.
# No fim o MT5 e' aberto de novo, sem config.

param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Testes)

$ErrorActionPreference = "Stop"
$Terminal = "C:\Program Files\Rico - MetaTrader 5\terminal64.exe"
$Dados    = Join-Path $env:APPDATA "MetaQuotes\Terminal\38FF261A42172F3478E54D3A1A8FE02B"
$Agentes  = Join-Path $env:APPDATA "MetaQuotes\Tester\38FF261A42172F3478E54D3A1A8FE02B"
$Aqui     = Split-Path -Parent $MyInvocation.MyCommand.Path
$Ini      = Join-Path $Aqui "ini"
$Saida    = Join-Path $Aqui "resultados"
$LimiteMin = 90   # um teste que passa disso e' considerado travado

if (Get-Process terminal64 -ErrorAction SilentlyContinue) {
    Write-Host "O MT5 esta' aberto. Feche o terminal (sem posicao aberta) e rode de novo." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $Ini)) { Write-Host "Rode antes: python mt5\testes\gera_ini.py" -ForegroundColor Red; exit 1 }
New-Item -ItemType Directory -Force $Saida | Out-Null
# O Testador NAO cria a subpasta do Report: sem ela o teste roda e o relatorio some sem aviso.
New-Item -ItemType Directory -Force (Join-Path $Dados "testes_maestro") | Out-Null

$ordem = "M_GB","M_CM","M_DM","M_RE","M_C1","M_TODOS","A_GB","A_CM","A_DM","A_RE","A_C1"
if ($Testes) { $ordem = $Testes }
$inicio = Get-Date

foreach ($nome in $ordem) {
    $cfg = Join-Path $Ini "$nome.ini"
    if (-not (Test-Path $cfg)) { Write-Host "$nome : ini nao existe, pulando" -ForegroundColor Yellow; continue }
    $t0 = Get-Date
    Write-Host ("{0:HH:mm:ss} {1} ..." -f $t0, $nome) -NoNewline
    $p = Start-Process -FilePath $Terminal -ArgumentList "/config:`"$cfg`"" -PassThru
    if (-not $p.WaitForExit($LimiteMin * 60 * 1000)) {
        Stop-Process -Id $p.Id -Force
        Write-Host " TRAVOU (> $LimiteMin min), terminal encerrado" -ForegroundColor Red
        continue
    }
    $rel = Get-ChildItem -Path (Join-Path $Dados "testes_maestro"), (Join-Path (Split-Path $Terminal) "testes_maestro") `
             -Filter "$nome.htm*" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($rel -and $rel.LastWriteTime -ge $t0) {
        Copy-Item $rel.FullName (Join-Path $Saida "$nome.htm") -Force
        Write-Host (" ok ({0:N1} min)" -f ((Get-Date) - $t0).TotalMinutes) -ForegroundColor Green
    } else {
        Write-Host " SEM RELATORIO novo (ver log do agente)" -ForegroundColor Red
    }
}

# Logs do agente do Testador (o Diario de cada teste) e do terminal, do periodo da bateria.
Get-ChildItem $Agentes -Directory -Filter "Agent-*" | ForEach-Object {
    Get-ChildItem (Join-Path $_.FullName "logs") -Filter *.log -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -ge $inicio } |
        ForEach-Object { Copy-Item $_.FullName (Join-Path $Saida ("agente_" + $_.Directory.Parent.Name + "_" + $_.Name)) -Force }
}
Get-ChildItem (Join-Path $Dados "Tester\logs") -Filter *.log -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -ge $inicio } |
    ForEach-Object { Copy-Item $_.FullName (Join-Path $Saida ("tester_" + $_.Name)) -Force }

Write-Host "Reabrindo o MT5..."
Start-Process -FilePath $Terminal
Write-Host "Fim. Relatorios em $Saida -- rode: python mt5\testes\compara.py"
