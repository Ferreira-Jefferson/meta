"""RATCHET DE STOP (2026-09-15) -- a mesma ideia do dono, SEM fechar a posicao.

## De onde isto vem

Na rodada de hoje de manha as duas regras que o dono pediu foram medidas
(`wdo_orb_devolucao_recuperacao_2026_09_15.py`) e as duas falharam -- mas
falharam de formas OPOSTAS, e e' a assimetria que gerou este teste:

    regra                      que cauda toca          custo (R$/op IS, OOS)
    A  fecha em 55% do alvo    a DIREITA (ganhador)    -8,69 / -4,76
    B  fecha em 50% do stop    a ESQUERDA (perdedor)   +2,64 / -0,62  (empate)

Tocar na direita e' caro; tocar na esquerda e' de graca. Nao e' coincidencia
das duas regras -- e' a forma da distribuicao: o top-3 de operacoes responde
por 28,7% do liquido no IS e 89,8% no OOS. Qualquer regra capaz de fechar uma
dessas antes da hora paga caro, escrita como for.

**O principio que sobrou: mexer so' na esquerda, nunca por teto na direita.**

## O defeito especifico da regra B, que este script corrige

O gatilho dela nao estava errado -- o que ela fazia DEPOIS do gatilho estava.
Ao FECHAR, ela matava as duas especies juntas: das 28 que cortou no IS, 8 eram
operacoes que ja tinham se recuperado e iam fechar no POSITIVO (elas devolveram
R$860 dos R$910 economizados nas outras 20; no OOS, R$625 de R$685).

A versao sem esse defeito e' o MESMO gatilho que nao fecha nada: **sobe o stop
e deixa a operacao viver.** Quem ia perder perde metade igual; quem ia se
recuperar se recupera.

## O gatilho tem de ser de DOIS passos -- descoberto no teste de fumaca

A primeira versao deste script armava num passo so' (contra >= 70% do stop ->
stop sobe para -50%) e era **autodestrutiva**: no instante em que arma, o
preco JA' esta' em -70%, entao um stop em -50% nasce do lado errado do preco
e dispara na barra seguinte. Medido em 2026-09-11: a regra B, que FECHAVA,
saia a -80,50; esse falso ratchet saia a -110,50, porque executava em -21
ticks em vez de -15. Um ratchet cujo nivel novo ja' foi ultrapassado nao e'
protecao, e' uma saida a mercado com nome bonito.

O gatilho correto e' o da propria regra B, de dois passos: **foi a -70% E
VOLTOU a -50%**. So' entao o stop sobe -- e sobe para **-70%**, o pior ponto
ja' visitado, que fica abaixo do preco atual (-50%) e portanto nao dispara
sozinho. Risco cortado em 30% do stop, posicao viva.

(O zero a zero nao tem esse problema: arma com o preco em +70% do alvo, e o
nivel novo -- a entrada -- esta' bem abaixo dele.)

## As 4 celulas

    BASE      producao de hoje (alvo 1,5x, teto de fade 1, stop 20-30)
    R70       foi a -70% do stop e VOLTOU a -50% -> stop sobe para -70%
    BE        a favor >= 70% do alvo             -> stop sobe para o ZERO A ZERO
    R70+BE    as duas

`BE` e' a conversao da regra A pelo mesmo principio: em vez de fechar em 55%
do alvo, tira o risco e deixa as 9 operacoes que iam ao alvo cheio seguirem.

Nenhuma das duas fecha posicao: so' `AdjustStop`, que o motor ja' so' aceita
quando o nivel novo e' MAIS protetor que o atual (`strategy.daytrade.base.
AdjustStop`). Quando as duas disparam, vale a mais protetora -- este script
calcula o nivel e emite UMA ordem, em vez de deixar o motor recusar a outra
em silencio.

## O teto do premio, declarado ANTES de medir

A regra B ja mostrou quanto dinheiro existe na perna esquerda desta
estrategia: **+R$910 no IS e +R$685 no OOS** de economia bruta nas perdedoras
(+8,83 e +10,70 por operacao). Esse e' o TETO da familia inteira. O trabalho
do ratchet e' coletar isso sem pagar os R$860/R$625 que a versao que fecha
pagava. Coletar nada = familia encerrada.

## O criterio de decisao, declarado ANTES de ver o resultado

IS e OOS ja' foram olhados muitas vezes em 14 e 15/09 (alvo, stop, combo,
fade, agitacao, perfil de operacao, achatamento, devolucao/recuperacao). Nao
sao mais janelas cegas; sao janelas GASTAS, e a pressao de comparacao
multipla e' real. Entao esta e' a ULTIMA rodada desta familia, e o criterio
esta congelado aqui em cima:

  1. melhora nas DUAS janelas em R$/op E em pregoes positivos; e
  2. bootstrap emparelhado por pregao >= 90% em pelo menos uma das duas
     metricas, com a outra nao piorando.

Falhou em qualquer uma -> familia ENCERRADA e registrada como tal. A janela
DESCOBERTA aparece na tabela e NAO vota.

Uso: `python -u scripts/daytrade/wdo_orb_ratchet_stop_2026_09_15.py`
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
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
from strategy.daytrade.base import AdjustStop, no_tick  # noqa: E402
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
    (BASE,     dict(ratchet_pos_recuperacao=False, ratchet_zero_a_zero=False)),
    ("R70",    dict(ratchet_pos_recuperacao=True,  ratchet_zero_a_zero=False)),
    ("BE",     dict(ratchet_pos_recuperacao=False, ratchet_zero_a_zero=True)),
    ("R70+BE", dict(ratchet_pos_recuperacao=True,  ratchet_zero_a_zero=True)),
]
N_BOOT = 5000
JANELAS_QUE_VOTAM = ["IS", "OOS_LIMPO"]
SAIDA = RAIZ / "scratch" / "wdo_orb_4semanas_2026_09_14"
MAX_WORKERS = min(12, (os.cpu_count() or 4))


@dataclass
class WdoOrbRatchet(WdoOrbInstrumentado):
    """`WdoOrb` de producao + dois ratchets de stop. Nenhum fecha posicao."""

    ratchet_pos_recuperacao: bool = False
    ratchet_zero_a_zero: bool = False
    #: fracoes da distancia geometrica, medidas a partir da ENTRADA
    arma_stop: float = 0.70      # 1o passo: o quanto o preco foi CONTRA
    volta_stop: float = 0.50     # 2o passo: ate' onde ele voltou
    nivel_novo: float = 0.70     # onde o stop passa a ficar (o pior ja' visto)
    arma_alvo: float = 0.70      # a favor, para armar o zero a zero

    _pos_ts: object = field(default=None, init=False, repr=False)
    _d_stop: float = field(default=0.0, init=False, repr=False)
    _d_alvo: float = field(default=0.0, init=False, repr=False)
    _entrada: float = field(default=0.0, init=False, repr=False)
    _tocou_70: bool = field(default=False, init=False, repr=False)
    _fez_r70: bool = field(default=False, init=False, repr=False)
    _fez_be: bool = field(default=False, init=False, repr=False)
    _ratchets: list = field(default_factory=list, init=False, repr=False)

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        extra: list = []
        if positions and (self.ratchet_pos_recuperacao or self.ratchet_zero_a_zero):
            pos = positions[0]
            if pos.entry_ts != self._pos_ts:
                # primeira barra desta posicao: congela a geometria ORIGINAL,
                # antes de o corte de relogio de 60 min mexer no alvo
                self._pos_ts = pos.entry_ts
                self._tocou_70 = self._fez_r70 = self._fez_be = False
                self._entrada = pos.entry_price
                self._d_stop = (abs(pos.entry_price - pos.current_stop)
                                if pos.current_stop is not None else 0.0)
                self._d_alvo = (abs(pos.current_target - pos.entry_price)
                                if pos.current_target is not None else 0.0)
            if self._d_stop > 0.0 and self._d_alvo > 0.0:
                if pos.side == "long":
                    pico_fav = bar.high - pos.entry_price
                    pico_adv = pos.entry_price - bar.low
                    adv = pos.entry_price - bar.close
                else:
                    pico_fav = pos.entry_price - bar.low
                    pico_adv = bar.high - pos.entry_price
                    adv = bar.close - pos.entry_price

                dispara = []
                if self.ratchet_pos_recuperacao and not self._fez_r70:
                    # 1o passo: foi CONTRA ate' 70% do stop
                    if pico_adv >= self.arma_stop * self._d_stop:
                        self._tocou_70 = True
                    # 2o passo: VOLTOU a 50%. So' agora o stop sobe -- e sobe
                    # para o pior ponto ja' visitado, que esta' ABAIXO do preco
                    # de agora e portanto nao dispara sozinho.
                    if self._tocou_70 and adv <= self.volta_stop * self._d_stop:
                        self._fez_r70 = True
                        dispara.append(("pos_recuperacao",
                                        self.nivel_novo * self._d_stop))
                if (self.ratchet_zero_a_zero and not self._fez_be
                        and pico_fav >= self.arma_alvo * self._d_alvo):
                    self._fez_be = True
                    dispara.append(("zero_a_zero", 0.0))

                if dispara:
                    # a MAIS protetora vence -- menor distancia da entrada.
                    # Emitir as duas deixaria o motor recusar uma em silencio.
                    regra, dist = min(dispara, key=lambda x: x[1])
                    alvo_stop = (pos.entry_price - dist if pos.side == "long"
                                 else pos.entry_price + dist)
                    alvo_stop = no_tick(alvo_stop, self.tick_size)
                    atual = pos.current_stop
                    mais_protetor = (atual is None
                                     or (alvo_stop > atual if pos.side == "long"
                                         else alvo_stop < atual))
                    if mais_protetor:
                        self._ratchets.append({
                            "entry_ts": pos.entry_ts, "regra": regra,
                            "nivel": alvo_stop,
                            "minutos": round((pd.Timestamp(ts) - pd.Timestamp(
                                pos.entry_ts)).total_seconds() / 60.0, 1),
                        })
                        extra.append(AdjustStop(float(alvo_stop)))
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        return list(acoes) + extra


def roda_pregao(dia: str) -> list[dict]:
    """UM pregao x as 4 celulas. Caixa R$375 do zero, como toda a rodada."""
    bars = carregar_bars(dia, dia)
    if bars.empty:
        return []
    linhas = []
    for nome, kwargs in CELULAS:
        strat = WdoOrbRatchet(**kwargs)
        cfg = monta_config(strat, CAPITAL_PARTIDA_BRL)
        res = run_intraday_backtest(bars, strat, cfg)
        ordens = sorted(strat._log_ordens, key=lambda o: o["sinal_ts"])
        por_pos: dict = {}
        for r in strat._ratchets:
            por_pos.setdefault(r["entry_ts"], []).append(r)
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
            rs = por_pos.get(t.entry_ts, [])
            saida = classifica_saida(razao, pnl_ticks, alvo)
            if razao == "stop" and rs:
                # saiu no stop DEPOIS de o ratchet ter subido o nivel
                saida = "stop_" + rs[-1]["regra"]
            linhas.append({
                "celula": nome, "data": dia, "op_do_dia": i + 1,
                "entrada_utc": pd.Timestamp(t.entry_ts).strftime("%H:%M:%S"),
                "saida_utc": pd.Timestamp(t.exit_ts).strftime("%H:%M:%S"),
                "tipo": ordem["tipo"] if ordem else "?", "side": t.side,
                "pnl_brl": round(t.pnl_brl, 2), "pnl_ticks": round(pnl_ticks, 1),
                "alvo_ticks": alvo,
                "stop_ticks": ordem["stop_ticks"] if ordem else float("nan"),
                "saida_efetiva": saida,
                "ratchets": "+".join(r["regra"] for r in rs),
                "min_1o_ratchet": rs[0]["minutos"] if rs else float("nan"),
                "mfe_ticks": round(exc["mfe_ticks"], 1),
                "mae_ticks": round(exc["mae_ticks"], 1),
            })
    return linhas


def bootstrap(df: pd.DataFrame, cand: str) -> dict:
    """Reamostra PREGOES (nao operacoes) com reposicao, emparelhado: a mesma
    lista de dias serve as duas celulas."""
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
    """O que a producao fez com as MESMAS operacoes em que o ratchet subiu o
    stop. Casa por (data, hora de entrada), nunca por ordem no dia -- mudar a
    saida muda quando o fade arma, entao a 2a operacao pode nem ser a mesma."""
    a = df[df.celula == BASE].set_index(["data", "entrada_utc"])
    b = df[(df.celula == cand) & (df.ratchets != "")].set_index(["data", "entrada_utc"])
    linhas = []
    for k in b.index.intersection(a.index):
        ra, rb = a.loc[k], b.loc[k]
        if isinstance(ra, pd.DataFrame): ra = ra.iloc[0]
        if isinstance(rb, pd.DataFrame): rb = rb.iloc[0]
        linhas.append({
            "data": k[0], "entrada": k[1], "janela": rb.janela,
            "ratchets": rb.ratchets, "min_1o": rb.min_1o_ratchet,
            "ratchet_saida": rb.saida_efetiva, "ratchet_pnl": rb.pnl_brl,
            "producao_saida": ra.saida_efetiva, "producao_pnl": ra.pnl_brl,
            "delta": round(rb.pnl_brl - ra.pnl_brl, 2),
        })
    d = pd.DataFrame(linhas)
    if not d.empty:
        d.attrs["orfas"] = len(b.index.difference(a.index))
    return d


def main() -> None:
    dias_por_janela, todos = {}, []
    for rotulo, ini, fim, _ in JANELAS:
        dias = pregoes_da_janela(ini, fim)
        dias_por_janela[rotulo] = set(dias)
        todos.extend(dias)
    print(f"[ratchet] {len(todos)} pregoes x {len(CELULAS)} celulas "
          f"({[c for c, _ in CELULAS]}), {MAX_WORKERS} processos\n", flush=True)

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
    df.to_csv(SAIDA / "99_ratchet_trades.csv", index=False, encoding="utf-8")
    print(f"\n[ratchet] {len(df)} operacoes -> 99_ratchet_trades.csv")

    # ---- 1. quanto cada ratchet disparou, e no que deu ---------------------
    print("\n" + "=" * 120)
    print("1) QUANTAS VEZES O STOP SUBIU  (e quantas dessas ainda assim bateram no stop novo)")
    print("=" * 120)
    disp = []
    for nome, _ in CELULAS:
        if nome == BASE:
            continue
        s = df[df.celula == nome]
        for janela in [j for j, _, _, _ in JANELAS]:
            sj = s[s.janela == janela]
            mex = sj[sj.ratchets != ""]
            disp.append({
                "celula": nome, "janela": janela, "ops": len(sj),
                "subiu_stop": len(mex),
                "pct": round(100.0 * len(mex) / len(sj), 1) if len(sj) else np.nan,
                "por_recuperacao": int(mex.ratchets.str.contains("pos_recuperacao").sum()),
                "por_zero_a_zero": int(mex.ratchets.str.contains("zero_a_zero").sum()),
                "bateu_stop_novo": int(mex.saida_efetiva.str.startswith("stop_").sum()),
                "seguiu_e_venceu": int((mex.pnl_brl > 0).sum()),
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
    pd.concat(tabelas).to_csv(SAIDA / "99b_ratchet_resumo.csv",
                              index=False, encoding="utf-8")

    # ---- 3. o contrafactual + quanto do TETO foi coletado ------------------
    print("\n" + "=" * 132)
    print("3) CONTRAFACTUAL -- as operacoes em que o stop subiu, contra o que a PRODUCAO fez")
    print("=" * 132)
    print("   [teto declarado] a regra B que FECHAVA economizava +R$910 (IS) e +R$685 (OOS)")
    print("   nas perdedoras, e devolvia R$860/R$625 nas ganhadoras. O ratchet tem de")
    print("   coletar a economia SEM pagar a devolucao.")
    for nome, _ in CELULAS:
        if nome == BASE:
            continue
        d = contrafactual(df, nome)
        print(f"\n--- celula {nome} ---")
        if d.empty:
            print("  o ratchet nunca disparou.")
            continue
        d.to_csv(SAIDA / f"99c_contrafactual_{nome.replace('+', '_')}.csv",
                 index=False, encoding="utf-8")
        for janela in [j for j, _, _, _ in JANELAS]:
            sj = d[d.janela == janela]
            if sj.empty:
                continue
            perd = sj[sj.producao_pnl <= 0]
            ganh = sj[sj.producao_pnl > 0]
            print(f"  [{janela}] {len(sj)} com stop subido | delta R${sj.delta.sum():+,.2f} "
                  f"| melhorou em {int((sj.delta > 0).sum())}/{len(sj)}")
            print(f"           das {len(perd)} que a producao PERDIA: "
                  f"economia R${(perd.ratchet_pnl.sum() - perd.producao_pnl.sum()):+,.2f}")
            print(f"           das {len(ganh)} que a producao GANHAVA:  "
                  f"devolucao R${(ganh.ratchet_pnl.sum() - ganh.producao_pnl.sum()):+,.2f}")
        if d.attrs.get("orfas"):
            print(f"  ({d.attrs['orfas']} sem par na producao -- so' existem nesta celula)")

    # ---- 4. bootstrap + o veredito pelo criterio congelado -----------------
    print("\n" + "=" * 132)
    print(f"4) BOOTSTRAP EMPARELHADO POR PREGAO contra {BASE} "
          f"({N_BOOT} reamostragens, so' IS+OOS_LIMPO)")
    print("=" * 132)
    resumo = pd.concat(tabelas).set_index(["janela", "celula"])
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
        # criterio 1, congelado na docstring: melhora nas DUAS janelas
        ok = True
        for j in JANELAS_QUE_VOTAM:
            for m in ("rs_por_op", "pregoes_pos_pct"):
                if not (resumo.loc[(j, nome), m] > resumo.loc[(j, BASE), m]):
                    ok = False
        c2 = max(b["rs_pct"], b["pr_pct"]) >= 90.0
        print(f"    criterio 1 (melhora nas 2 janelas, nas 2 metricas): "
              f"{'PASSA' if ok else 'FALHA'}")
        print(f"    criterio 2 (bootstrap >= 90% em uma das metricas):  "
              f"{'PASSA' if c2 else 'FALHA'}")
    print("\n  [criterio congelado ANTES da medicao -- ver a docstring do modulo]")
    print(f"\n[ratchet] arquivos em {SAIDA}")


if __name__ == "__main__":
    main()
