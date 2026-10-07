# -*- coding: utf-8 -*-
"""Geracao 15 -- sensibilidade extra (nao um dos 4 passos do protocolo
principal): confirma que a queda de p_ruina do orcamento UNICO e' um
GRADIENTE DE CENSURA (orcamento menor = exaure mais cedo = mais dias
"silenciados" no fim da janela = p_ruina medido sobre uma SUBAMOSTRA inicial,
nao sobre o periodo inteiro), nao uma melhora real de mecanismo. Varre
orcamento_valor de 120 a 240 (perto do n ilimitado=244) e reporta,
para cada um, se a janela fica censurada e quando o orcamento se esgota.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g15_portfolio_orcamento/g15_sensibilidade_censura.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g15_base as b  # noqa: E402

HORIZONTE_PREGOES = 44


def main() -> None:
    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print(f"Sensibilidade orcamento UNICO x p_ruina x censura (IS, {len(dias)} pregoes)\n")
    print(f"{'orcamento':>10}{'trades':>8}{'sem_trade':>11}{'ultimo_trade':>16}{'censurado':>11}{'p_ruina':>9}{'liquido':>12}")
    for valor in (121, 150, 180, 210, 230, 244):
        res, strat = b.roda_portfolio(
            dias, orcamento_modo="unico", orcamento_valor=valor, politica_prioridade="fifo",
            **b.KWARGS_GEOMETRIA)
        eqmin = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
        r = b.resumo(f"unico={valor}", list(res.trades), dias, horizonte_pregoes=HORIZONTE_PREGOES)
        c = r["c"]
        cens = b.censurado(c, eqmin)
        ultimo = max((t.exit_ts for t in res.trades), default=None)
        p_ru = r["ruina"]["p_ruina"]
        print(f"{valor:>10}{c['n']:>8}{str(c['sem_trade'])+'/'+str(c['pregoes']):>11}"
              f"{str(ultimo.date()) if ultimo is not None else '--':>16}{str(cens):>11}"
              f"{b.br(100*p_ru,1):>8}%{b.br(c['liquido']):>12}", flush=True)
    print("\nFIM.")


if __name__ == "__main__":
    main()
