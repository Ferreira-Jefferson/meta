"""WDO F1: a geometria tem vantagem, separada da ruina? -- 1 mes, caixa
REPOSTO a cada pregao, motor com fila calibrada.

POR QUE ESTA RODADA EXISTE
--------------------------
Todas as medicoes de geometria de 2026-09-09/10 morreram do mesmo jeito: com
capital real R$375 o robo quebra o piso de caixa no PRIMEIRO pregao e fica
mudo nos outros 71. A autopsia (extrato operacao a operacao, 4 primeiros
pregoes do IS) mostrou que NAO foi sequencia de stops -- o T2/S17 nunca teve
dois stops seguidos e mesmo assim foi de R$375 para R$111 num pregao so',
com 93 vitorias contra 14 derrotas. Foi desgaste: cada stop apaga 9 a 12
vitorias, e o robo ganha ~7 seguidas entre stops.

Com isso, a janela de 72 pregoes vira uma amostra de UM pregao repetida, e o
`liquido R$` dela mede o portao de capital. A pergunta "esta geometria tem
vantagem?" nunca foi respondida com o motor corrigido.

O DESENHO: CAIXA REPOSTO POR PREGAO
------------------------------------
Cada pregao roda ISOLADO, comecando nos mesmos R$375. Isso separa duas
perguntas que o backtest continuo mistura:

  * "esta geometria ganha dinheiro por operacao?"  <- e' esta que se responde aqui
  * "R$375 aguenta operar esta geometria?"         <- ja' respondida, e a resposta e' NAO

Repor o caixa nao e' fingir que a ruina nao existe: e' medir o numerador antes
de dividir pelo denominador. Uma geometria que nem por operacao ganha nao
merece a discussao de capital; uma que ganha vira uma pergunta de quanto
caixa, que e' outra conversa (e tem resposta: R$3.000 a R$8.000 para o risco
de 1% do proprio robo deixar de ser letra morta).

EFEITO COLATERAL DESEJADO: cada processo carrega UM pregao (~200 mil
negocios) em vez da janela inteira (14,5 milhoes). A bateria de 72 pregoes
estourou a RAM desta maquina e o SO comecou a paginar; aqui isso nao
acontece.

O QUE DECIDE, E O QUE NAO
--------------------------
NAO decide: `liquido R$` somado. Somar pregoes com caixa reposto e' somar
maçãs -- cada um partiu do mesmo lugar, entao a soma nao e' uma conta que
alguem possa ter.

DECIDE: **win% contra o breakeven, com intervalo de confianca**. O breakeven
e' aritmetica pura (ganho e perda sao fixos em ticks), e o win% com n de
milhares tem intervalo estreito. Se o IC 95% do win% ficar inteiro ABAIXO do
breakeven, a geometria e' negativa e nenhum capital conserta. Se ficar
inteiro ACIMA, ela tem vantagem e a conversa passa a ser de caixa. Se
atravessar, n nao chegou.

Secundario, mas util: `R$/operacao` e a fracao de pregoes positivos.

Fila: vem de `backtest.intraday.fidelidade` (WDO@ 438/489, Kaplan-Meier
sobre execucao real de 2026-09-09) -- nao se digita fila aqui.
Prazo: SEM PRAZO, que e' o default da classe desde 2026-09-09.
"""
from __future__ import annotations

import math
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"

SYMBOL = "WDO@"
CAPITAL_REAL_BRL = 375.0
CORRETAGEM_RT = 0.50
VALOR_TICK = 5.0

MAX_WORKERS = int(os.environ.get("WDOF1_WORKERS", "8"))

#: UM mes do IS (ordem do dono, 2026-09-10: "considere apenas 1 mes, acho
#: que e' suficiente para sabermos se estamos no caminho certo"). E' o
#: primeiro mes da janela congelada -- o OOS segue intocado.
INICIO = os.environ.get("WDOF1_INICIO", "2026-02-27")
FIM = os.environ.get("WDOF1_FIM", "2026-03-27")

ALVOS = tuple(int(x) for x in os.environ.get("WDOF1_ALVOS", "2").split(","))
STOPS = tuple(int(x) for x in os.environ.get("WDOF1_STOPS", "6,10,16,21").split(","))

#: 1% e' o de producao. O dono liberou ate' 5% em 2026-09-10 ("nao adianta
#: proteger o caixa so' para adiar sua morte"), mas a R$375 os dois dao o
#: MESMO 1 contrato: `caixa x pct / risco_por_contrato` da' zero nos dois
#: casos (R$3,75 e R$18,75 contra R$80 do stop de 16 ticks) e o piso
#: `max(1, ...)` assume. O percentual so' passa a existir a partir de
#: R$3.200 (5%) ou R$16.000 (1%). Fica como EIXO so' para a tabela provar
#: isso em vez de eu afirmar.
RISCOS = tuple(float(x) for x in os.environ.get("WDOF1_RISCOS", "0.01").split(","))

#: SENSIBILIDADE da fila. Vazio = usa a calibracao de `fidelidade.py`
#: (WDO@ 438/489), que e' o certo. `WDOF1_FILA="entrada:saida"` sobrescreve,
#: e existe por UM motivo: o veredito desta rodada nao pode depender de um
#: numero estimado com n=25. Se a geometria continuar negativa com fila
#: MENOR (mais otimista), o veredito nao e' sobre a calibracao. Fila 0/0
#: reproduz o motor de ate' 2026-09-08 -- e' referencia do otimismo antigo,
#: nunca candidata: ele previa +R$3,82/op para um pregao real que deu
#: -R$3,00.
#: Prazo da fatia de saida, em barras (= negocios). Vazio = herda o da
#: PRODUCAO, que desde 2026-09-09 e' SEM PRAZO (10**9). `WDOF1_PRAZOS="60"`
#: reproduz o robo de ate' aquele dia -- serve para medir quanto o prazo
#: custava sob a regua nova, que e' uma pergunta que ninguem tinha feito com
#: a fila no modelo. `0` na lista tambem significa sem prazo.
_PRAZOS = os.environ.get("WDOF1_PRAZOS", "").strip()
PRAZOS = (tuple(int(x) for x in _PRAZOS.split(",")) if _PRAZOS else (None,))
PRAZO_SEM_LIMITE = 10 ** 9

_FILA = os.environ.get("WDOF1_FILA", "").strip()
FILA_OVERRIDE = (tuple(float(x) for x in _FILA.split(":")) if _FILA else None)

CAMPOS_KWARGS = (
    "symbol", "tick_size", "level_spacing_ticks",
    "reanchor_mode", "reancora_min_segundos", "reancora_min_ticks",
    "max_trades_per_side", "session_stop_brl", "quantity",
    "margin_per_contract_brl", "margin_buffer", "hard_cap_contratos",
    "point_value_brl",
    "defesa_ativa", "defesa_gatilho_stop_pct", "defesa_alvo_proximidade_pct",
    "trailing_ativo", "trailing_recuo_ticks",
    "gate_atividade_ativo", "gate_volume_min", "gate_janela_segundos",
    "fatiar_saida_alvo", "exit_ttl_bars",
)


def breakeven_pct(alvo: int, stop: int) -> float:
    """Aritmetica pura: o `win%` que empata, a 1 contrato. O `+1` do stop e' o
    deslize medido dele (5 de 5 saidas reais nunca piores que o nivel)."""
    ganho = alvo * VALOR_TICK - CORRETAGEM_RT
    perda = (stop + 1) * VALOR_TICK + CORRETAGEM_RT
    return 100.0 * perda / (ganho + perda)


def ic_wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """IC 95% de proporcao por Wilson -- nao a aproximacao normal, que mente
    perto de 0% e 100% e e' justamente onde este robo vive (win ~90%)."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    meio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100.0 * (centro - meio), 100.0 * (centro + meio))


def _roda_pregao(spec: dict):
    """UM pregao, caixa proprio. Executado no processo filho."""
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot

    dia = spec["dia"]
    bars = pd.read_parquet(
        CACHE, columns=["open", "high", "low", "close", "volume"],
        filters=[("dia", "==", dia)],
    ).sort_index()
    if bars.empty:
        return None

    robo = get_daytrade_robot("wdo_grid_reload_maker")
    kwargs = {c: getattr(robo, c) for c in CAMPOS_KWARGS}
    kwargs["profit_ticks"] = int(spec["alvo"])
    kwargs["stop_ticks"] = int(spec["stop"])
    kwargs["risco_pct_por_trade"] = float(spec["risco"])
    if spec["prazo"] is not None:
        kwargs["exit_ttl_bars"] = (PRAZO_SEM_LIMITE if spec["prazo"] == 0
                                   else int(spec["prazo"]))
    strat = WdoGridReloadMaker(**kwargs)

    cfg = config_for(
        profile_for(SYMBOL),
        trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=CAPITAL_REAL_BRL,
        target_fills_as_maker=strat.target_fills_as_maker,
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
        # fila NAO se digita aqui: `config_for` resolve por `fidelidade.py`.
        # O override existe so' para SENSIBILIDADE (ver `FILA_OVERRIDE`).
        **({"queue_ahead_qty": spec["fila"][0],
            "exit_queue_ahead_qty": spec["fila"][1]} if spec["fila"] else {}),
    )
    res = run_intraday_backtest(bars, strat, cfg)
    trades = list(res.trades)
    equity = res.equity_curve
    return {
        "dia": dia, "alvo": spec["alvo"], "stop": spec["stop"],
        "risco": spec["risco"], "fila": spec["fila"],
        "prazo": spec["prazo"],
        "por_prazo": sum(1 for t in trades
                         if getattr(t, "exit_detail", None) == "target_timeout"),
        "n": len(trades),
        "ganhos": sum(1 for t in trades if t.pnl_brl > 0),
        "perdas": sum(1 for t in trades if t.pnl_brl < 0),
        "pnl": sum(t.pnl_brl for t in trades),
        "qtd_max": max((t.quantity for t in trades), default=0),
        "caixa_min": float(equity.min()) if len(equity) else float("nan"),
        "motivos": Counter(t.exit_reason.value for t in trades),
    }


def main() -> None:
    if not CACHE.exists():
        raise SystemExit(f"cache ausente: {CACHE}")
    sys.path.insert(0, str(RAIZ / "src"))

    dias_col = pd.read_parquet(CACHE, columns=["dia"])
    dias = sorted({d for d in dias_col["dia"].unique()
                   if pd.Timestamp(INICIO).date() <= d <= pd.Timestamp(FIM).date()})
    del dias_col
    if not dias:
        raise SystemExit(f"nenhum pregao entre {INICIO} e {FIM}")

    specs = [{"dia": d, "alvo": a, "stop": s, "risco": r,
              "fila": FILA_OVERRIDE, "prazo": pz}
             for pz in PRAZOS for r in RISCOS for a in ALVOS
             for s in STOPS for d in dias]
    print(f"[caixa reposto] {len(dias)} pregoes ({dias[0]} .. {dias[-1]}), "
          f"capital R${CAPITAL_REAL_BRL:.0f} REPOSTO por pregao")
    print(f"[caixa reposto] alvos {ALVOS}, stops {STOPS}, riscos {RISCOS}, "
          f"fila {'CALIBRADA (fidelidade.py)' if not FILA_OVERRIDE else FILA_OVERRIDE}")
    print(f"[caixa reposto] {len(specs)} execucoes, {MAX_WORKERS} processos "
          f"(1 pregao por processo -- nao estoura RAM)\n", flush=True)

    por_celula: dict[tuple, list] = {}
    t0 = time.perf_counter()
    feitos = 0
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {pool.submit(_roda_pregao, s): s for s in specs}
        for fut in as_completed(futuros):
            r = fut.result()
            feitos += 1
            if r is None:
                continue
            chave = (r["alvo"], r["stop"], r["risco"], r["fila"], r["prazo"])
            por_celula.setdefault(chave, []).append(r)
            if feitos % 10 == 0 or feitos == len(specs):
                print(f"  ({feitos}/{len(specs)}) "
                      f"{(time.perf_counter()-t0)/60:.1f} min", flush=True)

    print(f"\n[caixa reposto] {feitos} execucoes em "
          f"{(time.perf_counter()-t0)/60:.1f} min\n")

    # ---- tabela ------------------------------------------------------
    # NAO e' a tabela padrao de propósito: ela descreve UMA conta continua, e
    # aqui nao existe conta -- o caixa reseta todo pregao. Colunas de capital
    # (retorno, MaxDD, capital final) nao teriam significado.
    cab = (f"{'variante':<18}{'n ops':>8}{'win%':>8}{'IC 95% do win%':>20}"
           f"{'breakeven':>11}{'veredito':>12}{'R$/op':>9}"
           f"{'pregoes +':>11}{'ops/dia':>9}{'p/prazo':>9}")
    print(cab)
    print("-" * len(cab))
    for (alvo, stop, risco, fila, prazo), linhas in sorted(
            por_celula.items(), key=lambda kv: (kv[0][1], kv[0][4] or 0)):
        n = sum(x["n"] for x in linhas)
        g = sum(x["ganhos"] for x in linhas)
        pnl = sum(x["pnl"] for x in linhas)
        be = breakeven_pct(alvo, stop)
        lo, hi = ic_wilson(g, n)
        win = 100.0 * g / n if n else float("nan")
        if hi < be:
            veredito = "NEGATIVA"
        elif lo > be:
            veredito = "POSITIVA"
        else:
            veredito = "indefinido"
        positivos = sum(1 for x in linhas if x["pnl"] > 0)
        rot = (f"T{alvo}/S{stop} "
               + ("SEM prazo" if prazo in (None, 0) else f"prazo{prazo}"))
        print(f"{rot:<18}{n:>8}{win:>7.2f}%"
              f"{f'[{lo:.2f} ; {hi:.2f}]':>20}{be:>10.2f}%{veredito:>12}"
              f"{pnl/n if n else float('nan'):>9.2f}"
              f"{f'{positivos}/{len(linhas)}':>11}"
              f"{n/len(linhas):>9.0f}"
              f"{sum(x['por_prazo'] for x in linhas):>9}")

    print()
    print("LEITURA: o veredito olha o IC 95% do win% (Wilson) contra o "
          "breakeven aritmetico.")
    print("  NEGATIVA   = o intervalo INTEIRO abaixo do breakeven -- nenhum "
          "capital conserta.")
    print("  POSITIVA   = o intervalo INTEIRO acima -- ha' vantagem, e a "
          "conversa vira de caixa.")
    print("  indefinido = o intervalo atravessa o breakeven -- n nao chegou.")
    print("`R$/op` e' informativo; a soma dos pregoes NAO e' um resultado "
          "(cada um partiu do mesmo caixa).")


if __name__ == "__main__":
    main()
