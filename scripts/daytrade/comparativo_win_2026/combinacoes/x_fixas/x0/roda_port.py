"""Roda UM port do comparativo com `dados` trocado pelo shim dados_val (nenhum port e' editado).
Uso: python roda_port.py <Win|Win_c1|WinCincoMedias|WinDeslocamentoMatinal|WinRetanguloEma34>
     (DADOS_VAL_MODO=2026 PROVA_INI=2026-01-01 PROVA_FIM=2026-10-05 -> prova de reproducao em 2026, saida em prova_2026/)
O port roda pelo proprio __main__ (runpy), entao a logica e' exatamente a do arquivo original."""
import runpy, sys
from pathlib import Path
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import dados_val
sys.modules["dados"] = dados_val
BASE = AQUI.parents[2]                      # comparativo_win_2026
sys.path.insert(0, str(BASE))
robo = sys.argv[1]
ini, fim = dados_val.INICIO.isoformat(), dados_val.FIM.isoformat()
ARQ = {"Win": "port_win.py", "Win_c1": "port_win.py", "WinCincoMedias": "port_cinco_medias.py",
       "WinDeslocamentoMatinal": "port_deslocamento.py", "WinRetanguloEma34": "port_retangulo_ema34.py"}
sys.argv = [ARQ[robo]]
if robo.startswith("Win") and ARQ[robo] == "port_win.py":
    sys.argv += ["--inicio", ini, "--fim", fim, "--so", robo]
print(f"[{robo}] modo={dados_val.MODO} {ini}..{fim} dias={len(dados_val.dias())}", flush=True)
if robo == "WinRetanguloEma34" and dados_val.MODO != "2026":
    # X0: sem parar por saldo (pedido do dono). O port para quando o equity <= LIMITE_EQUITY (0.0); em 2022-06 isso
    # aconteceria. Troca so' essa constante, em memoria, sem editar o arquivo do port. Em modo 2026 (prova) nao troca.
    src = (BASE / ARQ[robo]).read_text(encoding="utf-8")
    assert "LIMITE_EQUITY = 0.0" in src
    g = {"__name__": "__main__", "__file__": str(BASE / ARQ[robo])}
    exec(compile(src.replace("LIMITE_EQUITY = 0.0", "LIMITE_EQUITY = -1e18"), str(BASE / ARQ[robo]), "exec"), g)
else:
    runpy.run_path(str(BASE / ARQ[robo]), run_name="__main__")
