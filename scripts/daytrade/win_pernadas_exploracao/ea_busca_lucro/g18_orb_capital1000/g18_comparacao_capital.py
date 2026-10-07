# -*- coding: utf-8 -*-
"""Geracao 18 -- comparacao EXPLICITA (item 2 do mandato): a MESMA geometria
vencedora original da G8/G13 (`stop_max_pontos=140`, `alvo_multiplo=3.0`,
`range_minutos=5`, `buffer_entrada_pontos=20`, classe ORIGINAL
`WinBuscaLucroG08OrbSobrevivencia`, import direto, SEM alteracao) rodada a
R$250 contra R$1.000 (so' o `cash_brl`/`initial_capital` do `config_for`
muda -- nenhum comportamento de codigo muda com o capital).

Pergunta (mesma da G17, agora sobre o ORB): o capital maior SOZINHO (sem
mexer na geometria) ja' resolve a ruina que G8/G13 mediram a R$250 (penhasco
isolado, 140 sobrevive, 150+ colapsa em censura total)?

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g18_orb_capital1000/g18_comparacao_capital.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g18_base as b  # noqa: E402

KW_G8_ORIGINAL = dict(
    range_minutos=5.0, stop_min_pontos=50.0, stop_max_pontos=140.0,
    alvo_multiplo=3.0, buffer_entrada_pontos=20.0,
)


def main() -> None:
    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 120)
    print("G18 -- MESMA geometria vencedora da G8/G13 (stop_max=140/alvo=3x/buffer=20), capital R$250 x R$1.000")
    print("=" * 120)

    for capital in (b.CAPITAL_ORIGINAL, b.CAPITAL):
        res, strat = b.roda_g08_original(dias, capital=capital, **KW_G8_ORIGINAL)
        trades = list(res.trades)
        c = b.consistencia(trades, dias)
        censura = b.censura_separada(res, c)
        ru = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias), caixa=capital)
        pior_seq_n, pior_seq_brl = b.maior_sequencia_perdas(trades)
        top5 = b.concentracao_topn(c["serie"], 5)
        print(f"\n-- capital=R${b.br(capital,0)} --")
        print(f"  trades={c['n']}  liquido={b.br(c['liquido'])}  win={b.br(100*c['win'],1) if c['n'] else '--'}%  "
              f"veredito={c['veredito']}  equity_min={b.br(censura['equity_min'])}  "
              f"ordens_recusadas_por_capital={censura['ordens_recusadas_por_capital']}  "
              f"censura_capital={censura['censura_capital']}")
        print(f"  pregoes_c_trade={c['com_trade']}/{c['pregoes']}  "
              f"top3/liq={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--'}%  "
              f"top5/liq={b.br(100*top5,0) if top5==top5 else '--'}%")
        print(f"  pior_seq={pior_seq_n} (R${b.br(pior_seq_brl)})  "
              f"p_ruina(MC, caixa=R${b.br(capital,0)}, piso=R${b.br(b.MARGEM_WIN_BRL,0)}, "
              f"n_ops={ru['n_ops']})={b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--'}%  "
              f"ruina_formula(Lundberg)={b.br(100*ru['ruina_formula'],1) if ru['ruina_formula']==ru['ruina_formula'] else '--'}%  "
              f"t_mediano_ate_quebrar={ru['t_mediano']}")

    print("\nFIM.")


if __name__ == "__main__":
    main()
