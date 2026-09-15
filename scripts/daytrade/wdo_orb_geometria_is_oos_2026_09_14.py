"""TESTE (2026-09-14) -- a GEOMETRIA do wdo_orb remedida no desenho de HOJE.

## A pergunta

Da coleta das 4 semanas: o alvo pedido e' em media **53 ticks**, o vencedor
anda **26 ticks** (MFE mediana) e o perdedor **11** antes de virar. So' 10,7%
das operacoes chegam ao alvo -- 46,4% saem pelo corte de relogio de 60 min,
com R$/op 8x menor que o alvo cheio (item 6.40 de LICOES_DE_PRODUCAO.md).

O dono declarou o criterio: *"melhor ganhar pouco e ganhar sempre do que
ganhar muito e devolver por mercado"*. Um alvo mais curto e' a traducao
direta disso -- mais operacoes fechando no alvo, ganho menor por operacao,
menos dependencia dos 3 alvos cheios que carregaram a janela inteira.

## Por que remedir algo ja' refutado

Geometria FIXA foi testada e REFUTADA de forma monotonica (docstring de
`WdoOrb`): S10/T20 deu +R$0,88/op e S20/T40 +R$2,34/op contra +R$15,71/op da
faixa adaptativa. Mas aquilo foi medido **em outro desenho de execucao**:
corte a MERCADO em vez de ordem-limite, SEM o fade do rompimento oposto, e
com a fila antiga (o motor enchia limite no primeiro toque). Os tres mudaram
desde entao. Remedir no desenho vigente nao e' repetir trabalho -- e' checar
se a refutacao sobreviveu a troca das premissas que a produziram.

As duas celulas `FIX_*` reproduzem exatamente as geometrias refutadas, para
que a comparacao seja direta.

## As celulas (7) -- eixo unico: o tamanho do ALVO

    T1.0    alvo = 1,0 x stop   (~27 ticks)
    T1.25   alvo = 1,25 x stop
    T1.5    alvo = 1,5 x stop
    T2.0    alvo = 2,0 x stop   <- PRODUCAO HOJE (~53 ticks)
    T2.5    alvo = 2,5 x stop
    FIX_S20_T40   stop 20 / alvo 40 ticks fixos  (refutada em outro desenho)
    FIX_S10_T20   stop 10 / alvo 20 ticks fixos  (idem)

Nenhuma celula chega perto de 1 tick de alvo -- a menor pede 20 ticks. A
proibicao do T1 (CLAUDE.md) esta respeitada com folga.

## Metodo

Tres janelas, capital R$375 REPOSTO por pregao (mesmo desenho do teste de
H1/H2 de hoje -- a caminhada continua censura e mede o portao de capital, nao
a geometria):

    IS           2026-02-27..2026-06-12   72 pregoes
    OOS_LIMPO    2026-06-15..2026-08-14   ~44 pregoes
    DESCOBERTA   2026-08-17..2026-09-11   19 pregoes

Um processo por PREGAO roda as 7 celulas do mesmo dia -- o tick daquele dia e'
lido UMA vez em vez de sete.

## O que decide (nao e' o liquido)

O criterio do dono e' consistencia. Cada celula reporta, alem de liquido e
R$/op:

  * **% de pregoes positivos** e **% de semanas positivas** -- a traducao
    direta de "ganhar sempre";
  * **win% ao lado do breakeven EMPIRICO** (`perda_media/(ganho_medio+
    perda_media)`) -- o nulo certo quando o payoff realizado foge do nominal
    (itens 6.22/6.23). `R$/op > 0` e `win% > BE` sao a MESMA afirmacao; se
    discordarem na tabela, o nulo esta' no lugar errado;
  * **desvio por operacao** -- "devolver por mercado" e' variancia;
  * **concentracao (top3%)** -- quanto do liquido vem das 3 melhores
    operacoes. Na producao de hoje, 3 de 28 operacoes valiam +R$688,50 de um
    liquido de -R$604,00;
  * `alvo_cheio` / `corte_relogio` / `stop` SEPARADOS (item 6.40) -- e' o
    numero que diz se o alvo mais curto esta' de fato sendo PAGO, em vez de
    so' mudar o rotulo da mesma saida;
  * **checagem de eixo morto**: alvo medio pedido e n de trades por celula. Se
    duas celulas devolverem os mesmos trades, o eixo nao mexeu em nada e a
    comparacao entre elas nao significa nada (CLAUDE.md).

Uso: `python -u scripts/daytrade/wdo_orb_geometria_is_oos_2026_09_14.py`
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

CELULAS = [
    ("T1.0", dict(alvo_multiplo=1.0)),
    ("T1.25", dict(alvo_multiplo=1.25)),
    ("T1.5", dict(alvo_multiplo=1.5)),
    ("T2.0", dict(alvo_multiplo=2.0)),          # producao
    ("T2.5", dict(alvo_multiplo=2.5)),
    ("FIX_S20_T40", dict(stop_ticks_fixo=20, alvo_ticks_fixo=40)),
    ("FIX_S10_T20", dict(stop_ticks_fixo=10, alvo_ticks_fixo=20)),
]
PRODUCAO = "T2.0"

SAIDA = RAIZ / "scratch" / "wdo_orb_4semanas_2026_09_14"
MAX_WORKERS = min(12, (os.cpu_count() or 4))


def roda_pregao_todas_celulas(dia: str) -> list[dict]:
    """UM pregao, as 7 celulas, caixa R$375 do zero em cada uma. O tick do dia
    e' lido uma vez so'."""
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
                "tipo": ordem["tipo"] if ordem else "?",
                "pnl_brl": round(t.pnl_brl, 2),
                "pnl_ticks": round(pnl_ticks, 1),
                "alvo_ticks": alvo,
                "stop_ticks": ordem["stop_ticks"] if ordem else float("nan"),
                "saida_efetiva": classifica_saida(razao, pnl_ticks, alvo),
                "mfe_ticks": round(exc["mfe_ticks"], 1),
                "mae_ticks": round(exc["mae_ticks"], 1),
            })
    return linhas


def resumo_celula(ops: pd.DataFrame, pregoes_janela: int) -> dict:
    if ops.empty:
        return {"n": 0}
    pnl = ops["pnl_brl"]
    g, p = pnl[pnl > 0], pnl[pnl <= 0]
    por_dia = ops.groupby("data")["pnl_brl"].sum()
    semana = pd.to_datetime(ops["data"]).dt.isocalendar()
    por_semana = ops.assign(sem=semana["week"].values).groupby("sem")["pnl_brl"].sum()
    saidas = ops["saida_efetiva"].value_counts()
    top3 = pnl.nlargest(3).sum()
    return {
        "n": len(ops),
        "liquido": round(pnl.sum(), 2),
        "rs_por_op": round(pnl.mean(), 2),
        "desvio_op": round(pnl.std(ddof=1), 2) if len(ops) > 1 else float("nan"),
        "win_pct": round(100.0 * len(g) / len(ops), 1),
        "be_emp": (round(100.0 * (-p.mean()) / (g.mean() - p.mean()), 1)
                   if len(g) and len(p) else float("nan")),
        "pregoes_pos_pct": round(100.0 * (por_dia > 0).sum() / len(por_dia), 1),
        "semanas_pos_pct": round(100.0 * (por_semana > 0).sum() / len(por_semana), 1),
        "top3_pct": round(100.0 * top3 / pnl.sum(), 1) if pnl.sum() != 0 else float("nan"),
        "alvo_medio": round(ops["alvo_ticks"].mean(), 1),
        "alvo_cheio": int(saidas.get("alvo_cheio", 0)),
        "corte_rel": int(saidas.get("corte_relogio", 0)),
        "stops": int(saidas.get("stop", 0)),
        "alvo_cheio_pct": round(100.0 * saidas.get("alvo_cheio", 0) / len(ops), 1),
        "sem_trade": pregoes_janela - ops["data"].nunique(),
    }


def main() -> None:
    dias_por_janela = {}
    todos_dias = []
    for rotulo, ini, fim, _ in JANELAS:
        dias = pregoes_da_janela(ini, fim)
        dias_por_janela[rotulo] = set(dias)
        todos_dias.extend(dias)
        print(f"[janela] {rotulo}: {len(dias)} pregoes ({dias[0]} .. {dias[-1]})", flush=True)
    print(f"\n[geometria] {len(todos_dias)} pregoes x {len(CELULAS)} celulas, "
          f"{MAX_WORKERS} processos, capital R${CAPITAL_PARTIDA_BRL:.0f} reposto\n",
          flush=True)

    linhas, feitos = [], 0
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {pool.submit(roda_pregao_todas_celulas, d): d for d in todos_dias}
        for fut in as_completed(futuros):
            dia = futuros[fut]
            feitos += 1
            try:
                linhas.extend(fut.result())
            except Exception as exc:
                print(f"[{dia}] ERRO: {exc!r}", flush=True)
            if feitos % 25 == 0:
                print(f"  ... {feitos}/{len(todos_dias)} pregoes", flush=True)

    df = pd.DataFrame(linhas)
    df["janela"] = df["data"].map(
        lambda d: next(r for r, s in dias_por_janela.items() if d in s))
    df.to_csv(SAIDA / "40_geometria_trades.csv", index=False, encoding="utf-8")
    print(f"\n[geometria] {len(df)} operacoes -> 40_geometria_trades.csv")

    tabelas = []
    for rotulo, _, _, papel in JANELAS:
        n_pregoes = len(dias_por_janela[rotulo])
        print("\n" + "=" * 132)
        print(f"JANELA {rotulo}  ({n_pregoes} pregoes, {papel})")
        print("=" * 132)
        linhas_tab = []
        for nome, _ in CELULAS:
            ops = df[(df.janela == rotulo) & (df.celula == nome)]
            linhas_tab.append({"celula": nome, **resumo_celula(ops, n_pregoes)})
        tab = pd.DataFrame(linhas_tab)
        print(tab.to_string(index=False))
        tab.insert(0, "janela", rotulo)
        tabelas.append(tab)

        # checagem de eixo morto
        assinaturas = {}
        for nome, _ in CELULAS:
            ops = df[(df.janela == rotulo) & (df.celula == nome)]
            assinaturas[nome] = (len(ops), round(ops["pnl_brl"].sum(), 2))
        iguais = [a for a in assinaturas.items()
                  if list(assinaturas.values()).count(a[1]) > 1]
        if iguais:
            print(f"  [EIXO MORTO] celulas com trades/liquido IDENTICOS: "
                  f"{[a[0] for a in iguais]} -- comparar entre elas nao significa nada")

    pd.concat(tabelas).to_csv(SAIDA / "41_geometria_resumo.csv",
                               index=False, encoding="utf-8")

    # --- leitura cruzada: a celula tem de sobreviver as DUAS independentes ---
    print("\n" + "=" * 132)
    print("LEITURA CRUZADA -- R$/op por celula nas tres janelas "
          "(a producao e' T2.0; so' vale trocar o que ganha nas DUAS independentes)")
    print("=" * 132)
    piv = pd.concat(tabelas).pivot(index="celula", columns="janela",
                                    values="rs_por_op")
    piv_cons = pd.concat(tabelas).pivot(index="celula", columns="janela",
                                         values="pregoes_pos_pct")
    juntos = piv.join(piv_cons, rsuffix="_pregoes_pos%")
    juntos = juntos.reindex([c for c, _ in CELULAS])
    print(juntos.to_string())
    juntos.to_csv(SAIDA / "42_geometria_cruzada.csv", encoding="utf-8")
    print(f"\n[geometria] arquivos em {SAIDA}")


if __name__ == "__main__":
    main()
