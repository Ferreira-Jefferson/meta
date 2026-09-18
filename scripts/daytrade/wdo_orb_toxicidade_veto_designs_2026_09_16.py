"""VETO POR TOXICIDADE -- DOIS DESENHOS QUE CANCELAM, NAO ADIAM (2026-09-16).

## Por que este script existe

`wdo_orb_toxicidade_fluxo_veto_2026_09_16.py` testou "espera 120s depois do
pico de toxicidade e tenta de novo" no `wdo_orb`. Resultado: NULO -- como a
ordem de entrada tem `entrada_ttl_bars=5000` (prazo efetivamente infinito),
em 3 dos 5 pregoes a MESMA entrada aconteceu de qualquer jeito, so' atrasada.
O filtro mudou o QUANDO, nunca o SE. Efeito agregado: R$0,50 de diferenca.

Este script reaproveita a MESMA calibracao de toxicidade (corte top-decil
0,7193, calibrado em 08-28, congelado -- NAO recalibrado aqui) e testa DOIS
desenhos que efetivamente podem mudar o SE, nao so' o QUANDO:

  DESENHO A ("cancela_excursao") -- quando o rompimento (ou o fade) dispara
    durante um pico de toxicidade (janela de ~120s pos-pico, mesmo corte/
    janela do script anterior), a excursao ATUAL de preco para fora da faixa
    morre PERMANENTEMENTE: nenhuma nova tentativa nesse MESMO lado e' aceita
    enquanto o preco continuar fora da faixa. So' revive quando o preco volta
    para dentro de [range_lo, range_hi] e rompe de novo depois -- ai' e' uma
    excursao NOVA (id novo), com direito a nova checagem de toxicidade do
    zero. Isto e' estruturalmente diferente do script anterior: la', o
    proprio motor reagia a cada tick e re-tentava a MESMA excursao ate' o
    veto expirar; aqui a excursao cancelada fica morta ate' o preco
    fisicamente sair e voltar a faixa.

  DESENHO B ("pula_dia") -- filtro grosso, no nivel do PREGAO: se algum pico
    de toxicidade (cruzar o corte) acontecer entre a abertura e a 1a
    tentativa de rompimento do dia (cobrindo tanto os `range_minutos=15`
    de formacao da faixa quanto os minutos seguintes ate' a 1a ordem, por
    mais que demorem), o robo NAO opera nada naquele pregao -- nem
    rompimento nem fade. Testa a hipotese "o dia ja' nasceu ruidoso demais"
    em vez de reagir tick a tick.

Ambos tocam SO' `EnterLimit` de abertura (rompimento e fade) -- stop, saida
por alvo, `AdjustTarget` e fechamento de posicao aberta nunca sao tocados,
igual ao script anterior.

## A mesma limitacao de dado do script anterior -- vale identica aqui

So' 5 pregoes tem `flags` de compra/venda CONFIAVEL no repo: 2026-08-28
(dia de calibracao, autoajustado) e 2026-09-08..11 (4 pregoes de
"confirmacao", corte congelado sem recalibrar). NAO e' a IS/OOS oficial de
72/51 pregoes do `wdo_orb`. O veredito tem de ser do tamanho da amostra
(5 pregoes), nao do tamanho da hipotese.

## Reaproveitamento -- nada de calibracao nova

Toda a mecanica de dado/toxicidade (`carregar_ticks_dia`,
`negocios_classificados`, `serie_toxicidade`, `gatilhos_de_veto`,
`indice_gatilho_ativo`, `calibra`) vem por IMPORT de
`wdo_orb_toxicidade_fluxo_veto_2026_09_16.py` -- o mesmo corte 0,7193, a
mesma janela de veto de 120s, o mesmo peso 3x para negocios >= p90 de
tamanho. So' o MECANISMO de veto (o que a estrategia faz quando a
toxicidade dispara) e' novo.

Uso: `python -u scripts/daytrade/wdo_orb_toxicidade_veto_designs_2026_09_16.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from market_data_intraday.tick_bars import ticks_to_degenerate_bars  # noqa: E402
from strategy.daytrade.base import EnterLimit  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wdo_orb_toxicidade_fluxo_veto_2026_09_16 import (  # noqa: E402
    CAPITAL_PARTIDA_BRL, DIA_CALIBRACAO, DIAS_CONFIRMACAO, TODOS_OS_DIAS,
    WdoOrbInstrumentado, calibra, carregar_ticks_dia, gatilhos_de_veto,
    indice_gatilho_ativo, monta_config, negocios_classificados,
    serie_toxicidade,
)

SAIDA = RAIZ / "scratch" / "wdo_orb_toxicidade_designs_2026_09_16"


# ---------------------------------------------------------------------------
# helper -- "houve toxicidade ate' agora?" (para o desenho B)
# ---------------------------------------------------------------------------

def houve_toxicidade_ate(ts, gatilhos: np.ndarray) -> bool:
    """Existe algum gatilho de toxicidade com timestamp <= `ts`? Causal:
    so' olha o passado. Diferente de `indice_gatilho_ativo`, que restringe a
    uma janela de 120s -- aqui e' "aconteceu alguma vez ate' agora", sem
    prazo de validade, porque o desenho B decide uma vez so' por pregao."""
    if gatilhos.size == 0:
        return False
    ts64 = np.datetime64(pd.Timestamp(ts).tz_convert("UTC").tz_localize(None), "ns")
    return bool((gatilhos <= ts64).any())


# ---------------------------------------------------------------------------
# DESENHO A -- cancela a EXCURSAO inteira, nao so' a tentativa
# ---------------------------------------------------------------------------

@dataclass
class WdoOrbCancelaExcursao(WdoOrbInstrumentado):
    """Rompimento/fade vetado por toxicidade morre PERMANENTEMENTE enquanto
    o preco continuar na mesma excursao (fora da faixa, do mesmo lado). So'
    revive quando o preco volta para dentro de [range_lo, range_hi] e rompe
    de novo -- uma excursao NOVA, `_exc_id` incrementado, toxicidade
    reavaliada do zero. Nao e' "espera e tenta de novo": e' "essa
    oportunidade morreu, a proxima e' outra pergunta"."""

    ativo: bool = True
    _gatilhos: np.ndarray = field(default_factory=lambda: np.array([], dtype="datetime64[ns]"),
                                   init=False, repr=False)
    _vetos: list = field(default_factory=list, init=False, repr=False)
    #: lado da excursao ATUAL fora da faixa: "alta", "baixa" ou None (preco
    #: dentro de [range_lo, range_hi]).
    _exc_lado: str | None = field(default=None, init=False, repr=False)
    #: a excursao atual ja' foi vetada (e permanece morta ate' o lado mudar)?
    _exc_morta: bool = field(default=False, init=False, repr=False)
    #: contador de excursoes no pregao -- so' para o log/depuracao.
    _exc_id: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        super().on_session_start(session_date)
        self._exc_lado = None
        self._exc_morta = False
        self._exc_id = 0

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        if not self.ativo:
            return super().on_bar(ts, bar, positions, session_pnl_brl)

        # --- atualiza o lado da excursao ATUAL, ANTES de deixar o pai agir --
        # (so' depois que a faixa existe -- antes disso nao ha' "fora da
        # faixa" que faca sentido).
        if self._range_hi is not None and self._range_lo is not None:
            if bar.close > self._range_hi:
                lado_agora = "alta"
            elif bar.close < self._range_lo:
                lado_agora = "baixa"
            else:
                lado_agora = None
            if lado_agora != self._exc_lado:
                self._exc_lado = lado_agora
                self._exc_morta = False  # excursao nova (ou voltou pra dentro): vida nova
                if lado_agora is not None:
                    self._exc_id += 1

        antes = (self._armou_hoje, self._limite_posto, self._lado_primeiro,
                 self._fades_no_dia)
        n_log = len(self._log_ordens)
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)

        saida = []
        for a in acoes:
            if not isinstance(a, EnterLimit):
                saida.append(a)
                continue
            ordem = self._log_ordens[-1] if len(self._log_ordens) > n_log else None
            if ordem is None:
                saida.append(a)
                continue

            if self._exc_morta:
                # ja' vetada antes, MESMA excursao -- descarta sem nem
                # reavaliar toxicidade (ela ja' foi julgada e morreu).
                cancelar = True
            else:
                cancelar = indice_gatilho_ativo(ts, self._gatilhos) >= 0

            if not cancelar:
                saida.append(a)
                continue

            if self._exc_morta and self._vetos and self._vetos[-1]["exc_id"] == self._exc_id:
                self._vetos[-1]["tentativas"] += 1
                self._vetos[-1]["ts_fim"] = ts
            else:
                self._exc_morta = True
                self._vetos.append({
                    "ts": ts, "ts_fim": ts, "exc_id": self._exc_id,
                    "tipo": ordem["tipo"], "side": ordem["side"], "tentativas": 1,
                })
            # a ordem nunca existiu: desfaz o estado que o pai marcou.
            self._log_ordens.pop()
            (self._armou_hoje, self._limite_posto, self._lado_primeiro,
             self._fades_no_dia) = antes
        return saida


# ---------------------------------------------------------------------------
# DESENHO B -- pula o PREGAO inteiro se houve pico antes da 1a tentativa
# ---------------------------------------------------------------------------

@dataclass
class WdoOrbPulaDia(WdoOrbInstrumentado):
    """Se um pico de toxicidade acontecer em algum momento entre a abertura
    do pregao e a 1a tentativa de rompimento (cobre a formacao da faixa E os
    minutos seguintes ate' a 1a ordem, por mais que demorem), o robo nao
    opera NADA no pregao inteiro -- nem rompimento, nem fade. Decisao tomada
    UMA VEZ, na 1a tentativa (ou no 1o pico, o que vier primeiro)."""

    ativo: bool = True
    _gatilhos: np.ndarray = field(default_factory=lambda: np.array([], dtype="datetime64[ns]"),
                                   init=False, repr=False)
    _pregao_vetado: bool = field(default=False, init=False, repr=False)
    _decisao_tomada: bool = field(default=False, init=False, repr=False)
    _motivo: dict | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        super().on_session_start(session_date)
        self._pregao_vetado = False
        self._decisao_tomada = False
        self._motivo = None

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        if not self.ativo:
            return super().on_bar(ts, bar, positions, session_pnl_brl)

        if self._pregao_vetado:
            return []

        if not self._decisao_tomada and houve_toxicidade_ate(ts, self._gatilhos):
            # pico ANTES de qualquer tentativa de rompimento -- pula o dia
            # inteiro, sem nem deixar o pai formar a faixa/tentar nada mais.
            self._decisao_tomada = True
            self._pregao_vetado = True
            self._motivo = {"ts_pico": ts, "fase": (
                "formacao_da_faixa"
                if self._open_ts is not None and (ts - self._open_ts) < pd.Timedelta(minutes=self.range_minutos)
                else "espera_pos_faixa")}
            return []

        n_log = len(self._log_ordens)
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)

        if not self._decisao_tomada and len(self._log_ordens) > n_log:
            # 1a tentativa de rompimento aconteceu sem pico antes dela --
            # janela de decisao fecha, o pregao segue LIBERADO dali em diante
            # (picos DEPOIS disso nao acionam o desenho B -- isso e' o
            # desenho A).
            self._decisao_tomada = True
        return acoes


# ---------------------------------------------------------------------------
# roda 1 pregao -- BASE, A e B, mesmo capital, mesma barra, mesma toxicidade
# ---------------------------------------------------------------------------

def roda_pregao(dia: str, corte: float, p90_tamanho: float) -> dict:
    ticks = carregar_ticks_dia(dia)
    if ticks.empty:
        return {"dia": dia, "erro": "sem ticks"}
    bars = ticks_to_degenerate_bars(ticks)
    negocios = negocios_classificados(ticks)
    tox = serie_toxicidade(negocios, p90_tamanho)
    gatilhos = gatilhos_de_veto(tox, corte)

    strat_base = WdoOrbInstrumentado()
    res_base = run_intraday_backtest(bars, strat_base, monta_config(strat_base, CAPITAL_PARTIDA_BRL))

    strat_a = WdoOrbCancelaExcursao()
    strat_a._gatilhos = gatilhos
    res_a = run_intraday_backtest(bars, strat_a, monta_config(strat_a, CAPITAL_PARTIDA_BRL))

    strat_b = WdoOrbPulaDia()
    strat_b._gatilhos = gatilhos
    res_b = run_intraday_backtest(bars, strat_b, monta_config(strat_b, CAPITAL_PARTIDA_BRL))

    def extrai(nome, strat, res):
        ordens = sorted(strat._log_ordens, key=lambda o: o["sinal_ts"])
        linhas = []
        caixa = CAPITAL_PARTIDA_BRL
        for t in sorted(res.trades, key=lambda x: x.entry_ts):
            ordem = None
            for o in ordens:
                if o["sinal_ts"] <= t.entry_ts:
                    ordem = o
                else:
                    break
            razao = t.exit_reason.value if hasattr(t.exit_reason, "value") else str(t.exit_reason)
            entry_brt = pd.Timestamp(t.entry_ts).tz_convert("America/Sao_Paulo")
            linhas.append({
                "celula": nome, "data": dia,
                "entrada_utc": pd.Timestamp(t.entry_ts).strftime("%H:%M:%S.%f"),
                "entrada_brt": entry_brt.strftime("%H:%M:%S"),
                "tipo": ordem["tipo"] if ordem else "?", "side": t.side,
                "pnl_brl": round(t.pnl_brl, 2),
                "exit_reason": razao,
                "caixa_antes": round(caixa, 2),
            })
            caixa += t.pnl_brl
        caixa_min = min([CAPITAL_PARTIDA_BRL] + [l["caixa_antes"] + l["pnl_brl"] for l in linhas])
        return linhas, caixa_min

    linhas_base, caixa_min_base = extrai("BASE", strat_base, res_base)
    linhas_a, caixa_min_a = extrai("A", strat_a, res_a)
    linhas_b, caixa_min_b = extrai("B", strat_b, res_b)

    vetos_a = [{"dia": dia, "ts": pd.Timestamp(v["ts"]).tz_convert("America/Sao_Paulo").strftime("%H:%M:%S"),
                "tipo": v["tipo"], "side": v["side"], "tentativas": v["tentativas"]}
               for v in strat_a._vetos]

    veto_b = {"dia": dia, "pulado": int(strat_b._pregao_vetado),
              "motivo_fase": (strat_b._motivo or {}).get("fase", ""),
              "ts_pico": (pd.Timestamp(strat_b._motivo["ts_pico"]).tz_convert("America/Sao_Paulo").strftime("%H:%M:%S")
                          if strat_b._motivo else "")}

    def resumo(nome, linhas, caixa_min):
        n = len(linhas)
        liq = sum(l["pnl_brl"] for l in linhas)
        win = 100.0 * sum(1 for l in linhas if l["pnl_brl"] > 0) / n if n else float("nan")
        dd = round(max(0.0, CAPITAL_PARTIDA_BRL - caixa_min), 2)
        return {f"{nome}_trades": n, f"{nome}_liquido": round(liq, 2),
                f"{nome}_win_pct": round(win, 1), f"{nome}_maxdd": dd}

    res_dict = {"dia": dia}
    res_dict.update(resumo("base", linhas_base, caixa_min_base))
    res_dict.update(resumo("a", linhas_a, caixa_min_a))
    res_dict.update(resumo("b", linhas_b, caixa_min_b))
    res_dict["vetos_a"] = len(vetos_a)
    res_dict["b_pulado"] = veto_b["pulado"]

    return {
        "dia": dia, "erro": "",
        "trades": linhas_base + linhas_a + linhas_b,
        "vetos_a": vetos_a,
        "veto_b": veto_b,
        "n_gatilhos_toxicidade": int(gatilhos.size),
        "resumo": res_dict,
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    corte, p90_tamanho = calibra()
    print(f"[toxicidade] calibrado em {DIA_CALIBRACAO} (IS/exploracao, autoajustado, REAPROVEITADO):")
    print(f"  p90 tamanho do negocio = {p90_tamanho:.1f} contratos")
    print(f"  corte top-decil de toxicidade = {corte:.4f}")
    print(f"[toxicidade] congelado, aplicado sem recalibrar aos "
          f"{len(DIAS_CONFIRMACAO)} pregoes de confirmacao (09-08..09-11)\n", flush=True)

    resultados = {}
    with ProcessPoolExecutor(max_workers=min(5, len(TODOS_OS_DIAS))) as pool:
        futuros = {pool.submit(roda_pregao, d, corte, p90_tamanho): d for d in TODOS_OS_DIAS}
        for fut in as_completed(futuros):
            dia = futuros[fut]
            try:
                r = fut.result()
            except Exception as exc:
                print(f"[{dia}] ERRO: {exc!r}", flush=True)
                continue
            resultados[dia] = r
            if r["erro"]:
                print(f"[{dia}] {r['erro']}", flush=True)
                continue
            s = r["resumo"]
            print(f"[{dia}] gatilhos={r['n_gatilhos_toxicidade']:>4} vetos_A={s['vetos_a']:>2} "
                  f"pulado_B={'SIM' if s['b_pulado'] else 'nao'} | "
                  f"BASE {s['base_trades']:>2}op win{s['base_win_pct']:>5}% liq R${s['base_liquido']:>9,.2f} | "
                  f"A {s['a_trades']:>2}op win{s['a_win_pct']:>5}% liq R${s['a_liquido']:>9,.2f} | "
                  f"B {s['b_trades']:>2}op win{s['b_win_pct']:>5}% liq R${s['b_liquido']:>9,.2f}", flush=True)

    todas_trades = pd.concat(
        [pd.DataFrame(r["trades"]) for r in resultados.values() if r["erro"] == ""],
        ignore_index=True)
    todos_vetos_a = pd.concat(
        [pd.DataFrame(r["vetos_a"]) for r in resultados.values() if r["erro"] == "" and r["vetos_a"]],
        ignore_index=True) if any(r.get("vetos_a") for r in resultados.values()) else pd.DataFrame()
    veto_b_df = pd.DataFrame([r["veto_b"] for r in resultados.values() if r["erro"] == ""])
    todas_trades.to_csv(SAIDA / "trades.csv", index=False, encoding="utf-8")
    todos_vetos_a.to_csv(SAIDA / "vetos_a.csv", index=False, encoding="utf-8")
    veto_b_df.to_csv(SAIDA / "veto_b.csv", index=False, encoding="utf-8")

    # ---- contrafactual A: o que BASE fez com as excursoes que A cancelou --
    print("\n" + "=" * 100)
    print("CONTRAFACTUAL A -- o que a BASE (sem veto) fez com as operacoes que A cancelou")
    print("  (casado por (data, entrada_brt) -- so' a 1a tentativa de cada excursao cancelada")
    print("   compartilha timestamp com a BASE; tentativas repetidas da MESMA excursao morta")
    print("   nao geram novo instante de comparacao e ficam so' no contador `tentativas`)")
    print("=" * 100)
    base = todas_trades[todas_trades.celula == "BASE"].set_index(["data", "entrada_brt"])
    a = todas_trades[todas_trades.celula == "A"].set_index(["data", "entrada_brt"])
    sumiram_a = base.loc[base.index.difference(a.index)]
    surgiram_a = a.loc[a.index.difference(base.index)]
    n_van = len(sumiram_a)
    n_ganh = int((sumiram_a.pnl_brl > 0).sum()) if n_van else 0
    n_perd = n_van - n_ganh
    print(f"sumiram (BASE tinha, A cancelou -- MESMA entrada) : {n_van} op, "
          f"R${sumiram_a.pnl_brl.sum() if n_van else 0.0:+,.2f} | "
          f"{n_ganh} eram GANHADORAS (R${sumiram_a[sumiram_a.pnl_brl > 0].pnl_brl.sum() if n_ganh else 0.0:+,.2f}), "
          f"{n_perd} eram PERDEDORAS (R${sumiram_a[sumiram_a.pnl_brl <= 0].pnl_brl.sum() if n_perd else 0.0:+,.2f})")
    print(f"surgiram (A tem, BASE nao tinha -- reordenacao de estado do dia): {len(surgiram_a)} op, "
          f"R${surgiram_a.pnl_brl.sum():+,.2f}")

    # ---- contrafactual B: dias pulados -- o que a BASE fez naqueles dias --
    print("\n" + "=" * 100)
    print("CONTRAFACTUAL B -- o que a BASE fez nos PREGOES que B pulou inteiros")
    print("=" * 100)
    dias_pulados = veto_b_df[veto_b_df.pulado == 1]["dia"].tolist()
    if dias_pulados:
        sub = base.reset_index()
        sub = sub[sub.data.isin(dias_pulados)]
        for _, row in veto_b_df[veto_b_df.pulado == 1].iterrows():
            dia = row["dia"]
            ops_dia = sub[sub.data == dia]
            liq = ops_dia.pnl_brl.sum()
            print(f"  {dia}: B pulou (pico as {row['ts_pico']} BRT, fase={row['motivo_fase']}) -- "
                  f"BASE fez {len(ops_dia)} op naquele dia, liquido R${liq:+,.2f}, "
                  f"{int((ops_dia.pnl_brl > 0).sum())} ganhadoras, {int((ops_dia.pnl_brl <= 0).sum())} perdedoras")
    else:
        print("  nenhum pregao foi pulado por B nesta amostra")

    # ---- agregado, separando calibracao (autoajustado) de confirmacao -----
    for rotulo, dias in [("CALIBRACAO (08-28, autoajustado -- NAO conta como prova)", [DIA_CALIBRACAO]),
                         ("CONFIRMACAO (09-08..09-11, corte congelado)", DIAS_CONFIRMACAO)]:
        print("\n" + "=" * 100)
        print(rotulo)
        print("=" * 100)
        sub = todas_trades[todas_trades.data.isin(dias)]
        for cel in ("BASE", "A", "B"):
            ops = sub[sub.celula == cel]
            n = len(ops)
            liq = ops.pnl_brl.sum()
            win = 100.0 * (ops.pnl_brl > 0).mean() if n else float("nan")
            print(f"  {cel}: {n:>3} trades | liquido R${liq:>10,.2f} | win {win:>5.1f}% | "
                  f"R$/op {liq / n if n else float('nan'):>7.2f}")
        v_a = todos_vetos_a[todos_vetos_a.dia.isin(dias)] if not todos_vetos_a.empty else pd.DataFrame()
        n_pulados_b = int(veto_b_df[veto_b_df.dia.isin(dias)]["pulado"].sum())
        print(f"  vetos A (excursoes canceladas): {len(v_a)}  |  pregoes pulados por B: {n_pulados_b}/{len(dias)}")

    print(f"\n[toxicidade] arquivos em {SAIDA}")


if __name__ == "__main__":
    main()
