"""Teste das DUAS PONTAS na estrategia WIN (vela M5 inteira fora da roxa WMA34 + verde SMMA34 do lado oposto).

Em cada sinal NOVO (troca de estado) simula uma COMPRA e uma VENDA, ambas na abertura da M5 seguinte, com o mesmo
stop/alvo/saida e a execucao em M1 do simulador do repo. Compara com um controle de eventos no MESMO horario em
dias sorteados (sem sinal). Perguntas:
  - dir_val: a direcao do sinal vale mais que um lado sorteado? = media(lado do sinal) - (compra+venda)/2
  - oraculo: se um filtro escolhesse sempre o melhor lado (teto, NAO e' estrategia) quanto seria
  - a*: acerto minimo do filtro na escolha do lado para o resultado empatar em zero
  - acc: em que fracao dos eventos o lado do sinal foi o melhor (50% = moeda)
Custos do simulador: 5 pts/op + 2 pts de slip no stop, R$0,20/pt. Teste descritivo, nao otimiza nada.
Uso: python win_duas_pontas_2026_10_01.py [valida]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import win_ema8_wma8_sim_m1 as sim  # noqa: E402
from core.indicators import lwma, smma  # noqa: E402

CUSTO, SLIP, R = 5.0, 2.0, sim.R_PT
RNG = np.random.default_rng(0)


# ---------------------------------------------------------------- dados e eventos
def carregar():
    m5, m1 = sim.ler("WIN@D_M5_*.csv"), sim.ler("WIN@D_M1_*.csv")
    e, w = smma(m5.close, sim.PERIODO), lwma(m5.close, sim.PERIODO)
    acima, abaixo = (m5.low > w) & (e < w), (m5.high < w) & (e > w)
    sig5 = pd.Series(np.where(acima, 1, np.where(abaixo, -1, 0)), index=m5.index)
    sig5[e.isna() | w.isna()] = 0
    nova = (sig5 != 0) & (sig5 != sig5.shift(1).fillna(0))
    return m1, sig5, nova


def indexar(m1):
    t = (m1.index.hour * 60 + m1.index.minute).to_numpy()
    dia = np.array(m1.index.date)
    return {"o": m1.open.to_numpy(), "h": m1.high.to_numpy(), "l": m1.low.to_numpy(), "t": t, "dia": dia,
            "idx": m1.index}


def caminho(M, i0):
    """Barras da entrada (i0) ate a barra que zera (t>=17:50) inclusive; a ultima so' serve de preco de saida."""
    n = len(M["t"])
    j = i0
    while j + 1 < n and M["dia"][j + 1] == M["dia"][i0] and M["t"][j] < sim.ZERAR:
        j += 1
    return slice(i0, j + 1)


def eventos(M, m1, sig5, nova):
    pos = {ts: k for k, ts in enumerate(M["idx"])}
    ev = []
    for ts in sig5.index[nova.to_numpy()]:
        te = ts + pd.Timedelta(minutes=5)
        i0 = pos.get(te)
        if i0 is None or M["t"][i0] >= sim.SEM_ENTRADA or M["t"][i0] < 9 * 60:
            continue
        ev.append((i0, int(sig5[ts])))
    return ev


def controle(M, ev):
    """Para cada evento real, um evento no MESMO horario de outro dia sorteado (entrada so' em abertura de M5)."""
    por_t: dict[int, list[int]] = {}
    for i, t in enumerate(M["t"]):
        if t % 5 == 0 and 9 * 60 <= t < sim.SEM_ENTRADA:
            por_t.setdefault(int(t), []).append(i)
    out = []
    for i0, s in ev:
        c = por_t.get(int(M["t"][i0]))
        out.append((int(RNG.choice(c)) if c else i0, s))
    return out


# ---------------------------------------------------------------- execucao
def walk(o, h, l, d, stop, tp, trail_on=None, trail_dist=60.0, be_at=None, tmax=None):
    """Espelha simular(): stop antes do alvo na mesma barra, stop novo (trailing/BE) so' vale na barra seguinte,
    stop vence gap na abertura. o[-1] e' a abertura da barra que zera. Devolve pts liquidos."""
    e = o[0]
    sl = e - d * stop
    sl0 = sl
    mel = e
    n = len(o)
    for i in range(n - 1):
        if tmax is not None and i >= tmax:
            return d * (o[i] - e) - CUSTO
        if d == 1:
            if l[i] <= sl:
                return min(sl, o[i]) - e - CUSTO - SLIP
            if tp is not None and h[i] >= e + tp:
                return tp - CUSTO
            mel = max(mel, h[i])
            if trail_on is not None and mel - e >= trail_on:
                sl = max(sl, mel - trail_dist)
            if be_at is not None and mel - e >= be_at:
                sl = max(sl, e)
        else:
            if h[i] >= sl:
                return e - max(sl, o[i]) - CUSTO - SLIP
            if tp is not None and l[i] <= e - tp:
                return tp - CUSTO
            mel = min(mel, l[i])
            if trail_on is not None and e - mel >= trail_on:
                sl = min(sl, mel + trail_dist)
            if be_at is not None and e - mel >= be_at:
                sl = min(sl, e)
    return d * (o[-1] - e) - CUSTO


def grade_fixa(M, ev, stops, alvos):
    """Stop/alvo fixos, vetorizado por cummax. Devolve {(stop,alvo): array (n,2) = [compra, venda] em R$}."""
    res = {(s, a): np.zeros((len(ev), 2)) for s in stops for a in alvos}
    for k, (i0, _) in enumerate(ev):
        sl = caminho(M, i0)
        o, h, l = M["o"][sl], M["h"][sl], M["l"][sl]
        e, nb = o[0], len(o) - 1
        for c, d in enumerate((1, -1)):
            adv = np.maximum.accumulate(e - l[:nb] if d == 1 else h[:nb] - e)
            fav = np.maximum.accumulate(h[:nb] - e if d == 1 else e - l[:nb])
            zera = d * (o[-1] - e) - CUSTO
            for s in stops:
                ks = int(np.searchsorted(adv, s, side="left"))
                gs = min(-s, d * (o[ks] - e)) - CUSTO - SLIP if ks < nb else None
                for a in alvos:
                    kt = int(np.searchsorted(fav, a, side="left"))
                    if ks < nb and ks <= kt:
                        p = gs
                    elif kt < nb:
                        p = a - CUSTO
                    else:
                        p = zera
                    res[(s, a)][k, c] = p * R
    return res


def estrategia(M, ev, **kw):
    out = np.zeros((len(ev), 2))
    for k, (i0, _) in enumerate(ev):
        sl = caminho(M, i0)
        o, h, l = M["o"][sl], M["h"][sl], M["l"][sl]
        for c, d in enumerate((1, -1)):
            out[k, c] = walk(o, h, l, d, **kw) * R
    return out


# ---------------------------------------------------------------- metricas
def boot_dia(x, dias, n=400):
    u, inv = np.unique(dias, return_inverse=True)
    s, c = np.bincount(inv, weights=x), np.bincount(inv)
    idx = RNG.integers(0, len(u), (n, len(u)))
    m = s[idx].sum(1) / c[idx].sum(1)
    return np.percentile(m, [2.5, 97.5])


def metricas(P, ev, dias):
    dr = np.array([s for _, s in ev])
    col = np.where(dr == 1, 0, 1)
    sig = P[np.arange(len(P)), col]
    opp = P[np.arange(len(P)), 1 - col]
    media = P.mean(1)
    best, worst = P.max(1), P.min(1)
    dv = sig - media
    acc = np.mean(np.where(sig > opp, 1.0, np.where(sig == opp, 0.5, 0.0)))
    eb, ew = best.mean(), worst.mean()
    astar = (-ew / (eb - ew)) if eb > ew else np.nan
    ic = boot_dia(dv, dias)
    return {"n": len(P), "compra": P[:, 0].mean(), "venda": P[:, 1].mean(), "sinal": sig.mean(),
            "dir_val": dv.mean(), "ic_lo": ic[0], "ic_hi": ic[1], "oraculo": best.mean(), "a*": astar, "acc": acc,
            "ambos<0%": np.mean((P < 0).all(1)) * 100}


def tab(linhas, titulo):
    df = pd.DataFrame(linhas).set_index("cfg")
    pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_rows", 200)
    print(f"\n== {titulo}\n{df.round(3)}", flush=True)
    return df


def main(valida: bool):
    m1, sig5, nova = carregar()
    M = indexar(m1)
    ev = eventos(M, m1, sig5, nova)
    ctl = controle(M, ev)
    dias = np.array([M["dia"][i] for i, _ in ev], dtype="datetime64[D]").astype(str)
    dias_c = np.array([M["dia"][i] for i, _ in ctl], dtype="datetime64[D]").astype(str)
    print(f"eventos de sinal novo: {len(ev)} ({sum(s == 1 for _, s in ev)} compra / {sum(s == -1 for _, s in ev)} venda)", flush=True)

    if valida:  # confere contra simular() no mes: mesmas entradas devem dar o mesmo R$
        mes = "2026-08"
        base = sim.preparar(mes, limpa=True, so_roxa=True)
        tr = sim.simular(base, 300, 600, troca=True)
        pos = {(M["idx"][i0], s): k for k, (i0, s) in enumerate(ev)}
        ok = bad = 0
        for _, r in tr.iterrows():
            k = pos.get((r.t_entrada, int(r["dir"])))
            if k is None:
                continue
            sl = caminho(M, ev[k][0])
            p = walk(M["o"][sl], M["h"][sl], M["l"][sl], int(r["dir"]), 300, 600, trail_on=100.0, trail_dist=60.0) * R
            ok, bad = (ok + 1, bad) if abs(p - r.rs) < 1e-6 else (ok, bad + 1)
        print(f"VALIDACAO vs simular() em {mes}: {ok} iguais, {bad} diferentes (de {len(tr)} trades)", flush=True)
        g = grade_fixa(M, ev, [300], [600])[(300, 600)]
        w = estrategia(M, ev, stop=300, tp=600)
        print(f"VALIDACAO grade vetorizada vs walk (sem trailing, todos os eventos): max |dif| = {np.abs(g - w).max():.6f}", flush=True)
        return

    stops, alvos = [100, 150, 200, 300, 450], [100, 200, 300, 450, 600, 900]
    gs, gc = grade_fixa(M, ev, stops, alvos), grade_fixa(M, ctl, stops, alvos)
    lin = []
    for (s, a) in gs:
        m = metricas(gs[(s, a)], ev, dias)
        mc = metricas(gc[(s, a)], ctl, dias_c)
        lin.append({"cfg": f"{s}/{a}", **m, "a*_ctrl": mc["a*"], "orac_ctrl": mc["oraculo"], "ctrl_media": gc[(s, a)].mean()})
    tab(lin, "GRADE FIXA stop/alvo (sem trailing), R$ por evento, custos incluidos")

    saidas = {
        "fixa": dict(tp=None),
        "trail 100/60 (EA)": dict(trail_on=100.0, trail_dist=60.0),
        "trail 200/100": dict(trail_on=200.0, trail_dist=100.0),
        "BE apos +150": dict(be_at=150.0),
        "BE apos +100": dict(be_at=100.0),
        "tempo 30min": dict(tmax=30),
        "tempo 60min": dict(tmax=60),
        "tempo 120min": dict(tmax=120),
        "so trail 100/60 sem alvo": dict(trail_on=100.0, trail_dist=60.0, tp=None),
    }
    for (s, a) in ((300, 600), (150, 300)):
        lin = []
        for nome, kw in saidas.items():
            k = dict(stop=s, tp=a if "tp" not in kw else kw["tp"])
            k.update({x: v for x, v in kw.items() if x != "tp"})
            if nome == "fixa":
                k["tp"] = a
            P, Pc = estrategia(M, ev, **k), estrategia(M, ctl, **k)
            m, mc = metricas(P, ev, dias), metricas(Pc, ctl, dias_c)
            lin.append({"cfg": nome, **m, "a*_ctrl": mc["a*"], "orac_ctrl": mc["oraculo"], "ctrl_media": Pc.mean()})
        tab(lin, f"ESTRATEGIAS DE SAIDA com stop {s} / alvo {a}")

    anos = np.array([d[:4] for d in dias])
    lin = []
    for nome, kw in (("fixa 300/600", dict(stop=300, tp=600)), ("EA trail 300/600", dict(stop=300, tp=600, trail_on=100.0, trail_dist=60.0))):
        P = estrategia(M, ev, **kw)
        for ano in sorted(set(anos)):
            sel = anos == ano
            lin.append({"cfg": f"{nome} {ano}", **metricas(P[sel], [e for e, s in zip(ev, sel) if s], dias[sel])})
    tab(lin, "POR ANO")


if __name__ == "__main__":
    main(len(sys.argv) > 1 and sys.argv[1] == "valida")
