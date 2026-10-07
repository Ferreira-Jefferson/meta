"""ESTAGIO 2 (2026-09-27) -- fade do gap overnight do WDO@ NO MOTOR REAL.

## De onde isto vem

Estagio 1 (correlacao bruta, sem motor, permutacao + Bonferroni):

  * `wdo_gap_proprio_padrao_2026_09_27.py` -- 18 celulas, gap x DIRECAO do
    pregao. 0/18 sobrevivem, melhor p=0,215.
  * `wdo_gap_padrao_nao_linear_2026_09_27.py` -- 28 celulas nao-lineares.
    3/28 sobrevivem Bonferroni; a mais forte e' o fill-rate do gap por
    TERCIL de magnitude: gaps PEQUENOS voltam a tocar o fechamento anterior
    em 89,2% dos pregoes (122 pregoes, 2026-02-27..2026-08-25), gaps
    GRANDES so' em 41,5% (diff=0,477, p=0,00005).

Essa diferenca e' PROVAVELMENTE em boa parte mecanica (probabilidade de
toque, nao necessariamente edge) -- so' autoriza gastar ESTE estagio, nao
decide nada sozinha. Aqui a hipotese vira `IntradayStrategy`
(`strategy.daytrade.lab.wdo_gap_fade.WdoGapFade`) e roda no motor de
verdade: desenho de execucao FECHADO (entrada/alvo por ordem-limite, nunca
a mercado; stop a mercado, unica excecao), fila calibrada de
`backtest/intraday/fidelidade.py` via `config_for`, capital real de partida
R$375,00, proibicao do T1 respeitada por um PISO de alvo em ticks
(`WdoGapFade.alvo_min_ticks`).

## Metodo do TERCIL -- congelado no IS, aplicado ao OOS

Recomputamos os cortes de tercil de |gap| aqui (nao reaproveitamos o CSV do
estagio 1, que veio de `WDO_A_f1.parquet` -- um parquet de reconstrucao
DIFERENTE do que o motor de backtest realmente le', `WDO_A_.parquet` via
`carregar_bars`). Os cortes usam SO' a distribuicao do IS (71 pregoes com
gap valido, 2026-02-27..2026-06-12) e sao aplicados, congelados, ao OOS
(2026-06-15..2026-08-14) -- exatamente o padrao ja usado neste projeto para
nao gastar as duas janelas na mesma escolha (`LIMIARES_DESCOBERTA` em
`wdo_orb_fade_agitacao_is_oos_2026_09_14.py`). Calcular o tercil olhando o
OOS tambem seria "escolher parametro olhando as duas janelas ao mesmo
tempo" -- erro ja documentado neste projeto.

## Capital REPOSTO por pregao -- corrigido depois de medir a versao continua

A PRIMEIRA versao deste script rodava capital CONTINUO (R$375 uma vez no
inicio da janela, carregando de pregao a pregao) -- mesma razao que
`wdo_orb_geometria_is_oos_2026_09_14.py` da' para o caso contrario (aquele
robo dispara quase todo dia; este fade so' tenta nos dias elegiveis, e' baixa
frequencia por construcao, entao a caminhada continua pareceria segura).
Estava ERRADA, e o numero provou isso: **no IS, 100.955 ordens foram
armadas e 100.269 (99,3%) foram recusadas por CAPITAL** (nao por o preco
nunca ter tocado a entrada) -- so' 645 morreram por prazo. No OOS, 19.324 de
19.512 (99,05%). Em nenhuma das duas janelas uma SESSAO foi pulada
(`sessoes_puladas_por_capital=0`) nem a conta zerou (`wiped_out_at=None`) --
o caixa so' caiu abaixo da margem crua (R$150) num stop cedo e ficou PRESO
la' pelo resto da janela inteira, rejeitando toda tentativa seguinte em
SILENCIO. E' exatamente o padrao que `LICOES_DE_PRODUCAO.md`/CLAUDE.md
descrevem em "O piso de capital e' indicacao de PARTIDA, nunca condicao de
CONTINUIDADE" -- so' que medido aqui, nao so' lido na documentacao.

A correcao: cada pregao ELEGIVEL roda um `run_intraday_backtest` ISOLADO,
capital R$375 FRESCO no inicio do pregao -- mede a GEOMETRIA da estrategia,
nao o portao de capital. Paralelizado por pregao (`ProcessPoolExecutor`,
`submit`/`as_completed`, nunca `pool.map`) porque agora sao dezenas de
execucoes independentes em vez de duas continuas.

## O que a tabela reporta, alem do liquido

`win% ao lado do breakeven EMPIRICO` (perda_media/(ganho_medio+perda_media),
nao o nominal -- o payoff aqui NAO e' simetrico por construcao, o alvo e' a
distancia ate' o fechamento anterior e o stop e' derivado dela por
`razao_alvo_stop`), MFE/MAE em ticks (o preco TOCAR o alvo, medido no
estagio 1, nao e' o mesmo que um trade real capturar isso sem ser stopado
antes -- e' essa lacuna que este script fecha), e o atraso de preenchimento
REALIZADO em minutos (nunca o prazo nominal em barras -- base de tick). A
tabela padrao usa `capital_nocional=True` (retorno%/MaxDD%/capital final
saem `—`) porque, sob capital REPOSTO por pregao, esses tres numeros nao
descrevem nenhuma conta real que exista -- mesma razao que `report.py` ja
documenta para o ambiente de margem infinita da Copa BTG.

Uso: `python -u scripts/daytrade/wdo_gap_fade_is_oos_2026_09_27.py`
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.report import cabecalho, linha, linha_de_resultado, num_br  # noqa: E402
from strategy.daytrade.lab.wdo_gap_fade import WdoGapFade  # noqa: E402
from wdo_orb_4semanas_coleta_2026_09_14 import (  # noqa: E402
    CAPITAL_PARTIDA_BRL, TICK_SIZE, carregar_bars, excursao, monta_config,
)

#: Mesmas janelas ja' usadas na familia `wdo_orb` para este instrumento
#: (`wdo_orb_fade_agitacao_is_oos_2026_09_14.JANELAS`) -- reaproveitadas, nao
#: escolhidas de novo.
IS_INI, IS_FIM = "2026-02-27", "2026-06-12"
OOS_INI, OOS_FIM = "2026-06-15", "2026-08-14"

#: Piso do alvo (proibicao do T1, CLAUDE.md) -- so' para o DIAGNOSTICO deste
#: script (quantos dias elegiveis por tercil ainda esbarram no piso). A
#: estrategia (`WdoGapFade.alvo_min_ticks`, mesmo valor por default) e' quem
#: de fato recusa a operacao -- este numero aqui nunca filtra a decisao real.
ALVO_MIN_TICKS_DIAGNOSTICO = 4

SAIDA = RAIZ / "scratch" / "wdo_gap_fade_2026_09_27"
MAX_WORKERS = min(12, (os.cpu_count() or 4))


# ---------------------------------------------------------------------------
# 1. estrategia instrumentada -- so' registra o que o motor nao devolve
# ---------------------------------------------------------------------------

@dataclass
class WdoGapFadeInstrumentado(WdoGapFade):
    _log_ordens: list = field(default_factory=list, init=False, repr=False)
    _log_eventos: list = field(default_factory=list, init=False, repr=False)
    _ts_corrente: object = field(default=None, init=False, repr=False)

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        self._ts_corrente = ts
        return super().on_bar(ts, bar, positions, session_pnl_brl)

    def on_order_rejected(self, ts) -> None:
        self._log_eventos.append({"ts": ts, "evento": "recusada_capital"})
        super().on_order_rejected(ts)

    def on_order_expired(self, ts) -> None:
        self._log_eventos.append({"ts": ts, "evento": "prazo_estourado"})
        super().on_order_expired(ts)

    def _ordem(self):
        ordem = super()._ordem()
        self._log_ordens.append({
            "sinal_ts": self._ts_corrente, "lado": self._lado,
            "limite": ordem.limit_price, "alvo_ticks": self._alvo_ticks,
            "stop_ticks": self._stop_ticks, "prev_close_px": self._prev_close_hoje,
        })
        return ordem


# ---------------------------------------------------------------------------
# 2. sessoes + gap, congelado no IS
# ---------------------------------------------------------------------------

def construir_sessoes(bars: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por pregao presente em `bars`: abertura (primeiro close da
    barra degenerada), fechamento (ultimo), e gap_ticks contra o fechamento
    do pregao ANTERIOR que existe no dataset (nao do calendario -- gap de
    fim de semana/feriado entra igual, e' o mesmo pregao anterior real)."""
    linhas = []
    prev_close = None
    for dia, g in bars.groupby(bars.index.date):
        abertura = float(g["close"].iloc[0])
        fechamento = float(g["close"].iloc[-1])
        gap_ticks = ((abertura - prev_close) / TICK_SIZE) if prev_close is not None else float("nan")
        linhas.append({"data": dia, "abertura": abertura, "fechamento": fechamento,
                        "prev_close": prev_close, "gap_ticks": gap_ticks})
        prev_close = fechamento
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# 3. UM pregao, ISOLADO -- capital R$375 fresco, roda so' se elegivel
# ---------------------------------------------------------------------------

def roda_pregao_isolado(dia: str, prev_close_px: float) -> dict:
    """`dia`: pregao elegivel (tercil pequeno/medio, decidido pelo chamador --
    esta funcao so' roda quem ja' foi filtrado, para nao gastar tempo de
    engine em pregoes que o robo nunca tentaria operar)."""
    bars = carregar_bars(dia, dia)
    if bars.empty:
        return {"data": dia, "trades": [], "n_ordens_armadas": 0,
                "n_recusadas_capital_evento": 0, "n_prazo_estourado": 0,
                "ordens_recusadas_por_capital_result": 0, "wiped_out_at": None,
                "deslize_alvo_ticks": 0.0, "fila_entrada_qty": 0.0,
                "fila_saida_qty": 0.0, "fila_calibrada": None}

    strat = WdoGapFadeInstrumentado(elegivel=True, prev_close_px=prev_close_px)
    cfg = monta_config(strat, CAPITAL_PARTIDA_BRL)
    res = run_intraday_backtest(bars, strat, cfg)

    ordens = sorted(strat._log_ordens, key=lambda o: o["sinal_ts"])
    linhas_trade = []
    for t in sorted(res.trades, key=lambda x: x.entry_ts):
        ordem = None
        for o in ordens:
            if o["sinal_ts"] <= t.entry_ts:
                ordem = o
            else:
                break
        pnl_ticks = (((t.exit_price - t.entry_price) if t.side == "long"
                      else (t.entry_price - t.exit_price)) / TICK_SIZE)
        exc = excursao(bars, t.entry_ts, t.exit_ts, t.entry_price, t.side)
        razao = t.exit_reason.value if hasattr(t.exit_reason, "value") else str(t.exit_reason)
        linhas_trade.append({
            "data": dia, "side": t.side,
            "entry_ts": t.entry_ts, "exit_ts": t.exit_ts,
            "sinal_ts": ordem["sinal_ts"] if ordem else pd.NaT,
            "atraso_fill_min": (round((t.entry_ts - ordem["sinal_ts"]).total_seconds() / 60.0, 2)
                                if ordem else float("nan")),
            "entry_price": t.entry_price, "exit_price": t.exit_price,
            "alvo_ticks": ordem["alvo_ticks"] if ordem else float("nan"),
            "stop_ticks": ordem["stop_ticks"] if ordem else float("nan"),
            "prev_close_px": ordem["prev_close_px"] if ordem else float("nan"),
            "pnl_brl": round(t.pnl_brl, 2), "pnl_ticks": round(pnl_ticks, 1),
            "exit_reason": razao,
            "mfe_ticks": round(exc["mfe_ticks"], 1), "mae_ticks": round(exc["mae_ticks"], 1),
        })
    eventos = strat._log_eventos
    return {
        "data": dia, "trades": linhas_trade,
        "n_ordens_armadas": len(ordens),
        "n_recusadas_capital_evento": sum(1 for e in eventos if e["evento"] == "recusada_capital"),
        "n_prazo_estourado": sum(1 for e in eventos if e["evento"] == "prazo_estourado"),
        "ordens_recusadas_por_capital_result": res.ordens_recusadas_por_capital,
        "wiped_out_at": res.wiped_out_at,
        "deslize_alvo_ticks": res.deslize_alvo_ticks,
        "fila_entrada_qty": res.fila_entrada_qty, "fila_saida_qty": res.fila_saida_qty,
        "fila_calibrada": res.fila_calibrada,
    }


def resumo_texto(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0}
    df = pd.DataFrame(trades)
    pnl = df["pnl_brl"]
    g, p = pnl[pnl > 0], pnl[pnl <= 0]
    top3 = pnl.nlargest(min(3, len(pnl))).sum()
    return {
        "n": len(df),
        "liquido": round(pnl.sum(), 2),
        "rs_por_op": round(pnl.mean(), 2),
        "win_pct": round(100.0 * len(g) / len(df), 1),
        "ganho_medio": round(g.mean(), 2) if len(g) else float("nan"),
        "perda_media": round(p.mean(), 2) if len(p) else float("nan"),
        "be_empirico_pct": (round(100.0 * (-p.mean()) / (g.mean() - p.mean()), 1)
                             if len(g) and len(p) else float("nan")),
        "top3_pct": round(100.0 * top3 / pnl.sum(), 1) if pnl.sum() != 0 else float("nan"),
        "atraso_min_p50": round(df["atraso_fill_min"].median(), 2),
        "atraso_min_p90": round(df["atraso_fill_min"].quantile(0.9), 2),
        "mfe_perdedor_med": round(df.loc[df.pnl_brl <= 0, "mfe_ticks"].median(), 1) if len(p) else float("nan"),
        "mae_vencedor_med": round(df.loc[df.pnl_brl > 0, "mae_ticks"].median(), 1) if len(g) else float("nan"),
        "stops": int((df["exit_reason"] == "stop").sum()),
        "alvos": int((df["exit_reason"] == "target").sum()),
        "flatten": int((df["exit_reason"] == "forced_flatten").sum()),
        "long": int((df["side"] == "long").sum()),
        "short": int((df["side"] == "short").sum()),
    }


@dataclass
class _PseudoResultado:
    """O suficiente de `IntradayBacktestResult` para `linha_de_resultado`
    funcionar sobre um conjunto de pregoes REPOSTOS (capital independente por
    pregao, nao uma conta continua) -- `capital_nocional=True` apaga as tres
    colunas que dependeriam de uma conta real (retorno%/MaxDD%/capital
    final), mesmo mecanismo que `report.py` ja usa para o ambiente de margem
    infinita da Copa BTG."""
    trades: list
    equity_curve: pd.Series
    metrics: dict = field(default_factory=dict)
    wiped_out_at: object = None
    sessoes_puladas_por_capital: list = field(default_factory=list)
    ordens_recusadas_por_capital: int = 0
    deslize_alvo_ticks: float = 0.0
    fila_entrada_qty: float = 0.0
    fila_saida_qty: float = 0.0
    fila_calibrada: bool | None = None


def monta_pseudo_resultado(resultados_dia: list[dict], todos_dias: list) -> _PseudoResultado:
    """Agrega os resultados por-pregao (capital reposto) num objeto que
    `linha_de_resultado` sabe ler. A curva de equity e' a soma cumulativa dos
    trades em ordem cronologica, com um ponto por PREGAO da janela inteira
    (nao so' os dias com trade) -- para a coluna `pregoes` da tabela padrao
    contar a janela toda, e `MaxDD R$` refletir a sequencia real de
    trades (a unica leitura de risco que faz sentido sob reposicao: nao
    existe conta continua de verdade aqui, ver a docstring do modulo)."""
    trades_por_dia: dict[str, float] = {}
    todos_trades = []
    for r in resultados_dia:
        pnl_dia = sum(t["pnl_brl"] for t in r["trades"])
        if r["trades"]:
            trades_por_dia[r["data"]] = pnl_dia
        todos_trades.extend(r["trades"])

    cum = 0.0
    pontos_ts, pontos_v = [], []
    for d in sorted(str(x) for x in todos_dias):
        cum += trades_por_dia.get(d, 0.0)
        pontos_ts.append(pd.Timestamp(f"{d} 21:00", tz="UTC"))
        pontos_v.append(cum)
    equity = pd.Series(pontos_v, index=pd.DatetimeIndex(pontos_ts))

    # objetos IntradayTrade de verdade, so' para `linha_de_resultado` somar
    # `pnl_brl` -- reaproveita um trade "fake" minimo via SimpleNamespace.
    class _T:
        __slots__ = ("pnl_brl",)
        def __init__(self, pnl): self.pnl_brl = pnl
    trades_obj = [_T(t["pnl_brl"]) for t in todos_trades]

    amostra = next((r for r in resultados_dia if r["trades"]), None)
    if amostra is None:
        amostra = next((r for r in resultados_dia if r.get("fila_calibrada") is not None), None)

    return _PseudoResultado(
        trades=trades_obj, equity_curve=equity,
        ordens_recusadas_por_capital=sum(r["ordens_recusadas_por_capital_result"] for r in resultados_dia),
        wiped_out_at=next((r["wiped_out_at"] for r in resultados_dia if r["wiped_out_at"] is not None), None),
        deslize_alvo_ticks=(amostra["deslize_alvo_ticks"] if amostra else 0.0),
        fila_entrada_qty=(amostra["fila_entrada_qty"] if amostra else 0.0),
        fila_saida_qty=(amostra["fila_saida_qty"] if amostra else 0.0),
        fila_calibrada=(amostra["fila_calibrada"] if amostra else None),
    )


def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)

    print(f"[gap_fade] carregando ticks {IS_INI}..{OOS_FIM} (WDO@, mesma fonte "
          f"do motor de backtest) so' para montar o calendario de gap...", flush=True)
    bars_completo = carregar_bars(IS_INI, OOS_FIM)
    print(f"[gap_fade] {len(bars_completo):,} barras degeneradas\n", flush=True)

    sess = construir_sessoes(bars_completo)
    sess["abs_gap"] = sess["gap_ticks"].abs()
    del bars_completo  # so' precisavamos dela para montar o calendario de gap

    is_ini_d, is_fim_d = pd.Timestamp(IS_INI).date(), pd.Timestamp(IS_FIM).date()
    oos_ini_d, oos_fim_d = pd.Timestamp(OOS_INI).date(), pd.Timestamp(OOS_FIM).date()
    sess_is = sess[(sess.data >= is_ini_d) & (sess.data <= is_fim_d) & sess.gap_ticks.notna()]
    sess_oos = sess[(sess.data >= oos_ini_d) & (sess.data <= oos_fim_d) & sess.gap_ticks.notna()]

    cortes = sess_is["abs_gap"].quantile([1 / 3, 2 / 3]).to_numpy()
    corte_pequeno_medio, corte_medio_grande = cortes[0], cortes[1]
    print(f"[gap_fade] cortes de tercil |gap| CONGELADOS no IS ({len(sess_is)} pregoes "
          f"com gap valido): pequeno<={corte_pequeno_medio:.1f}t  medio<={corte_medio_grande:.1f}t  "
          f"grande>{corte_medio_grande:.1f}t", flush=True)

    janelas_sub = {"IS": sess_is, "OOS": sess_oos}
    tarefas = []  # (rotulo, dia_str, prev_close_px)
    for rotulo, sub in janelas_sub.items():
        eleg = sub[sub["abs_gap"] <= corte_medio_grande]
        n_piso = int((eleg["abs_gap"].round() >= ALVO_MIN_TICKS_DIAGNOSTICO).sum())
        print(f"[gap_fade] {rotulo}: {len(sub)} pregoes com gap valido, "
              f"{len(eleg)} elegiveis (tercil peq/med), {n_piso} acima do piso "
              f"de {ALVO_MIN_TICKS_DIAGNOSTICO} ticks de alvo", flush=True)
        for _, row in eleg.iterrows():
            tarefas.append((rotulo, str(row["data"]), float(row["prev_close"])))

    print(f"\n[gap_fade] {len(tarefas)} pregoes elegiveis, capital REPOSTO "
          f"R${CAPITAL_PARTIDA_BRL:.2f} por pregao, {MAX_WORKERS} processos...\n",
          flush=True)

    resultados_por_janela: dict[str, list[dict]] = {"IS": [], "OOS": []}
    feitos = 0
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {pool.submit(roda_pregao_isolado, dia, prev_close): (rotulo, dia)
                   for rotulo, dia, prev_close in tarefas}
        for fut in as_completed(futuros):
            rotulo, dia = futuros[fut]
            feitos += 1
            try:
                r = fut.result()
            except Exception as exc:
                print(f"[{rotulo}/{dia}] ERRO: {exc!r}", flush=True)
                continue
            resultados_por_janela[rotulo].append(r)
            if r["trades"]:
                liq = sum(t["pnl_brl"] for t in r["trades"])
                print(f"[{rotulo}/{dia}] {len(r['trades'])} trade(s) | liquido R${liq:,.2f}", flush=True)
            if feitos % 20 == 0:
                print(f"  ... {feitos}/{len(tarefas)} pregoes", flush=True)

    # ---- tabela PADRAO (report.py), capital NOCIONAL (reposto por pregao) --
    print("\n" + "=" * 140)
    print("TABELA PADRAO -- backtest/intraday/report.py (capital REPOSTO por pregao)")
    print("=" * 140)
    extras_nomes = ("elegiveis", "sem_trade", "BE_emp%", "atraso_p50min")
    linhas_padrao = []
    todos_trades_por_janela = {}
    for rotulo, sub in janelas_sub.items():
        resultados_dia = resultados_por_janela[rotulo]
        todos_dias = sub["data"].tolist()
        pseudo = monta_pseudo_resultado(resultados_dia, todos_dias)
        trades = [t for r in resultados_dia for t in r["trades"]]
        todos_trades_por_janela[rotulo] = trades
        resumo = resumo_texto(trades)
        n_eleg = sum(1 for r in resultados_dia)
        dias_com_trade = len({t["data"] for t in trades})
        extras = {
            "elegiveis": str(n_eleg),
            "sem_trade": str(n_eleg - dias_com_trade),
            "BE_emp%": (f"{num_br(resumo['be_empirico_pct'], 1)}%"
                        if resumo.get("n", 0) else "—"),
            "atraso_p50min": (num_br(resumo["atraso_min_p50"], 1)
                               if resumo.get("n", 0) else "—"),
        }
        linhas_padrao.append(linha_de_resultado(
            variante=rotulo, result=pseudo, initial_capital=CAPITAL_PARTIDA_BRL,
            capital_nocional=True, extras=extras,
        ))
    print(cabecalho(extras_nomes))
    for lr in linhas_padrao:
        print(linha(lr, extras_nomes))

    # ---- diagnostico rico (MFE/MAE, atraso realizado, direcao, censura) -----
    for rotulo in ("IS", "OOS"):
        resultados_dia = resultados_por_janela[rotulo]
        trades = todos_trades_por_janela[rotulo]
        resumo = resumo_texto(trades)
        rec_capital = sum(r["ordens_recusadas_por_capital_result"] for r in resultados_dia)
        prazo = sum(r["n_prazo_estourado"] for r in resultados_dia)
        armadas = sum(r["n_ordens_armadas"] for r in resultados_dia)
        wiped = sum(1 for r in resultados_dia if r["wiped_out_at"] is not None)
        print(f"\n--- {rotulo}: diagnostico ({resumo.get('n', 0)} trades, "
              f"{len(resultados_dia)} pregoes elegiveis rodados) ---")
        print(f"  ordens armadas: {armadas}  recusadas_por_capital: {rec_capital}  "
              f"prazo_estourado: {prazo}  pregoes com conta zerada: {wiped}")
        if resumo.get("n", 0) == 0:
            print("  nenhum trade nesta janela")
            continue
        for k, v in resumo.items():
            print(f"  {k}: {v}")

    # ---- csv para inspecao ---------------------------------------------
    todas = pd.DataFrame(
        [t for rot in ("IS", "OOS") for t in todos_trades_por_janela[rot]])
    if not todas.empty:
        todas.to_csv(SAIDA / "trades.csv", index=False, encoding="utf-8")
        print(f"\n[gap_fade] {len(todas)} trades -> {SAIDA / 'trades.csv'}")
    sess.to_csv(SAIDA / "sessoes_gap.csv", index=False, encoding="utf-8")
    print(f"[gap_fade] {len(sess)} pregoes -> {SAIDA / 'sessoes_gap.csv'}")


if __name__ == "__main__":
    main()
