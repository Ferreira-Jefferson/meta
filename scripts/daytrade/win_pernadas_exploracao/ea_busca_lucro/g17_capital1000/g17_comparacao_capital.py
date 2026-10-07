# -*- coding: utf-8 -*-
"""Geracao 17 -- comparacao EXPLICITA (item 2 do mandato): a MESMA geometria
vencedora original da G4 (alvo=3x, stop=150, buffer=30, j20/q75/continuacao)
rodada a R$250 (classe ORIGINAL da G4, import direto, SEM alteracao) contra
R$1.000 (mesma classe -- a mudanca de capital por si so' nao muda nenhum
comportamento de codigo, so' o `cash_brl`/`initial_capital` do `config_for`).

Pergunta: o capital maior SOZINHO (sem mexer no alvo) ja' ajuda a ruina?

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g17_capital1000/g17_comparacao_capital.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g17_base as b  # noqa: E402

KW_G4_ORIGINAL = dict(
    direcao_aposta="continuacao", stop_pontos=150.0, alvo_multiplo=3.0,
    buffer_entrada_pontos=30.0,
)
JANELA_MIN, QUANTIL = 20, 0.75


def main() -> None:
    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 120)
    print("G17 -- MESMA geometria vencedora da G4 (alvo=3x/stop=150/buffer=30), capital R$250 x R$1.000")
    print("=" * 120)

    for capital in (b.CAPITAL_G4_ORIGINAL, b.CAPITAL):
        res, strat = b.roda_g04_original(dias, dias_historico=dias, janela_min=JANELA_MIN,
                                          quantil=QUANTIL, capital=capital, **KW_G4_ORIGINAL)
        trades = list(res.trades)
        c = b.consistencia(trades, dias)
        equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
        ru = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias), caixa=capital)
        pior_seq_n, pior_seq_brl = b.maior_sequencia_perdas(trades)
        print(f"\n-- capital=R${b.br(capital,0)} --")
        print(f"  trades={c['n']}  liquido={b.br(c['liquido'])}  win={b.br(100*c['win'],1)}%  "
              f"veredito={c['veredito']}  equity_min={b.br(equity_min)}  "
              f"ordens_recusadas_por_capital={res.ordens_recusadas_por_capital}")
        print(f"  pior_seq={pior_seq_n} (R${b.br(pior_seq_brl)})  "
              f"p_ruina(MC, caixa=R${b.br(capital,0)}, piso=R${b.br(b.MARGEM_WIN_BRL,0)}, "
              f"n_ops={ru['n_ops']})={b.br(100*ru['p_ruina'],1)}%  "
              f"ruina_formula(Lundberg)={b.br(100*ru['ruina_formula'],1)}%  "
              f"t_mediano_ate_quebrar={ru['t_mediano']}")

    print("\nFIM.")


if __name__ == "__main__":
    main()
