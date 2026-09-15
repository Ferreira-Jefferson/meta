"""COLETA (2026-09-14) -- anatomia do wdo_orb nas 4 ultimas semanas FECHADAS.

Pergunta do dono: o resultado das ultimas 2-4 semanas parece alternar entre
uma sequencia longa de perdas e uma sequencia longa de ganhos. Ele quer saber
se da' para IDENTIFICAR quando cada sequencia comeca -- e deixou claro o
criterio de escolha: "melhor ganhar pouco e ganhar sempre do que ganhar muito
e devolver por mercado".

Este script NAO responde a pergunta. Ele so' COLETA, no maior nivel de
detalhe possivel, os dados que permitem responde-la depois. Nenhuma linha
aqui decide nada.

## As 5 janelas (rodam em PARALELO, uma por processo)

Hoje e' segunda 2026-09-14, entao as 4 ultimas semanas FECHADAS sao:

    S1  2026-08-17..2026-08-21   (5 pregoes)
    S2  2026-08-24..2026-08-28   (5 pregoes)
    S3  2026-08-31..2026-09-04   (5 pregoes)
    S4  2026-09-08..2026-09-11   (4 pregoes -- 07/09 e' feriado)

Cada uma roda ISOLADA, com o capital minimo real de partida do WDO@
(R$375,00 = margem 150 x buffer 2,0 x reserva 1,25 -- CLAUDE.md, ordem do
dono: capital inicial nunca arbitrario), caixa RESETADO no inicio da semana.

A 5a janela e' a que o dono pediu a parte: 2026-08-17..2026-09-11 CONTINUA,
capital de R$1.000,00 aportado UMA UNICA VEZ no comeco e nunca reposto --
para ver o efeito do caixa real caminhando sem renovacao.

## Base de dado

Tick a tick REAL do terminal. `data/raw_ticks/WDO_A_.parquet` cobre ate'
2026-09-04; os 4 pregoes de 08..11/09 foram baixados em 2026-09-14 por
`wdo_tick_update_semana_2026_09_14.py` para um parquet separado. Os dois sao
concatenados na leitura.

## Premissas de execucao -- as MESMAS da producao

`config_for` monta a config exatamente como `scripts/run_live.py`:
fidelidade de fila calibrada contra extrato real (438 na entrada / 489 na
saida, `backtest/intraday/fidelidade.py`), entrada e alvo por ordem-limite,
stop a mercado, teto de contratos por capital. Nada e' passado a mao.

## O que sai (um arquivo por recorte, em `scratch/wdo_orb_4semanas_2026_09_14/`)

    01_trades.csv    uma linha por OPERACAO, ~40 colunas de contexto
    02_ordens.csv    uma linha por ORDEM emitida (encheu? morreu de prazo?)
    03_pregoes.csv   uma linha por PREGAO (sequencia, recuperacao, caixa)
    04_semanas.csv   uma linha por JANELA
    05_equity.csv    a caminhada de caixa, operacao a operacao

Colunas de contexto por operacao: hora, faixa de abertura, geometria, atraso
do preenchimento, MFE/MAE em ticks (o quanto o trade andou a favor e contra
antes de fechar), volume e volatilidade realizada nos 5 e 15 minutos ANTES do
sinal, numero da operacao no dia, tipo (rompimento ou fade), sequencia de
ganhos/perdas ate' ali, e o caixa antes e depois.

Uso: `python -u scripts/daytrade/wdo_orb_4semanas_coleta_2026_09_14.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from core.models import IntradayExitReason  # noqa: E402
from market_data_intraday.tick_bars import ticks_to_degenerate_bars  # noqa: E402
from strategy.daytrade.base import (  # noqa: E402
    EnterLimit, MARGIN_BUFFER_FUTUROS, RESERVA_CAIXA_SEGURANCA,
)
from strategy.daytrade.lab.wdo_orb import WdoOrb  # noqa: E402

SYMBOL = "WDO@"
MARGEM_WDO_BRL = 150.0
CAPITAL_PARTIDA_BRL = MARGEM_WDO_BRL * MARGIN_BUFFER_FUTUROS * RESERVA_CAIXA_SEGURANCA  # 375,00
CAPITAL_CONTINUO_BRL = 1000.0
_ECONOMIA_WDO = (0.01, 0.001)
TICK_SIZE = 0.5

TICK_CANONICO = RAIZ / "data" / "raw_ticks" / "WDO_A_.parquet"
TICK_SEMANA_NOVA = RAIZ / "data" / "raw_ticks" / "WDO_A_semana_2026_09_08.parquet"
SAIDA = RAIZ / "scratch" / "wdo_orb_4semanas_2026_09_14"

#: (rotulo, primeiro dia, ultimo dia inclusive, capital, regime)
JANELAS = [
    ("S1", "2026-08-17", "2026-08-21", CAPITAL_PARTIDA_BRL, "semanal_375"),
    ("S2", "2026-08-24", "2026-08-28", CAPITAL_PARTIDA_BRL, "semanal_375"),
    ("S3", "2026-08-31", "2026-09-04", CAPITAL_PARTIDA_BRL, "semanal_375"),
    ("S4", "2026-09-08", "2026-09-11", CAPITAL_PARTIDA_BRL, "semanal_375"),
    ("CONT1K", "2026-08-17", "2026-09-11", CAPITAL_CONTINUO_BRL, "continuo_1000"),
]

DIAS_PT = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]


# ---------------------------------------------------------------------------
# 1. estrategia instrumentada -- MESMOS parametros de producao, so' registra
# ---------------------------------------------------------------------------

@dataclass
class WdoOrbInstrumentado(WdoOrb):
    """`WdoOrb` de producao, sem UM parametro alterado. A subclasse existe
    unicamente para gravar o que o motor nao devolve: qual ordem gerou qual
    trade (rompimento ou fade), em que instante o sinal aconteceu, com que
    faixa/geometria, e quais ordens morreram sem preencher."""

    _log_ordens: list = field(default_factory=list, init=False, repr=False)
    _log_eventos: list = field(default_factory=list, init=False, repr=False)
    _ts_corrente: object = field(default=None, init=False, repr=False)
    _close_corrente: float = field(default=float("nan"), init=False, repr=False)

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        self._ts_corrente = ts
        self._close_corrente = bar.close
        return super().on_bar(ts, bar, positions, session_pnl_brl)

    def on_order_expired(self, ts) -> None:
        self._log_eventos.append({"ts": ts, "evento": "prazo_estourado"})
        super().on_order_expired(ts)

    def on_order_rejected(self, ts) -> None:
        self._log_eventos.append({"ts": ts, "evento": "recusada"})
        super().on_order_rejected(ts)

    def _ordem(self, side, limite, stop_ticks, alvo_ticks, reason) -> EnterLimit:
        ordem = super()._ordem(side, limite, stop_ticks, alvo_ticks, reason)
        self._log_ordens.append({
            "sinal_ts": self._ts_corrente,
            "reason": reason,
            "tipo": "fade" if "fade" in reason else "rompimento",
            "side": side,
            "preco_sinal": self._close_corrente,
            "limite": limite,
            "stop_ticks": stop_ticks,
            "alvo_ticks": alvo_ticks,
            "faixa_hi": self._range_hi,
            "faixa_lo": self._range_lo,
            "faixa_ticks": (None if self._range_hi is None
                            else round((self._range_hi - self._range_lo) / self.tick_size)),
            "fades_no_dia": self._fades_no_dia,
        })
        return ordem


# ---------------------------------------------------------------------------
# 2. dado
# ---------------------------------------------------------------------------

def carregar_bars(inicio: str, fim_inclusive: str) -> pd.DataFrame:
    """Barras degeneradas (1 tick = 1 barra) do WDO@ no intervalo fechado de
    pregoes, unindo o parquet canonico (ate' 04/09) com o da semana nova."""
    ini = pd.Timestamp(inicio, tz="UTC")
    fim = pd.Timestamp(fim_inclusive, tz="UTC") + pd.Timedelta(days=1)
    pedacos = []
    for caminho in (TICK_CANONICO, TICK_SEMANA_NOVA):
        if not caminho.exists():
            continue
        df = pd.read_parquet(
            caminho, columns=["last", "volume", "volume_real"],
            filters=[("time", ">=", ini), ("time", "<", fim)],
        )
        if not df.empty:
            pedacos.append(df)
    if not pedacos:
        return pd.DataFrame()
    ticks = pd.concat(pedacos).sort_index(kind="mergesort")
    # o mesmo negocio pode existir nos dois arquivos se as janelas se tocarem
    ticks = ticks[~ticks.reset_index().duplicated().values]
    return ticks_to_degenerate_bars(ticks)


def monta_config(strategy: WdoOrb, cash: float):
    profile = profile_for(SYMBOL)
    trade_tick_value, trade_tick_size = _ECONOMIA_WDO
    return config_for(
        profile,
        trade_tick_value=trade_tick_value, trade_tick_size=trade_tick_size,
        target_fills_as_maker=strategy.target_fills_as_maker,
        anchor_exits_at_fill=strategy.anchor_exits_at_fill,
        initial_capital=cash,
    )


# ---------------------------------------------------------------------------
# 3. contexto de mercado -- calculado das BARRAS, nunca inventado
# ---------------------------------------------------------------------------

def _janela_antes(bars: pd.DataFrame, ts, minutos: int) -> pd.DataFrame:
    return bars.loc[ts - pd.Timedelta(minutes=minutos):ts]

def contexto_no_sinal(bars: pd.DataFrame, ts) -> dict:
    """Volume, velocidade e volatilidade REALIZADA nos minutos que antecedem
    o sinal. Tudo sai do proprio tick -- nenhum indicador externo."""
    saida = {}
    for minutos in (5, 15):
        jan = _janela_antes(bars, ts, minutos)
        if jan.empty:
            saida[f"vol_{minutos}min"] = float("nan")
            saida[f"nticks_{minutos}min"] = 0
            saida[f"amplitude_ticks_{minutos}min"] = float("nan")
            continue
        saida[f"vol_{minutos}min"] = float(jan["volume"].sum())
        saida[f"nticks_{minutos}min"] = int(len(jan))
        saida[f"amplitude_ticks_{minutos}min"] = float(
            (jan["close"].max() - jan["close"].min()) / TICK_SIZE)
    return saida


def excursao(bars: pd.DataFrame, entry_ts, exit_ts, entry_price: float,
             side: str) -> dict:
    """MFE/MAE em ticks: o quanto o trade chegou a andar A FAVOR e CONTRA
    entre o preenchimento e o fechamento. E' o que separa "perdeu porque a
    tese estava errada" de "estava ganhando e devolveu"."""
    jan = bars.loc[entry_ts:exit_ts, "close"]
    if jan.empty:
        return {"mfe_ticks": float("nan"), "mae_ticks": float("nan")}
    if side == "long":
        mfe = (jan.max() - entry_price) / TICK_SIZE
        mae = (jan.min() - entry_price) / TICK_SIZE
    else:
        mfe = (entry_price - jan.min()) / TICK_SIZE
        mae = (entry_price - jan.max()) / TICK_SIZE
    return {"mfe_ticks": float(mfe), "mae_ticks": float(mae)}


# ---------------------------------------------------------------------------
# 4. UMA janela -- roda o motor e devolve os registros ja' montados
# ---------------------------------------------------------------------------

def roda_janela(rotulo: str, inicio: str, fim: str, capital: float,
                regime: str) -> dict:
    bars = carregar_bars(inicio, fim)
    if bars.empty:
        return {"rotulo": rotulo, "erro": "sem barras", "trades": [],
                "ordens": [], "pregoes": [], "semana": {}, "equity": []}

    strat = WdoOrbInstrumentado()
    cfg = monta_config(strat, capital)
    res = run_intraday_backtest(bars, strat, cfg)

    pregoes = sorted(set(bars.index.date))
    ordens = sorted(strat._log_ordens, key=lambda o: o["sinal_ts"])
    eventos = sorted(strat._log_eventos, key=lambda e: e["ts"])

    # ---- trades, com o contexto todo -------------------------------------
    linhas_trade = []
    caixa = capital
    seq_anterior = None          # "G"/"P" do trade anterior (na janela)
    streak = 0                   # tamanho da sequencia corrente
    pnl_dia_ate_agora: dict = {}
    n_op_no_dia: dict = {}

    for t in sorted(res.trades, key=lambda x: x.entry_ts):
        dia = pd.Timestamp(t.entry_ts).date()
        n_op_no_dia[dia] = n_op_no_dia.get(dia, 0) + 1
        ordem = None
        for o in ordens:
            if o["sinal_ts"] <= t.entry_ts:
                ordem = o
            else:
                break
        pnl = t.pnl_brl
        resultado = "G" if pnl > 0 else "P"
        if resultado == seq_anterior:
            streak += 1
        else:
            streak = 1
            seq_anterior = resultado

        entry_brt = pd.Timestamp(t.entry_ts).tz_convert("America/Sao_Paulo")
        exit_brt = pd.Timestamp(t.exit_ts).tz_convert("America/Sao_Paulo")
        ctx = contexto_no_sinal(bars, ordem["sinal_ts"] if ordem else t.entry_ts)
        exc = excursao(bars, t.entry_ts, t.exit_ts, t.entry_price, t.side)
        pnl_antes_no_dia = pnl_dia_ate_agora.get(dia, 0.0)

        linhas_trade.append({
            "janela": rotulo, "regime": regime,
            "data": str(dia), "dia_semana": DIAS_PT[entry_brt.weekday()],
            "op_do_dia": n_op_no_dia[dia],
            "tipo": ordem["tipo"] if ordem else "?",
            "reason": ordem["reason"] if ordem else "?",
            "side": t.side,
            "entrada_brt": entry_brt.strftime("%H:%M:%S"),
            "saida_brt": exit_brt.strftime("%H:%M:%S"),
            "hora_entrada": entry_brt.hour,
            "duracao_min": round((t.exit_ts - t.entry_ts).total_seconds() / 60.0, 2),
            "sinal_brt": (pd.Timestamp(ordem["sinal_ts"]).tz_convert("America/Sao_Paulo")
                          .strftime("%H:%M:%S") if ordem else ""),
            "atraso_fill_min": (round((t.entry_ts - ordem["sinal_ts"]).total_seconds() / 60.0, 2)
                                if ordem else float("nan")),
            "entry_price": t.entry_price, "exit_price": t.exit_price,
            "stop_ticks": ordem["stop_ticks"] if ordem else None,
            "alvo_ticks": ordem["alvo_ticks"] if ordem else None,
            "faixa_ticks": ordem["faixa_ticks"] if ordem else None,
            "faixa_hi": ordem["faixa_hi"] if ordem else None,
            "faixa_lo": ordem["faixa_lo"] if ordem else None,
            "exit_reason": t.exit_reason.value if hasattr(t.exit_reason, "value") else str(t.exit_reason),
            "exit_detail": t.exit_detail or "",
            "pnl_brl": round(pnl, 2),
            "pnl_ticks": round(((t.exit_price - t.entry_price) if t.side == "long"
                                else (t.entry_price - t.exit_price)) / TICK_SIZE, 1),
            "fees": round(t.fees_total, 2),
            "resultado": resultado,
            "streak": streak,
            "mfe_ticks": round(exc["mfe_ticks"], 1),
            "mae_ticks": round(exc["mae_ticks"], 1),
            "pnl_dia_antes": round(pnl_antes_no_dia, 2),
            "caixa_antes": round(caixa, 2),
            "caixa_depois": round(caixa + pnl, 2),
            **{k: (round(v, 2) if isinstance(v, float) else v) for k, v in ctx.items()},
        })
        caixa += pnl
        pnl_dia_ate_agora[dia] = pnl_antes_no_dia + pnl

    # ---- ordens (inclusive as que nunca preencheram) ----------------------
    ts_entradas = {pd.Timestamp(t.entry_ts) for t in res.trades}
    linhas_ordem = []
    for i, o in enumerate(ordens):
        proxima = ordens[i + 1]["sinal_ts"] if i + 1 < len(ordens) else None
        encheu = any(o["sinal_ts"] <= ts and (proxima is None or ts < proxima)
                     for ts in ts_entradas)
        morreu = ""
        if not encheu:
            for ev in eventos:
                if ev["ts"] >= o["sinal_ts"] and (proxima is None or ev["ts"] <= proxima):
                    morreu = ev["evento"]
                    break
        sinal_brt = pd.Timestamp(o["sinal_ts"]).tz_convert("America/Sao_Paulo")
        linhas_ordem.append({
            "janela": rotulo, "regime": regime,
            "data": str(sinal_brt.date()), "sinal_brt": sinal_brt.strftime("%H:%M:%S"),
            "tipo": o["tipo"], "side": o["side"], "limite": o["limite"],
            "preco_sinal": o["preco_sinal"],
            "stop_ticks": o["stop_ticks"], "alvo_ticks": o["alvo_ticks"],
            "faixa_ticks": o["faixa_ticks"],
            "preencheu": int(encheu), "morte": morreu,
        })

    # ---- pregoes ---------------------------------------------------------
    linhas_pregao = []
    caixa_dia = capital
    trades_por_dia: dict = {}
    for lt in linhas_trade:
        trades_por_dia.setdefault(lt["data"], []).append(lt)
    for dia in pregoes:
        chave = str(dia)
        lst = trades_por_dia.get(chave, [])
        ordens_dia = [o for o in linhas_ordem if o["data"] == chave]
        pnl_dia = sum(x["pnl_brl"] for x in lst)
        faixa = next((o["faixa_ticks"] for o in ordens_dia if o["faixa_ticks"]), None)
        primeira = lst[0] if lst else None
        linhas_pregao.append({
            "janela": rotulo, "regime": regime, "data": chave,
            "dia_semana": DIAS_PT[pd.Timestamp(dia).weekday()],
            "n_ops": len(lst),
            "n_ordens": len(ordens_dia),
            "ordens_sem_fill": sum(1 for o in ordens_dia if not o["preencheu"]),
            "pnl_brl": round(pnl_dia, 2),
            "faixa_ticks": faixa,
            "primeira_op": primeira["resultado"] if primeira else "",
            "primeira_op_tipo": primeira["tipo"] if primeira else "",
            "primeira_op_pnl": primeira["pnl_brl"] if primeira else 0.0,
            "recuperou": int(bool(primeira and primeira["resultado"] == "P" and pnl_dia > 0)),
            "seq_resultados": "".join(x["resultado"] for x in lst),
            "caixa_abertura": round(caixa_dia, 2),
            "caixa_fechamento": round(caixa_dia + pnl_dia, 2),
        })
        caixa_dia += pnl_dia

    # ---- resumo da janela -------------------------------------------------
    pnls = [x["pnl_brl"] for x in linhas_trade]
    ganhos = [p for p in pnls if p > 0]
    perdas = [p for p in pnls if p <= 0]
    dias_com_trade = {x["data"] for x in linhas_trade}
    semana = {
        "janela": rotulo, "regime": regime, "inicio": inicio, "fim": fim,
        "capital_inicial": capital,
        "pregoes": len(pregoes),
        "pregoes_sem_trade": len(pregoes) - len(dias_com_trade),
        "sessoes_puladas_capital": len(res.sessoes_puladas_por_capital),
        "trades": len(pnls),
        "ordens": len(linhas_ordem),
        "ordens_sem_fill": sum(1 for o in linhas_ordem if not o["preencheu"]),
        "win_pct": round(100.0 * len(ganhos) / len(pnls), 2) if pnls else float("nan"),
        "liquido_brl": round(sum(pnls), 2),
        "rs_por_op": round(sum(pnls) / len(pnls), 2) if pnls else float("nan"),
        "ganho_medio": round(sum(ganhos) / len(ganhos), 2) if ganhos else float("nan"),
        "perda_media": round(sum(perdas) / len(perdas), 2) if perdas else float("nan"),
        "capital_final": round(capital + sum(pnls), 2),
        "caixa_minimo": round(min([x["caixa_depois"] for x in linhas_trade] + [capital]), 2),
        "stops": sum(1 for x in linhas_trade if x["exit_reason"] == IntradayExitReason.STOP.value),
        "zerou": int(res.wiped_out_at is not None),
        "fila_entrada": res.fila_entrada_qty, "fila_saida": res.fila_saida_qty,
        "recusadas_capital": res.ordens_recusadas_por_capital,
    }

    equity = [{"janela": rotulo, "regime": regime, "n": i + 1,
               "data": x["data"], "hora": x["entrada_brt"],
               "pnl_brl": x["pnl_brl"], "caixa": x["caixa_depois"]}
              for i, x in enumerate(linhas_trade)]

    return {"rotulo": rotulo, "erro": "", "trades": linhas_trade,
            "ordens": linhas_ordem, "pregoes": linhas_pregao,
            "semana": semana, "equity": equity}


# ---------------------------------------------------------------------------
# main -- paralelo, cada janela imprime a SUA linha assim que termina
# ---------------------------------------------------------------------------

def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    print(f"[coleta] capital semanal R${CAPITAL_PARTIDA_BRL:,.2f} | "
          f"continuo R${CAPITAL_CONTINUO_BRL:,.2f}", flush=True)
    print(f"[coleta] {len(JANELAS)} janelas em paralelo...\n", flush=True)

    resultados = {}
    with ProcessPoolExecutor(max_workers=min(5, len(JANELAS))) as pool:
        futuros = {pool.submit(roda_janela, *j): j[0] for j in JANELAS}
        for fut in as_completed(futuros):
            rot = futuros[fut]
            try:
                r = fut.result()
            except Exception as exc:  # pragma: no cover
                print(f"[{rot}] ERRO: {exc!r}", flush=True)
                continue
            resultados[rot] = r
            s = r["semana"]
            if not s:
                print(f"[{rot}] {r['erro']}", flush=True)
                continue
            print(f"[{rot}] {s['pregoes']} pregoes | {s['trades']} ops | "
                  f"win {s['win_pct']}% | liquido R${s['liquido_brl']:,.2f} | "
                  f"R$/op {s['rs_por_op']} | caixa min R${s['caixa_minimo']:,.2f} | "
                  f"sem trade {s['pregoes_sem_trade']} | "
                  f"ordens s/fill {s['ordens_sem_fill']}/{s['ordens']}", flush=True)

    ordem_janelas = [j[0] for j in JANELAS]
    def concat(chave):
        linhas = []
        for rot in ordem_janelas:
            linhas.extend(resultados.get(rot, {}).get(chave, []))
        return pd.DataFrame(linhas)

    arquivos = {
        "01_trades.csv": concat("trades"),
        "02_ordens.csv": concat("ordens"),
        "03_pregoes.csv": concat("pregoes"),
        "04_semanas.csv": pd.DataFrame(
            [resultados[r]["semana"] for r in ordem_janelas
             if r in resultados and resultados[r]["semana"]]),
        "05_equity.csv": concat("equity"),
    }
    print()
    for nome, df in arquivos.items():
        caminho = SAIDA / nome
        df.to_csv(caminho, index=False, encoding="utf-8")
        print(f"[coleta] {nome}: {len(df)} linhas -> {caminho}", flush=True)


if __name__ == "__main__":
    main()
