"""Confere a caminhada de caixa (replay) contra o MOTOR com capital real R$250 (capital minimo WIN, regra do CLAUDE.md).
Uso: python -u confere_motor_real.py IS|OOS  -- roda a celula CONGELADA (ou a canonica na IS) em P0/P1/P2."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import comum as c  # noqa: E402
from backtest.intraday.report import cabecalho, linha, num_br  # noqa: E402
import dataclasses  # noqa: E402


def main() -> None:
    janela_nome = sys.argv[1] if len(sys.argv) > 1 else "IS"
    params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else dict(desloc_min_atr=0.3, stop_atr=None, alvo_atr=None)
    ini, fim = (c.IS_INI, c.IS_FIM) if janela_nome == "IS" else (c.OOS_INI, c.OOS_FIM)
    df = c.carregar("WIN@")
    sel, dias = c.janela(df, ini, fim)
    print(f"MOTOR com capital REAL R${c.CAPITAL['WIN@']:.0f} | {janela_nome} {ini.date()}..{fim.date()} | {c.nome_celula(params)}", flush=True)
    print(cabecalho(("premissa", "sinais", "recusadas$", "caixa_min")), flush=True)
    for prem in ("P0", "P1", "P2"):
        r = c.rodar("WIN@", sel, dias, params, prem, rotulo=f"{c.nome_celula(params)}")
        ex = {"premissa": prem, "sinais": str(len(r["sinais"])), "recusadas$": str(r["res"].ordens_recusadas_por_capital),
              "caixa_min": num_br(r["caixa_min"], 2)}
        print(linha(dataclasses.replace(r["item"], extras=ex), extras=tuple(ex), largura_extra=12), flush=True)
        st = c.estatisticas(r["trades"])
        print(f"    trades={st['n']} liquido={st['liquido']:.1f} recusadas_por_capital={r['res'].ordens_recusadas_por_capital} "
              f"puladas={len(r['res'].sessoes_puladas_por_capital)} zerado={r['res'].wiped_out_at}", flush=True)


if __name__ == "__main__":
    main()
