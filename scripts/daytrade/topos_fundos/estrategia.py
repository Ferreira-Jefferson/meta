"""Robô escada WIN M15 v4.1 (adotado em 2026-10-08). Monta tudo e roda IS, OOS e o período virgem.

  1. Escada: fundo confirmado acima do anterior (estágio >= 1), ZigZag 1,5 ATR no M15. Venda = espelho.
  2. Filtros a favor: H1 (MME 9/21/34), lado da abertura do dia, MMS17 > MMS34 (close), MMS72 do open subindo.
  3. Só sinais bons: Estocástico 14 < 70 a favor OU H4 neutro. 2 contratos.
  4. Entrada limitada no close da confirmação (3 barras, enche se passar 2 ticks).
  5. Stop no pivô, apertado até 0,2 ATR além da MME38; sobe a cada novo pivô; sem alvo; zera no fim do pregão.

Uso: python scripts/daytrade/topos_fundos/estrategia.py
"""
import pandas as pd
import dados
import escada
import filtros
import indicadores as ind
import operacao
import stop

FILTROS_V41 = (filtros.h1_a_favor, filtros.lado_da_abertura, filtros.mms17_acima_mms34,
               filtros.mms72_open_inclinada, filtros.sinal_bom)


def preparar(periodo):
    """Barras M15 com os indicadores que o stop usa, pregões e sinais da v4.1 (já filtrados)."""
    b = dados.m15(periodo)
    b["mme38"] = ind.mme(b.close, stop.MME_APERTO)
    dias = escada.pregoes(b)
    s = escada.sinais(dias)
    ok = pd.Series(True, index=s.index)
    for f in FILTROS_V41:
        ok &= f(b, s)
    return b, dias, s[ok].sort_values(["seg", "t0"]).reset_index(drop=True)


def rodar(periodo, inicial=stop.inicial_v41, mover=stop.estrutura):
    _, dias, s = preparar(periodo)
    return operacao.operar(s, dias, inicial, mover)


if __name__ == "__main__":
    linhas = {p: operacao.resumo(rodar(p)) for p in dados.PERIODOS}
    t = pd.DataFrame(linhas).T
    pd.set_option("display.width", 200)
    print("v4.1 (pts com 2 contratos, já com 10 pts de custo por contrato; R$ = pts x 0,20)")
    print(t.round(2).to_string())
