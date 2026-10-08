"""Inclinacao das MMEs semanais na ENTRADA e na SAIDA da estrategia semanal.

Pedido do dono (2026-10-08): nos prints, olhar a inclinacao das medias teria
entrado em pontos melhores e saido mais perto do pico. Testar 1, 2 ou as 3
medias, cada uma com o seu limiar, entrada e saida com a mesma inclinacao ou
nao, e as combinacoes.

INCLINACAO de uma MME na semana t = MME[t] / MME[t-1] - 1 (% por semana, no
fechamento semanal). A linha de base ja exige as tres > 0 no sinal.

LIMIARES. A MME9 anda muito mais rapido que a MME50, entao cada media usa o
proprio limiar: os quartis (q25, q50, q75) da inclinacao dela nas semanas de
sinal do IS. Calculados uma vez no IS e gravados em
`inclinacao_limiares_is.json`; o OOS usa os mesmos numeros, congelados.

DECLARADO ANTES DE RODAR -- tres fases no IS, mesmo criterio em todas:
  criterio = maior expectativa media por operacao nas saidas da configuracao
  (14x2 e 21x3 quando a linha ATR participa), mantendo pelo menos 40% das
  operacoes da linha de base; empate -> mais operacoes.
  Grade limitada a 50 (pedido do dono), em escada para mostrar DIRECAO:
  Fase A, ENTRADA (15): exigir inclinacao >= q25/q50/q75 em cada media
     sozinha e nas tres juntas; cada par so em q50. Saida = linha de base.
  Fase B, SAIDA (17): sair na abertura seguinte quando a inclinacao cair
     abaixo de 0/q25/q50 -- cada media sozinha junto da linha ATR, o que vier
     primeiro ("incl+atr", 9); cada media ao virar para baixo NO LUGAR da
     ATR ("incl", 3); as tres juntas, 0/q25/q50 (3); qualquer uma entre 9 e
     21, 0/q25 (2). Entrada = linha de base. O stop inicial vale em tudo.
  Fase C (9): mesma inclinacao na entrada e na saida para cada media em q25
     e q50 (6, fixas), mais a melhor entrada x as 3 melhores saidas (3).
  Total 42. So o vencedor da fase C vai para o OOS (rodado a parte, --configs).

Com dezenas de configuracoes no mesmo IS a melhor sempre parece boa por sorte;
o OOS e o que separa. A tabela mostra tambem quantas batem a linha de base por
mais que o intervalo de confianca.

Uso:
  .venv/Scripts/python.exe scripts/swing_lab/semanal_inclinacao_2026_10_08.py --conjunto is
  .venv/Scripts/python.exe scripts/swing_lab/semanal_inclinacao_2026_10_08.py --conjunto oos --configs <id> [<id> ...]
"""
from __future__ import annotations

import argparse
import io
import itertools
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base_mt5 as base  # noqa: E402
import semanal_mmes_video_2026_10_08 as setup  # noqa: E402
from semanal_linha_de_base_2026_10_08 import br, bh, carteira  # noqa: E402

LIMIARES = Path(__file__).with_name("inclinacao_limiares_is.json")
MMS = (9, 21, 50)
GRUPOS = [g for k in (1, 2, 3) for g in itertools.combinations(MMS, k)]
NIVEIS_ENT = ("q25", "q50", "q75")
NIVEIS_SAI = ("zero", "q25", "q50")


def nome_grupo(g) -> str:
    return "+".join(str(x) for x in g)


def _sai(g, q, nv, modo) -> dict:
    rotulo = nome_grupo(g) if len(g) == 1 else f"{q} {nome_grupo(g)}"
    return dict(id=f"S[{rotulo}]<{nv}|{modo}", fase="B", ent=None, sai=(g, q, nv), modo=modo)


def configs_ab() -> list[dict]:
    """Grade limitada a 50 no total (pedido do dono): niveis em escada para
    mostrar DIRECAO, nao todas as combinacoes. 1 base + 15 entradas + 17 saidas;
    a fase C acrescenta 9."""
    cs = [dict(id="base", fase="base", ent=None, sai=None, modo="atr")]
    entradas = [((n,), nv) for n in MMS for nv in NIVEIS_ENT] + [(MMS, nv) for nv in NIVEIS_ENT] + \
               [(g, "q50") for g in GRUPOS if len(g) == 2]
    for g, nv in entradas:
        cs.append(dict(id=f"E[{nome_grupo(g)}]>{nv}", fase="A", ent=(g, nv), sai=None, modo="atr"))
    cs += [_sai((n,), "todas", nv, "incl+atr") for n in MMS for nv in NIVEIS_SAI]
    cs += [_sai((n,), "todas", "zero", "incl") for n in MMS]
    cs += [_sai(MMS, "todas", nv, "incl+atr") for nv in NIVEIS_SAI]
    cs += [_sai((9, 21), "qualquer", nv, "incl+atr") for nv in ("zero", "q25")]
    return cs


def inclinacoes(w: pd.DataFrame) -> dict[int, pd.Series]:
    return {n: setup.ema(w.close, n) / setup.ema(w.close, n).shift() - 1 for n in MMS}


def preparar(tk: str, conjunto: str):
    d = base.carregar(tk, conjunto)
    if len(d) < 300:
        return None
    w = setup.semanal(d)
    if w.index[-1] > d.index[-1]:
        w = w.iloc[:-1]
    return d, w, setup.sinais(w), inclinacoes(w)


def amostra_sinais(tk: str) -> dict[int, list[float]]:
    """Inclinacao de cada MME nas semanas de sinal do IS (para os quartis)."""
    p = preparar(tk, "is")
    if p is None:
        return {}
    _, w, sig, inc = p
    ini, fim = base.janela("is")
    m = sig.recuo_media & (w.index >= ini) & (w.index <= fim)
    return {n: inc[n][m].dropna().tolist() for n in MMS}


def medir(tk: str, conjunto: str, configs: list[dict], lim: dict) -> tuple[str, list[dict], dict, pd.Series]:
    out: list[dict] = []
    with redirect_stdout(io.StringIO()):
        p = preparar(tk, conjunto)
        if p is None:
            return tk, out, {}, base.carregar(tk, conjunto)["close"]
        d, w, sig0, inc = p
        H = d.high
        ini, fim = base.janela(conjunto)

        def valor(n, nv):
            return 0.0 if nv == "zero" else lim[str(n)][nv]

        for c in configs:
            sig = sig0
            if c["ent"]:
                g, nv = c["ent"]
                ok = np.logical_and.reduce([(inc[n] >= valor(n, nv)).to_numpy() for n in g])
                sig = sig0.copy()
                sig["recuo_media"] = sig0.recuo_media & ok
            sair = None
            if c["sai"]:
                g, q, nv = c["sai"]
                abaixo = [(inc[n] < valor(n, nv)).to_numpy() for n in g]
                sair = np.logical_or.reduce(abaixo) if q == "qualquer" else np.logical_and.reduce(abaixo)
            variantes = ("atr14x2", "atr21x3") if c["modo"] != "incl" else ("atr21x3",)
            for v in variantes:
                for t in setup.simular(d, w, sig, "recuo_media", v, usar_atr=c["modo"] != "incl", sair_semana=sair):
                    if not (ini <= t.entrada_data <= fim):
                        continue
                    pico = float(H.loc[t.entrada_data:t.saida_data].max())
                    out.append(dict(cfg=c["id"], var=v if c["modo"] != "incl" else "incl", ret=t.ret, dias=t.dias,
                                    motivo=t.motivo, entrada_data=t.entrada_data, saida_data=t.saida_data,
                                    semana_sinal=t.semana_sinal, entrada=t.entrada, saida=t.saida,
                                    ticker=tk, devol=1 - t.saida / pico))
        r52 = (w["close"] / w["close"].shift(52) - 1).dropna()
    return tk, out, {k.strftime("%Y-%m-%d"): float(x) for k, x in r52.items()}, d["close"]


def rodar(tks, conjunto, configs, lim):
    trades, r52, closes = [], {}, {}
    with ProcessPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(medir, tk, conjunto, configs, lim) for tk in tks]
        for i, f in enumerate(as_completed(futs), 1):
            tk, tr, r, c = f.result()
            trades += tr; closes[tk] = c
            if r:
                r52[tk] = pd.Series(r)
            if i % 25 == 0 or i == len(tks):
                print(f"  medidos {i}/{len(tks)}", flush=True)
    return pd.DataFrame(trades), r52, closes


def placar(T: pd.DataFrame, configs: list[dict]) -> pd.DataFrame:
    n_base = T[T.cfg == "base"].groupby("var").size().mean()
    base_exp = T[T.cfg == "base"].groupby("var").ret.mean().mean()
    linhas = []
    for c in configs:
        g = T[T.cfg == c["id"]]
        if g.empty:
            continue
        por_var = g.groupby("var").ret
        exp = por_var.mean().mean()
        ic = (1.96 * por_var.std(ddof=1) / np.sqrt(por_var.size())).mean()
        anos = g.groupby(g.entrada_data.str[:4]).ret.mean()
        linhas.append(dict(id=c["id"], fase=c["fase"], exp=exp, ic=ic, n=len(g) / g["var"].nunique(),
                           frac=len(g) / g["var"].nunique() / n_base, acerto=(g.ret > 0).mean(),
                           devol=g.devol.median(), dias=g.dias.median(),
                           acima_ic=exp - base_exp > ic,
                           anos=" ".join(f"{a[2:]}:{br(v, 1)}" for a, v in anos.items())))
    return pd.DataFrame(linhas)


def imprimir(P: pd.DataFrame, titulo: str, top: int | None = None) -> None:
    print(f"\n{titulo}", flush=True)
    P = P.sort_values(["exp", "n"], ascending=False)
    if top:
        P = P.head(top)
    for r in P.itertuples():
        fora = "" if r.frac >= .4 else "  (menos de 40% das operações: fora)"
        print(f"  {r.id:34s} por op.={br(r.exp):>7s} ±{br(r.ic, sinal=False):6s} n={r.n:5.0f} ({r.frac:4.0%})"
              f"  acerto={br(r.acerto, 1, sinal=False):>6s}  devolve do pico={br(r.devol, 1, sinal=False):>6s}"
              f"  dias={r.dias:4.0f}  | {r.anos}{fora}", flush=True)


def melhores(P: pd.DataFrame, fase: str, k: int) -> list[str]:
    Q = P[(P.fase == fase) & (P.frac >= .4)].sort_values(["exp", "n"], ascending=False)
    return Q.id.head(k).tolist()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--conjunto", choices=["is", "oos"], required=True)
    ap.add_argument("--configs", nargs="*", default=None, help="ids para o OOS (a linha de base entra sempre)")
    a = ap.parse_args()
    ab = configs_ab()
    por_id = {c["id"]: c for c in ab}

    if a.conjunto == "is":
        print("== limiares: quartis da inclinação nas semanas de sinal do IS", flush=True)
        amostras: dict[int, list[float]] = {n: [] for n in MMS}
        with ProcessPoolExecutor(max_workers=2) as ex:
            for f in as_completed([ex.submit(amostra_sinais, tk) for tk in base.papeis("is")]):
                for n, v in f.result().items():
                    amostras[n] += v
        lim = {str(n): {q: float(np.quantile(amostras[n], p)) for q, p in (("q25", .25), ("q50", .5), ("q75", .75))} for n in MMS}
        LIMIARES.write_text(json.dumps(lim, indent=1), encoding="utf-8")
        for n in MMS:
            print(f"  MME{n:<2d} q25 {br(lim[str(n)]['q25'])}/sem  q50 {br(lim[str(n)]['q50'])}/sem  q75 {br(lim[str(n)]['q75'])}/sem", flush=True)

        print(f"\n== fases A e B: {len(ab)} configurações, {len(base.papeis('is'))} papéis", flush=True)
        T, r52, closes = rodar(base.papeis("is"), "is", ab, lim)
        P = placar(T, ab)
        imprimir(P[P.fase == "base"], "LINHA DE BASE")
        imprimir(P[P.fase == "A"], "FASE A — ENTRADA (todas as 21)")
        imprimir(P[P.fase == "B"], "FASE B — SAÍDA (as 15 melhores de 66)", top=15)
        ba = P[P.fase.isin(["A", "B"])]
        print(f"\n  batem a linha de base por mais que o IC: {int(ba.acima_ic.sum())} de {len(ba)}", flush=True)

        ea, sb = melhores(P, "A", 1), melhores(P, "B", 3)
        cc = []
        for n in MMS:  # mesma inclinacao na entrada e na saida, fixas antes de ver resultado
            for nv in ("q25", "q50"):
                e = f"E[{n}]>{nv}"
                cc.append(dict(id=f"{e} + simétrica|incl+atr", fase="C", ent=((n,), nv), sai=((n,), "todas", nv), modo="incl+atr"))
        for s in sb:
            cc.append(dict(id=f"{ea[0]} + {s}", fase="C", ent=por_id[ea[0]]["ent"], sai=por_id[s]["sai"], modo=por_id[s]["modo"]))
        print(f"\n== fase C: {len(cc)} combinações (6 simétricas + melhor entrada {ea} x saídas {sb}); total {len(ab) + len(cc)}", flush=True)
        T2, _, _ = rodar(base.papeis("is"), "is", [ab[0]] + cc, lim)
        P2 = placar(T2, [ab[0]] + cc)
        imprimir(P2, "FASE C")
        venc = melhores(P2, "C", 1)
        finalistas = {"base": ab[0]} | {i: c for i, c in ((x, por_id[x]) for x in ea[:1] + sb[:1])} | \
                     {c["id"]: c for c in cc if c["id"] in venc}
        print(f"\n  VENCEDOR (critério declarado): {venc[0] if venc else '—'}", flush=True)
    else:
        lim = json.loads(LIMIARES.read_text(encoding="utf-8"))
        finalistas = {"base": ab[0]}
        for i in a.configs or []:
            if i in por_id:
                finalistas[i] = por_id[i]
            else:  # combinacao da fase C: "<entrada> + <saida>"
                e, s = i.split(" + ")
                ent = por_id[e]["ent"]
                if s.startswith("simétrica|"):
                    g, nv = ent
                    finalistas[i] = dict(id=i, fase="C", ent=ent, sai=(g, "todas", nv), modo=s.split("|")[1])
                else:
                    finalistas[i] = dict(id=i, fase="C", ent=ent, sai=por_id[s]["sai"], modo=por_id[s]["modo"])
        T, r52, closes = rodar(base.papeis("oos"), "oos", list(finalistas.values()), lim)
        imprimir(placar(T, list(finalistas.values())), "OOS")

    # carteira so para os finalistas (linha de base, melhor entrada, melhor saida, vencedor)
    ini, fim = base.janela(a.conjunto)
    Tf, r52f, clf = rodar(base.papeis(a.conjunto), a.conjunto, list(finalistas.values()), lim) if a.conjunto == "is" else (T, r52, closes)
    pct = pd.DataFrame(r52f).rank(axis=1, pct=True)
    Tf["pct12m"] = [pct.at[s, t] if s in pct.index else np.nan for s, t in zip(Tf.semana_sinal, Tf.ticker)]
    cl = pd.DataFrame(clf).sort_index().ffill().loc[:fim]
    b = bh(pd.read_parquet(base.PASTA / "BOVA11.parquet")["close"], ini, fim)
    print(f"\nCARTEIRA R$1.000 — {a.conjunto.upper()} (BOVA11 comprar e segurar R${br(b['final'], 0, pct=False, sinal=False)})", flush=True)
    for cid in finalistas:
        for v, g in Tf[Tf.cfg == cid].groupby("var"):
            tv = [dict(r._asdict()) for r in g.itertuples(index=False)]
            for t in tv:
                t["pct12m"] = None if pd.isna(t["pct12m"]) else t["pct12m"]
            cel = []
            for K in (3, 5):
                r = carteira(tv, cl, K, ini, fim, False)
                cel.append(f"K{K} R${br(r['final'], 0, pct=False, sinal=False):>6s} dd{br(r['dd'], 0):>5s} n={r['n']:3d}")
            print(f"  {cid:44s} {v:8s} " + " | ".join(cel), flush=True)


if __name__ == "__main__":
    main()
