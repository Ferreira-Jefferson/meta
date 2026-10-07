# -*- coding: utf-8 -*-
"""Geracao 22 -- OOS-1 (jul-ago/2026, 44 pregoes), rodado UMA VEZ, candidato
CONGELADO (`win_busca_lucro_g22_retangulo_filtro_amplitude_congelado_v22.py`):
`WinBuscaLucroG21Retangulo1000` (stop=0,45xL/alvo=2,0x, capital R$1.000) +
filtro de PREGAO `amplitude_ontem > 2.558,3pts` (limiar CONGELADO no IS,
NAO recalculado aqui).

Protocolo: roda-se SO' esta vez, sem reajustar limiar nem geometria depois de
ver o resultado. Se passar "com folga" (concentracao melhor ou pelo menos
nao pior que a propria G21 sem filtro, E veredito nao pior), avanca para
OOS-2 (`g22_oos2.py`); senao, para aqui.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g22_proxy_dia/g22_oos1.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import g22_base as b  # noqa: E402


def main() -> None:
    win_full = b.carrega_win()
    dias_oos1 = b.dias_da_janela(win_full, b.CORTE_IS_FIM, b.CORTE_OOS1_FIM)
    print(f"Geracao 22 -- OOS-1 (jul-ago/2026, {len(dias_oos1)} pregoes), "
          f"candidato CONGELADO, limiar={b.br(2558.3)}pts (IS, nao reajustado)\n",
          flush=True)

    res, strat, dias_habilitados = b.roda_g22_filtrado(
        dias_oos1, win_full=win_full, congelado=True)
    trades = list(res.trades)
    c = b.consistencia(trades, dias_oos1)
    top5 = b.concentracao_topn(c["serie"], 5)
    cs = b.censura_separada(res, c)
    ru = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias_oos1))
    pior_n, pior_brl = b.maior_sequencia_perdas(trades)

    print(f"Dias habilitados pelo filtro: {len(dias_habilitados)}/{len(dias_oos1)}")
    print(f"liquido={b.br(c['liquido'])}  n={c['n']}  win={100*c['win']:.1f}%  "
          f"BEemp={100*c['be']:.1f}%  IC95=[{100*c['lo']:.1f};{100*c['hi']:.1f}]  "
          f"veredito={c['veredito']}  top3/liq={100*c['concentracao_top3']:.0f}%  "
          f"top5/liq={100*top5:.0f}%  p_ruina={100*ru['p_ruina']:.1f}%  "
          f"pior_seq={pior_n}(R${b.br(pior_brl)})  "
          f"sem_trade={c['sem_trade']}/{c['pregoes']}  "
          f"equity_min={b.br(cs['equity_min'])}  "
          f"recusadas_capital={cs['ordens_recusadas_por_capital']}  "
          f"censura_capital={cs['censura_capital']}")

    retorno_pct = 100.0 * c["liquido"] / b.CAPITAL
    meses = len(dias_oos1) / 22.0
    print(f"\nRetorno sobre a regua do dono (R$1.000): {retorno_pct:.1f}% no periodo "
          f"(~{retorno_pct/meses:.1f}%/mes medio, {meses:.1f} meses)")

    print("\n--- Comparacao contra a G21 sem filtro no MESMO OOS-1 (ja registrado em ORQUESTRACAO.md) ---")
    print("  G21 sem filtro: liquido=+650,00  n=98  win=39,8%  IC95=[30,7;49,7] indefinido  "
          "top3/liq=97,2%  top5/liq=133,4%  p_ruina=0,7%")
    print(f"  G22 com filtro: liquido={b.br(c['liquido'])}  n={c['n']}  win={100*c['win']:.1f}%  "
          f"IC95=[{100*c['lo']:.1f};{100*c['hi']:.1f}] {c['veredito']}  "
          f"top3/liq={100*c['concentracao_top3']:.0f}%  top5/liq={100*top5:.0f}%  "
          f"p_ruina={100*ru['p_ruina']:.1f}%")

    concentracao_melhorou = (c["concentracao_top3"] == c["concentracao_top3"]
                              and c["concentracao_top3"] < 0.972 and top5 < 1.334)
    passa_com_folga = (c["liquido"] > 0 and not cs["censura_capital"]
                        and c["veredito"] != "NEGATIVO" and concentracao_melhorou)
    print(f"\nConcentracao melhorou frente a G21 sem filtro? {'SIM' if concentracao_melhorou else 'NAO'}")
    print(f"Passa o OOS-1 'com folga' (protocolo desta geracao)? {'SIM -- avancar para OOS-2' if passa_com_folga else 'NAO -- parar aqui'}")


if __name__ == "__main__":
    main()
