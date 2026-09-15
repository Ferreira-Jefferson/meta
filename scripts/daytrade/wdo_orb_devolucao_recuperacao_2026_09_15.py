"""DEVOLUCAO / RECUPERACAO (2026-09-15) -- cortar a operacao que ANDOU e VOLTOU.

Pedido do dono, textual:

    "sempre que o preco subir a 70% do alvo, mas voltar a 55%, fechamos a
     operacao / sempre que ele for em direcao ao stop for a 70% do stop e
     depois voltar a 50%, fechamos a operacao / 3 testes, um de cada e um
     juntos"

E' o mesmo criterio que ele declarou na rodada de 14/09 -- "melhor ganhar
pouco, mas ganhar sempre, do que ganhar muito correndo o risco de entregar
boa parte por mercado" -- aplicado agora DENTRO da operacao, e nao na
geometria dela. As duas regras atacam exatamente o que a coleta de 14/09
mostrou ser o problema: o vencedor tipico andava 26 ticks (MFE mediana)
para um alvo pedido de 53, e so' 10,7% chegavam ao alvo. O robo enxerga
lucro e devolve.

## A leitura dos numeros (declarada, porque o enunciado admite duas)

Tudo medido A PARTIR DO PRECO DE ENTRADA, em fracao da distancia geometrica:

    REGRA A (devolucao do lucro)
        arma  quando a favor >= 0,70 x distancia_do_alvo
        corta quando, ja' armada, a favor <= 0,55 x distancia_do_alvo
        -> sai com lucro de 55% do alvo, em vez de esperar os 100%

    REGRA B (recuperacao da perda)
        arma  quando contra   >= 0,70 x distancia_do_stop
        corta quando, ja' armada, contra   <= 0,50 x distancia_do_stop
        -> sai com prejuizo de metade do stop, em vez de arriscar o stop cheio

A outra leitura possivel de "voltar a 55%" seria "devolver 55% da excursao".
Nao e' a adotada: os dois numeros do dono estao na mesma escala (70 e 55, 70
e 50), o que so' faz sentido se ambos medirem a mesma coisa -- distancia
percorrida desde a entrada.

`distancia_do_alvo` e `distancia_do_stop` sao lidas da propria posicao na
PRIMEIRA barra em que ela aparece, antes de o corte de relogio de 60 min
mexer no alvo (`saida_limite_minutos` -> `AdjustTarget`). Assim a regra mede
contra a geometria ORIGINAL da operacao, que e' o que o dono descreveu.

## As 4 celulas -- as 3 pedidas mais a producao ao lado

    BASE     producao de hoje (alvo 1,5x, teto de fade 1, stop 20-30)
    A        so' a devolucao do lucro
    B        so' a recuperacao da perda
    A+B      as duas juntas

A producao entra porque as tres pedidas nao se comparam entre si: sem ela
nao da' para saber se a melhor das tres e' melhor que NAO fazer nada.

Quando as duas estao ligadas, A dispara ANTES de B por construcao -- o
gatilho de A exige ter chegado a 70% do alvo, e o corte de A (55% do alvo,
ainda positivo) e' cruzado muito antes de o preco descer aos 70% do stop.
A+B nao e' "a soma das duas", e' "A, e B so' nas operacoes que A nunca armou".

## O custo que esta regra paga, declarado

O corte sai a MERCADO (`Exit`), nao por ordem-limite. Isso e' exececao ao
desenho fechado do CLAUDE.md pelo mesmo motivo que o stop e': **e' protecao,
e protecao nao espera fila.** O motor cobra `slippage_ticks` nessa saida, e o
`Exit` decidido na barra t executa na abertura da barra t+1 (anti-look-ahead
do motor) -- em base de tick, "t+1" e' o proximo negocio. O custo esta na
conta; nao ha' desconto.

## O que decide

Mesma disciplina das rodadas anteriores, e ela e' o ponto: tem de melhorar
nas DUAS janelas congeladas independentes (IS e OOS_LIMPO) e passar no
bootstrap emparelhado por pregao contra a producao, piso 90%. A janela
DESCOBERTA aparece na tabela mas NAO vota -- foi ela que gerou a hipotese.

Uso: `python -u scripts/daytrade/wdo_orb_devolucao_recuperacao_2026_09_15.py`
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from strategy.daytrade.base import Exit  # noqa: E402
from wdo_orb_4semanas_coleta_2026_09_14 import (  # noqa: E402
    CAPITAL_PARTIDA_BRL, TICK_SIZE, WdoOrbInstrumentado, carregar_bars,
    excursao, monta_config,
)
from wdo_orb_fade_agitacao_is_oos_2026_09_14 import (  # noqa: E402
    JANELAS, classifica_saida, pregoes_da_janela,
)
from wdo_orb_geometria_is_oos_2026_09_14 import resumo_celula  # noqa: E402

BASE = "BASE"
CELULAS = [
    (BASE,  dict(corta_devolucao_alvo=False, corta_recuperacao_stop=False)),
    ("A",   dict(corta_devolucao_alvo=True,  corta_recuperacao_stop=False)),
    ("B",   dict(corta_devolucao_alvo=False, corta_recuperacao_stop=True)),
    ("A+B", dict(corta_devolucao_alvo=True,  corta_recuperacao_stop=True)),
]
N_BOOT = 5000
JANELAS_QUE_VOTAM = ["IS", "OOS_LIMPO"]
SAIDA = RAIZ / "scratch" / "wdo_orb_4semanas_2026_09_14"
MAX_WORKERS = min(12, (os.cpu_count() or 4))


# ---------------------------------------------------------------------------
# a estrategia com as duas regras -- subclasse, a producao nao e' tocada
# ---------------------------------------------------------------------------

@dataclass
class WdoOrbDevolucao(WdoOrbInstrumentado):
    """`WdoOrb` de producao + os dois cortes por excursao. Cada regra e' um
    booleano proprio, entao a mesma classe serve as 4 celulas."""

    corta_devolucao_alvo: bool = False
    corta_recuperacao_stop: bool = False
    #: fracoes da distancia geometrica, medidas a partir da ENTRADA
    arma_alvo: float = 0.70
    corta_alvo: float = 0.55
    arma_stop: float = 0.70
    corta_stop: float = 0.50

    _pos_ts: object = field(default=None, init=False, repr=False)
    _d_stop: float = field(default=0.0, init=False, repr=False)
    _d_alvo: float = field(default=0.0, init=False, repr=False)
    _armou_a: bool = field(default=False, init=False, repr=False)
    _armou_b: bool = field(default=False, init=False, repr=False)
    _cortes: list = field(default_factory=list, init=False, repr=False)

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        if positions and (self.corta_devolucao_alvo or self.corta_recuperacao_stop):
            pos = positions[0]
            if pos.entry_ts != self._pos_ts:
                # primeira barra desta posicao: congela a geometria ORIGINAL,
                # antes de o corte de relogio de 60 min mexer no alvo
                self._pos_ts = pos.entry_ts
                self._armou_a = self._armou_b = False
                self._d_stop = (abs(pos.entry_price - pos.current_stop)
                                if pos.current_stop is not None else 0.0)
                self._d_alvo = (abs(pos.current_target - pos.entry_price)
                                if pos.current_target is not None else 0.0)
            if self._d_stop > 0.0 and self._d_alvo > 0.0:
                if pos.side == "long":
                    pico_fav = bar.high - pos.entry_price
                    pico_adv = pos.entry_price - bar.low
                    fav = bar.close - pos.entry_price
                else:
                    pico_fav = pos.entry_price - bar.low
                    pico_adv = bar.high - pos.entry_price
                    fav = pos.entry_price - bar.close
                adv = -fav

                if self.corta_devolucao_alvo:
                    if pico_fav >= self.arma_alvo * self._d_alvo:
                        self._armou_a = True
                    if self._armou_a and fav <= self.corta_alvo * self._d_alvo:
                        return self._corta(ts, pos, "devolucao_alvo",
                                           fav / self._d_alvo)
                if self.corta_recuperacao_stop:
                    if pico_adv >= self.arma_stop * self._d_stop:
                        self._armou_b = True
                    if self._armou_b and adv <= self.corta_stop * self._d_stop:
                        return self._corta(ts, pos, "recuperacao_stop",
                                           -adv / self._d_stop)
        return super().on_bar(ts, bar, positions, session_pnl_brl)

    def _corta(self, ts, pos, regra: str, fracao: float) -> list:
        self._cortes.append({
            "entry_ts": pos.entry_ts, "regra": regra,
            "decidiu_utc": pd.Timestamp(ts).strftime("%H:%M:%S"),
            "fracao_no_corte": round(fracao, 3),
            "minutos_ate_corte": round(
                (pd.Timestamp(ts) - pd.Timestamp(pos.entry_ts)).total_seconds() / 60.0, 1),
        })
        self._pos_ts = None          # a proxima posicao recomeca do zero
        return [Exit(reason=regra)]


# ---------------------------------------------------------------------------

def roda_pregao(dia: str) -> list[dict]:
    """UM pregao x as 4 celulas. Caixa R$375 do zero, como toda a rodada."""
    bars = carregar_bars(dia, dia)
    if bars.empty:
        return []
    linhas = []
    for nome, kwargs in CELULAS:
        strat = WdoOrbDevolucao(**kwargs)
        cfg = monta_config(strat, CAPITAL_PARTIDA_BRL)
        res = run_intraday_backtest(bars, strat, cfg)
        ordens = sorted(strat._log_ordens, key=lambda o: o["sinal_ts"])
        cortes = {c["entry_ts"]: c for c in strat._cortes}
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
            c = cortes.get(t.entry_ts)
            saida = classifica_saida(razao, pnl_ticks, alvo)
            if c is not None and razao == "signal":
                saida = c["regra"]
            linhas.append({
                "celula": nome, "data": dia, "op_do_dia": i + 1,
                "entrada_utc": pd.Timestamp(t.entry_ts).strftime("%H:%M:%S"),
                "saida_utc": pd.Timestamp(t.exit_ts).strftime("%H:%M:%S"),
                "tipo": ordem["tipo"] if ordem else "?", "side": t.side,
                "pnl_brl": round(t.pnl_brl, 2), "pnl_ticks": round(pnl_ticks, 1),
                "alvo_ticks": alvo,
                "stop_ticks": ordem["stop_ticks"] if ordem else float("nan"),
                "saida_efetiva": saida,
                "regra_cortou": c["regra"] if c else "",
                "min_ate_corte": c["minutos_ate_corte"] if c else float("nan"),
                "mfe_ticks": round(exc["mfe_ticks"], 1),
                "mae_ticks": round(exc["mae_ticks"], 1),
            })
    return linhas


def bootstrap(df: pd.DataFrame, cand: str) -> dict:
    """Reamostra PREGOES (nao operacoes) com reposicao, emparelhado: a mesma
    lista de dias serve as duas celulas, entao a comparacao e' sempre sobre o
    mesmo mercado. Duas operacoes do mesmo dia compartilham faixa, regime e
    ate' o lado -- trata-las como independentes inflaria a confianca."""
    base = df[df.janela.isin(JANELAS_QUE_VOTAM)]
    dias = base.data.unique()
    agr = {}
    for cel in (BASE, cand):
        g = base[base.celula == cel].groupby("data")["pnl_brl"]
        agr[cel] = pd.DataFrame({"soma": g.sum(), "n": g.count()}).reindex(dias).fillna(0.0)
    rng = np.random.default_rng(20260915)
    g_rs = g_pr = g_ambos = 0
    d_rs, d_pr = [], []
    for _ in range(N_BOOT):
        idx = rng.integers(0, len(dias), len(dias))
        r = {}
        for cel in (BASE, cand):
            somas = agr[cel]["soma"].values[idx]
            ns = agr[cel]["n"].values[idx]
            r[cel] = {"rs": somas.sum() / ns.sum() if ns.sum() else np.nan,
                      "pr": 100.0 * (somas > 0).sum() / max((ns > 0).sum(), 1)}
        a = r[cand]["rs"] - r[BASE]["rs"]
        b = r[cand]["pr"] - r[BASE]["pr"]
        d_rs.append(a); d_pr.append(b)
        if a > 0: g_rs += 1
        if b > 0: g_pr += 1
        if a > 0 and b > 0: g_ambos += 1
    return {"rs_pct": 100.0 * g_rs / N_BOOT, "pr_pct": 100.0 * g_pr / N_BOOT,
            "ambos_pct": 100.0 * g_ambos / N_BOOT,
            "d_rs": float(np.median(d_rs)), "d_pr": float(np.median(d_pr)),
            "ic_rs": (float(np.percentile(d_rs, 2.5)), float(np.percentile(d_rs, 97.5))),
            "ic_pr": (float(np.percentile(d_pr, 2.5)), float(np.percentile(d_pr, 97.5)))}


def contrafactual(df: pd.DataFrame, cand: str) -> pd.DataFrame:
    """O que a producao fez com as MESMAS operacoes que a regra cortou.

    Casa por (data, hora de entrada) -- nao por ordem no dia: cortar mais
    cedo libera o fade mais cedo, entao a 2a operacao pode nem ser a mesma.
    Operacao sem par e' contada a parte, nunca comparada."""
    a = df[df.celula == BASE].set_index(["data", "entrada_utc"])
    b = df[(df.celula == cand) & (df.regra_cortou != "")].set_index(["data", "entrada_utc"])
    comuns = b.index.intersection(a.index)
    linhas = []
    for k in comuns:
        ra, rb = a.loc[k], b.loc[k]
        if isinstance(ra, pd.DataFrame):
            ra = ra.iloc[0]
        if isinstance(rb, pd.DataFrame):
            rb = rb.iloc[0]
        linhas.append({
            "data": k[0], "entrada": k[1], "janela": rb.janela, "regra": rb.regra_cortou,
            "min_ate_corte": rb.min_ate_corte,
            "cortada_pnl": rb.pnl_brl, "cortada_ticks": rb.pnl_ticks,
            "producao_saida": ra.saida_efetiva, "producao_pnl": ra.pnl_brl,
            "delta": round(rb.pnl_brl - ra.pnl_brl, 2),
        })
    orfas = len(b.index.difference(a.index))
    d = pd.DataFrame(linhas)
    if not d.empty:
        d.attrs["orfas"] = orfas
    return d


def main() -> None:
    dias_por_janela, todos = {}, []
    for rotulo, ini, fim, _ in JANELAS:
        dias = pregoes_da_janela(ini, fim)
        dias_por_janela[rotulo] = set(dias)
        todos.extend(dias)
    print(f"[devolucao] {len(todos)} pregoes x {len(CELULAS)} celulas "
          f"({[c for c, _ in CELULAS]}), {MAX_WORKERS} processos\n", flush=True)

    from concurrent.futures import ProcessPoolExecutor, as_completed
    linhas, feitos = [], 0
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {pool.submit(roda_pregao, d): d for d in todos}
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
    df.to_csv(SAIDA / "96_devolucao_trades.csv", index=False, encoding="utf-8")
    print(f"\n[devolucao] {len(df)} operacoes -> 96_devolucao_trades.csv")

    # ---- 1. quanto cada regra DISPAROU ------------------------------------
    print("\n" + "=" * 120)
    print("1) QUANTAS VEZES CADA REGRA DISPAROU  (se disparou pouco, o resto e' ruido)")
    print("=" * 120)
    disp = []
    for nome, _ in CELULAS:
        if nome == BASE:
            continue
        s = df[df.celula == nome]
        for janela in [j for j, _, _, _ in JANELAS]:
            sj = s[s.janela == janela]
            cortadas = sj[sj.regra_cortou != ""]
            disp.append({
                "celula": nome, "janela": janela, "ops": len(sj),
                "cortadas": len(cortadas),
                "pct": round(100.0 * len(cortadas) / len(sj), 1) if len(sj) else np.nan,
                "por_A": int((cortadas.regra_cortou == "devolucao_alvo").sum()),
                "por_B": int((cortadas.regra_cortou == "recuperacao_stop").sum()),
                "min_mediano": (round(cortadas.min_ate_corte.median(), 1)
                                if len(cortadas) else np.nan),
            })
    print(pd.DataFrame(disp).to_string(index=False))

    # ---- 2. a tabela por janela -------------------------------------------
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
        rep = [k for k, v in assin.items() if list(assin.values()).count(v) > 1]
        if rep:
            print(f"  [EIXO MORTO] celulas identicas nesta janela: {rep}")
    pd.concat(tabelas).to_csv(SAIDA / "97_devolucao_resumo.csv",
                              index=False, encoding="utf-8")

    # ---- 3. o contrafactual: o que a producao fez com a MESMA operacao -----
    print("\n" + "=" * 132)
    print("3) CONTRAFACTUAL -- as operacoes que a regra cortou, e o que a PRODUCAO fez com elas")
    print("=" * 132)
    for nome, _ in CELULAS:
        if nome == BASE:
            continue
        d = contrafactual(df, nome)
        print(f"\n--- celula {nome} ---")
        if d.empty:
            print("  a regra nunca disparou.")
            continue
        d.to_csv(SAIDA / f"98_contrafactual_{nome.replace('+', '_')}.csv",
                 index=False, encoding="utf-8")
        for janela in [j for j, _, _, _ in JANELAS]:
            sj = d[d.janela == janela]
            if sj.empty:
                continue
            melhorou = int((sj.delta > 0).sum())
            print(f"  [{janela}] {len(sj)} cortadas | "
                  f"cortando R${sj.cortada_pnl.sum():+,.2f} contra "
                  f"R${sj.producao_pnl.sum():+,.2f} da producao | "
                  f"delta R${sj.delta.sum():+,.2f} | "
                  f"melhorou em {melhorou}/{len(sj)}")
            destino = sj.producao_saida.value_counts()
            print(f"           o que a producao fazia com elas: {dict(destino)}")
        if d.attrs.get("orfas"):
            print(f"  ({d.attrs['orfas']} cortadas sem par na producao -- "
                  f"operacoes que so' existem nesta celula, nao comparadas)")

    # ---- 4. bootstrap contra a producao -----------------------------------
    print("\n" + "=" * 132)
    print(f"4) BOOTSTRAP EMPARELHADO POR PREGAO contra {BASE} "
          f"({N_BOOT} reamostragens, so' IS+OOS_LIMPO)")
    print("=" * 132)
    for nome, _ in CELULAS:
        if nome == BASE:
            continue
        b = bootstrap(df, nome)
        print(f"\n  {nome} contra {BASE}:")
        print(f"    R$/op maior em          {b['rs_pct']:5.1f}%  "
              f"(mediana {b['d_rs']:+.2f}, IC95 [{b['ic_rs'][0]:+.2f} ; {b['ic_rs'][1]:+.2f}])")
        print(f"    mais pregoes positivos: {b['pr_pct']:5.1f}%  "
              f"(mediana {b['d_pr']:+.2f}pp, IC95 [{b['ic_pr'][0]:+.2f} ; {b['ic_pr'][1]:+.2f}])")
        print(f"    as DUAS ao mesmo tempo: {b['ambos_pct']:5.1f}%")
    print("\n  [piso declarado] 90%. Abaixo disso a vantagem nao sobrevive ao")
    print("  reembaralhamento da propria amostra -- quanto mais a um pregao novo.")
    print(f"\n[devolucao] arquivos em {SAIDA}")


if __name__ == "__main__":
    main()
