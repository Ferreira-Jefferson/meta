"""Sobe o uvicorn do dashboard e GARANTE a limpeza quando ele termina.

Por que este arquivo existe (2026-09-08, queixa do dono: "tem um problema no
kill, pq eu usei a flag").

`dev.bat` tinha a limpeza escrita DEPOIS da linha do uvicorn -- tanto o
`--kill-robots` quanto a liberacao da porta 8000. Em batch do Windows isso
nao roda de forma confiavel: Ctrl+C num `.bat` faz o cmd perguntar "Deseja
finalizar o arquivo em lotes (S/N)?", e responder **S mata o script naquele
ponto**, sem executar mais nenhuma linha. Como "S" e' o que qualquer um
responde (o proposito de apertar Ctrl+C era justamente encerrar), a flag
`--kill-robots` na pratica quase nunca disparava.

Medido no dia: o dono rodou `dev.bat --kill-robots`, deu Ctrl+C, respondeu
"S", e os tres robos (`dt-wdo_grid_reload_maker-wdo@-live`, o gemeo sombra e
`dt-copa_win-win@-shadow`) continuaram vivos com o PID de 15:55 -- rodando
codigo de antes dos commits do dia. A saida colada por ele nao tinha nem a
linha "==> --kill-robots: encerrando..." nem "==> Encerrado.", que e' a prova
de que o batch morreu antes de chegar nelas.

A correcao NAO muda a semantica da flag: a limpeza continua acontecendo
quando o uvicorn termina, nunca antes. O que muda e' quem executa. Um
processo Python tem `finally`, e `finally` roda no Ctrl+C -- batch nao tem
nada equivalente. O prompt do cmd continua aparecendo e continua matando o
`dev.bat`, mas a essa altura ESTE processo ja fez a limpeza, entao a resposta
do dono ao prompt deixou de importar.

Sobre matar os robos ao INICIAR em vez de ao encerrar: seria mais simples e
sempre funcionaria, mas muda o contrato documentado da flag e, num dia de
operacao real, derrubaria um robo com posicao aberta no instante em que
alguem sobe o dashboard. Ficou de fora de proposito.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

#: Segundos que esperamos o uvicorn sair sozinho depois do Ctrl+C antes de
#: matar no braco. Ele fecha em menos de 1s no caso normal (ver o
#: "Application shutdown complete" no log); a folga aqui e' para o caso de
#: uma requisicao em voo -- um backtest longo roda em thread do
#: `dashboard/app.py` e pode segurar o shutdown.
ESPERA_SAIDA_LIMPA_S = 20

#: Tentativas de liberar a porta 8000. Uvicorn `--reload` sobe master +
#: filho, e os dois se agarram ao socket: quando o master morre o filho
#: herda, entao `netstat` passa a reportar OUTRO dono e e' preciso matar de
#: novo. Mesmo motivo do loop que existia no `dev.bat`.
MAX_TENTATIVAS_PORTA = 10

# Casa pela LINHA DE COMANDO, nao pelo nome do processo: "python.exe"
# pegaria qualquer python do dono, inclusive este mesmo. Mata rastreado E
# orfao -- o bug de double-Popen documentado em
# `dashboard/live_control.py::start()` deixa duplicados que nem aparecem em
# `db/live_process.json`.
_PS_MATA_ROBOS = (
    "Get-CimInstance Win32_Process "
    "| Where-Object { $_.CommandLine -match 'run_live\\.py' } "
    "| ForEach-Object { Write-Host ('  matando PID ' + $_.ProcessId); "
    "Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
)


def _powershell(comando: str) -> None:
    """Roda um comando PowerShell sem deixar erro dele derrubar a limpeza.

    Tudo aqui e' best-effort de encerramento: se o `netstat` nao achar nada
    ou o processo ja tiver morrido, isso e' sucesso, nao falha."""
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", comando],
                       check=False)
    except OSError as erro:  # PowerShell fora do PATH -- nao vale abortar
        print(f"  (limpeza pulada: {erro})", flush=True)


def mata_robos() -> None:
    print("==> --kill-robots: encerrando processos run_live.py "
          "(rastreados e orfaos)...", flush=True)
    _powershell(_PS_MATA_ROBOS)


def dono_da_porta_em(saida_netstat: str, porta: int) -> str | None:
    """PID que escuta `porta` em 127.0.0.1, lido de uma saida de `netstat -ano`.

    Separada da chamada ao `netstat` para poder ser testada: em batch isto era
    um `for /f "tokens=5"` que ninguem conseguia exercitar. O PID e' a ULTIMA
    coluna da linha (`Proto  Local  Foreign  State  PID`), e o filtro por
    `127.0.0.1:` de proposito -- o dashboard so' sobe em loopback, e casar
    `:8000` solto pegaria porta de outra interface ou um endereco remoto."""
    alvo = f"127.0.0.1:{porta}"
    for linha in saida_netstat.splitlines():
        partes = linha.split()
        if len(partes) >= 5 and "LISTENING" in partes and alvo in partes:
            return partes[-1]
    return None


def _dono_da_porta(porta: int) -> str | None:
    saida = subprocess.run(
        ["netstat", "-ano"], check=False, capture_output=True, text=True).stdout
    return dono_da_porta_em(saida, porta)


def libera_porta(porta: int = 8000) -> None:
    """Mata quem ficou segurando a porta, em loop -- ver `MAX_TENTATIVAS_PORTA`."""
    for _ in range(MAX_TENTATIVAS_PORTA):
        pid = _dono_da_porta(porta)
        if pid is None:
            return
        subprocess.run(["taskkill", "/F", "/T", "/PID", pid],
                       check=False, capture_output=True)
        time.sleep(1)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--kill-robots", action="store_true")
    args = parser.parse_args()

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "--app-dir", "src",
         "dashboard.app:app", "--reload", "--host", "127.0.0.1",
         "--port", "8000"],
        cwd=RAIZ,
    )
    try:
        try:
            proc.wait()
        except KeyboardInterrupt:
            # O console ja entregou o Ctrl+C ao uvicorn tambem (ele esta no
            # mesmo grupo). Aqui so' damos tempo pra ele fechar sozinho, que
            # e' o que faz o "Application shutdown complete" aparecer.
            try:
                proc.wait(timeout=ESPERA_SAIDA_LIMPA_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    finally:
        # Este `finally` e' o ponto INTEIRO do arquivo -- ver o modulo.
        if args.kill_robots:
            mata_robos()
        libera_porta()
        print("==> Encerrado.", flush=True)
    return proc.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
