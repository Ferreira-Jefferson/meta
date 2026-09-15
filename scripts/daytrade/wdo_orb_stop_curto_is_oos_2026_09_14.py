"""TESTE (2026-09-14) -- stop mais curto, a hipotese que o MAE levantou.

## De onde veio

`wdo_orb_perfil_operacao_2026_09_14.py` mediu, por operacao, o quanto ela
chega a ficar CONTRA antes de fechar (MAE). A separacao e' a maior de todo o
estudo e aparece nas tres janelas:

    janela        vencedora   perdedora
    IS              -8,0        -27,0
    OOS_LIMPO       -5,5        -20,5
    DESCOBERTA     -12,0        -25,0

O stop de producao e' 30 ticks (teto) e a vencedora tipica usa 8. Os 22 ticks
restantes parecem existir so' para a perdedora sangrar mais.

## Por que isso NAO e' obvio, e o numero que impede a conclusao facil

Medido sobre IS+OOS, cortar no MAE mata vencedora junto:

    stop 12t -> mata 24,2% das vencedoras | pega 97,2% das perdedoras mais cedo
    stop 15t -> mata 18,9%                | pega 93,1%
    stop 20t -> mata  9,5%                | pega 83,3%
    stop 25t -> mata  2,1%                | pega 48,6%

E "pegar mais cedo" reduz o TAMANHO da perda, nunca a converte em ganho. Se o
saldo compensa, so' o motor responde -- contar MAE na planilha nao basta,
porque um stop mais curto muda TODA a sequencia do pregao (a posicao fecha
antes, o fade e' liberado antes, o proximo rompimento acontece com outro
caixa).

## O acoplamento que a grade tem de respeitar

A geometria do robo e' `stop = clamp(tamanho da faixa, stop_min, stop_max)` e
`alvo = alvo_multiplo x stop`. Mexer no stop mexe no alvo junto -- nao ha'
como isolar um do outro sem sair do desenho da estrategia. Entao a grade
varia o PAR (min, max) com o multiplo fixo em 2,0 (producao), e a leitura e'
sempre "esta geometria inteira", nunca "o efeito do stop isolado".

Para o stop cair abaixo de 20 e' preciso baixar `stop_min_ticks` junto: com
`min=20, max=12`, `clamp` devolve 20 sempre e a celula seria um EIXO MORTO
disfarcado (o detector no fim do script pega isso).

    (20,30)  producao hoje
    (20,25)
    (20,20)  stop fixo em 20
    (15,15)  stop fixo em 15
    (12,12)  stop fixo em 12
    (10,10)  stop fixo em 10  -> alvo 20 ticks, longe da proibicao do T1

## Metodo

Identico ao da varredura de alvo: tres janelas (IS 72, OOS_LIMPO 43,
DESCOBERTA 19), capital R$375 REPOSTO por pregao, um processo por pregao
rodando as 6 celulas do mesmo dia. Decide por consistencia (pregoes e semanas
positivos, desvio, concentracao), nao por liquido -- criterio do dono.

Uso: `python -u scripts/daytrade/wdo_orb_stop_curto_is_oos_2026_09_14.py`
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from wdo_orb_4semanas_coleta_2026_09_14 import (  # noqa: E402
    CAPITAL_PARTIDA_BRL, TICK_SIZE, WdoOrbInstrumentado, carregar_bars,
    excursao, monta_config,
)
from wdo_orb_fade_agitacao_is_oos_2026_09_14 import (  # noqa: E402
    JANELAS, classifica_saida, pregoes_da_janela,
)
from wdo_orb_geometria_is_oos_2026_09_14 import resumo_celula  # noqa: E402

CELULAS = [
    ("S20-30", dict(stop_min_ticks=20, stop_max_ticks=30)),   # producao
    ("S20-25", dict(stop_min_ticks=20, stop_max_ticks=25)),
    ("S20fix", dict(stop_min_ticks=20, stop_max_ticks=20)),
    ("S15fix", dict(stop_min_ticks=15, stop_max_ticks=15)),
    ("S12fix", dict(stop_min_ticks=12, stop_max_ticks=12)),
    ("S10fix", dict(stop_min_ticks=10, stop_max_ticks=10)),
]
PRODUCAO = "S20-30"
SAIDA = RAIZ / "scratch" / "wdo_orb_4semanas_2026_09_14"
MAX_WORKERS = min(12, (os.cpu_count() or 4))


def roda_pregao_todas_celulas(dia: str) -> list[dict]:
    bars = carregar_bars(dia, dia)
    if bars.empty:
        return []
    linhas = []
    for nome, kwargs in CELULAS:
        strat = WdoOrbInstrumentado(**kwargs)
        cfg = monta_config(strat, CAPITAL_PARTIDA_BRL)
        res = run_intraday_backtest(bars, strat, cfg)
        ordens = sorted(strat._log_ordens, key=lambda o: o["sinal_ts"])
        for i, t in enumerate(sorted(res.trades, key=lambda x: x.entry_ts)):
            ordem = None
            for o in ordens:
                if o["sinal_ts"] <= t.entry_ts:
                    ordem = o
                else:
                    break
            pnl_ticks = (((t.exit_price - t.entry_price) if t.side == "long"
                          else (t.entry_price - t.exit_price)) / TICK_SIZE)
            razao = (t.exit_reason.value if hasattr(t.exit_reason, "value")
                     else str(t.exit_reason))
            alvo = ordem["alvo_ticks"] if ordem else float("nan")
            exc = excursao(bars, t.entry_ts, t.exit_ts, t.entry_price, t.side)
            linhas.append({
                "celula": nome, "data": dia, "op_do_dia": i + 1,
                "tipo": ordem["tipo"] if ordem else "?", "side": t.side,
                "pnl_brl": round(t.pnl_brl, 2), "pnl_ticks": round(pnl_ticks, 1),
                "alvo_ticks": alvo,
                "stop_ticks": ordem["stop_ticks"] if ordem else float("nan"),
                "saida_efetiva": classifica_saida(razao, pnl_ticks, alvo),
                "mfe_ticks": round(exc["mfe_ticks"], 1),
                "mae_ticks": round(exc["mae_ticks"], 1),
            })
    return linhas


def main() -> None:
    dias_por_janela, todos = {}, []
    for rotulo, ini, fim, _ in JANELAS:
        dias = pregoes_da_janela(ini, fim)
        dias_por_janela[rotulo] = set(dias)
        todos.extend(dias)
        print(f"[janela] {rotulo}: {len(dias)} pregoes", flush=True)
    print(f"\n[stop] {len(todos)} pregoes x {len(CELULAS)} celulas, "
          f"{MAX_WORKERS} processos, capital R${CAPITAL_PARTIDA_BRL:.0f} reposto\n",
          flush=True)

    linhas, feitos = [], 0
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {pool.submit(roda_pregao_todas_celulas, d): d for d in todos}
        for fut in as_completed(futuros):
            feitos += 1
            try:
                linhas.extend(fut.result())
            except Exception as exc:
                print(f"[{futuros[fut]}] ERRO: {exc!r}", flush=True)
            if feitos % 25 == 0:
                print(f"  ... {feitos}/{len(todos)}", flush=True)

    df = pd.DataFrame(linhas)
    df["janela"] = df["data"].map(
        lambda d: next(r for r, s in dias_por_janela.items() if d in s))
    df.to_csv(SAIDA / "70_stop_curto_trades.csv", index=False, encoding="utf-8")
    print(f"\n[stop] {len(df)} operacoes -> 70_stop_curto_trades.csv")

    tabelas = []
    for rotulo, _, _, papel in JANELAS:
        n_pregoes = len(dias_por_janela[rotulo])
        print("\n" + "=" * 132)
        print(f"JANELA {rotulo}  ({n_pregoes} pregoes, {papel})")
        print("=" * 132)
        tab = pd.DataFrame([{"celula": nome,
                             **resumo_celula(df[(df.janela == rotulo) & (df.celula == nome)],
                                             n_pregoes)}
                            for nome, _ in CELULAS])
        print(tab.to_string(index=False))
        tab.insert(0, "janela", rotulo)
        tabelas.append(tab)

        assin = {}
        for nome, _ in CELULAS:
            ops = df[(df.janela == rotulo) & (df.celula == nome)]
            assin[nome] = (len(ops), round(ops["pnl_brl"].sum(), 2))
        repetidos = [k for k, v in assin.items() if list(assin.values()).count(v) > 1]
        if repetidos:
            print(f"  [EIXO MORTO] celulas identicas: {repetidos} -- "
                  f"comparar entre elas nao significa nada")

    pd.concat(tabelas).to_csv(SAIDA / "71_stop_curto_resumo.csv",
                               index=False, encoding="utf-8")

    print("\n" + "=" * 132)
    print(f"LEITURA CRUZADA -- producao e' {PRODUCAO}; so' vale trocar o que "
          f"melhora nas DUAS janelas independentes")
    print("=" * 132)
    todas = pd.concat(tabelas)
    for metrica in ["rs_por_op", "pregoes_pos_pct", "desvio_op", "win_pct"]:
        piv = todas.pivot(index="celula", columns="janela", values=metrica)
        piv = piv.reindex([c for c, _ in CELULAS])[["IS", "OOS_LIMPO", "DESCOBERTA"]]
        print(f"\n--- {metrica} ---")
        print(piv.to_string())
    todas.to_csv(SAIDA / "72_stop_curto_cruzada.csv", index=False, encoding="utf-8")
    print(f"\n[stop] arquivos em {SAIDA}")


if __name__ == "__main__":
    main()
