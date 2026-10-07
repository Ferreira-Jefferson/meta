"""Hipotese C (WIN): saida diferente conforme o lado esteja A FAVOR ou CONTRA o regime do mes.

Regime em tempo real: fechamento da barra do SINAL acima/abaixo da VWAP ancorada no 1o pregao
do mes (max(inicio do mes, inicio do contrato)); tipico (h+l+c)/3 x vol. Oraculo: sinal da
direcao real do mes (teto, usa o futuro).
Saida (por posicao, escolhida pelo regime da barra do sinal):
  contra: (exit_ema, k, m) -> sai tambem se fecha do lado errado da EMA rapida (5/7);
          stop fixo k*ATR14(M5) a partir do preenchimento (mercado, 1 tick de deslize);
          alvo-limite m*stop (enche so se o preco negocia 1 tick ALEM do nivel); stop+alvo na mesma barra = stop.
  favor : 'orig' | '9x21' (so sai quando EMA9 cruza a EMA21) | 'c21' (fecha cruza a EMA21) | 'c34'.
Em todos os casos continua valendo a quebra original (exceto nas saidas de favor, que a substituem).
"""
from __future__ import annotations
import importlib.util as u
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np, pandas as pd

AQUI = Path(__file__).resolve().parent
_s = u.spec_from_file_location("kit", AQUI.parent / "win_melhor_kit.py")
kit = u.module_from_spec(_s); _s.loader.exec_module(kit)
b = kit.b
PT, TICK, FEE_RT, CAP0, TTL, FIM = b.PT, b.TICK, b.FEE_RT, b.CAP0, b.TTL, b.FIM
ORIG_C = (None, None, None)


def simula(d, ini, fim, reg, contra=ORIG_C, favor="orig", periodos=(9, 21, 34, 100, 200)):
    """Copia de b.simula (filtro reentra, saida quebra) + saida por regime. reg: array {-1,0,1} alinhado a d."""
    o_, h_, l_, c_ = d["o"], d["h"], d["l"], d["c"]
    es = [b.media(c_, p, "EMA") for p in periodos]
    up = pd.Series(True, index=d.index); dn = up.copy()
    for a_, b_ in zip(es, es[1:]):
        up &= a_ > b_; dn &= a_ < b_
    for e in es:
        up &= e.diff() > 0; dn &= e.diff() < 0
    est_all = np.where(up, 1, np.where(dn, -1, 0))
    e5, e7 = b.media(c_, 5, "EMA").values, b.media(c_, 7, "EMA").values
    e9, e21, e34 = es[0].values, es[1].values, es[2].values
    tr = pd.concat([h_ - l_, (h_ - c_.shift()).abs(), (l_ - c_.shift()).abs()], axis=1).max(axis=1)
    atr_all = tr.ewm(alpha=1 / 14, adjust=False).mean().values
    sel = d.index >= ini
    if fim is not None:
        sel &= d.index < fim
    idx = d.index[sel]
    o, h, l, cl = (d[k].values[sel] for k in "ohlc")
    est = est_all[sel]
    e5, e7, e9, e21, e34, atr = (x[sel] for x in (e5, e7, e9, e21, e34, atr_all))
    reg = np.asarray(reg)[sel]
    dias = idx.normalize(); tempo = idx.time; n = len(idx)
    cash = CAP0; trades = []; eq = np.empty(n)
    pos = 0; px = 0.0; pend = 0; lim = 0.0; ttl = 0; t_ent = None; lado_ent = 0
    reg_pend = 0; atr_pend = 0.0
    p_cfg = None; p_stop = np.nan; p_tgt = np.nan

    def fecha(s, dia, t):
        nonlocal cash, pos
        pts = pos * (s - px); pnl = (pts * PT - FEE_RT)
        cash += pnl
        trades.append((pnl, dia, pts, t_ent, lado_ent, idx[t], 1)); pos = 0

    for t in range(n):
        novo_dia = t == 0 or dias[t] != dias[t - 1]
        if novo_dia:
            pend = 0
        if pos and t > 0 and not novo_dia:
            j = t - 1
            if tempo[j] >= FIM:
                sai = True
            elif p_cfg["favor_mode"] != "orig":
                m = p_cfg["favor_mode"]
                if m == "9x21": sai = pos * (e9[j] - e21[j]) <= 0
                elif m == "c21": sai = pos * (cl[j] - e21[j]) <= 0
                else: sai = pos * (cl[j] - e34[j]) <= 0
            else:
                sai = est[j] != pos
                ee = p_cfg["exit_ema"]
                if not sai and ee:
                    ev = e5 if ee == 5 else e7
                    sai = pos * (cl[j] - ev[j]) <= 0
            if sai:
                fecha(o[t] - pos * TICK, dias[t], t)
        if pend and not pos:
            if (pend == 1 and l[t] <= lim) or (pend == -1 and h[t] >= lim):
                if cash >= 100:
                    pos = pend
                    px = min(lim, o[t]) if pend == 1 else max(lim, o[t])
                    t_ent, lado_ent = idx[t], pend
                    if reg_pend == pend or reg_pend == 2:
                        p_cfg = dict(favor_mode=favor, exit_ema=None); k = m_ = None
                    else:
                        ee, k, m_ = contra
                        p_cfg = dict(favor_mode="orig", exit_ema=ee)
                    if k:
                        dist = k * atr_pend
                        p_stop = px - pos * dist
                        p_tgt = px + pos * m_ * dist if m_ else np.nan
                    else:
                        p_stop = np.nan; p_tgt = np.nan
                pend = 0
            else:
                ttl -= 1
                if ttl <= 0 or est[t] != pend:
                    pend = 0
        if pos and not np.isnan(p_stop):
            if pos == 1:
                if l[t] <= p_stop: fecha(min(p_stop, o[t]) - TICK, dias[t], t)
                elif not np.isnan(p_tgt) and h[t] >= p_tgt + TICK: fecha(max(p_tgt, o[t]), dias[t], t)
            else:
                if h[t] >= p_stop: fecha(max(p_stop, o[t]) + TICK, dias[t], t)
                elif not np.isnan(p_tgt) and l[t] <= p_tgt - TICK: fecha(min(p_tgt, o[t]), dias[t], t)
        if not pos and not pend and est[t] != 0 and tempo[t] < FIM:
            pend, lim, ttl = est[t], cl[t], TTL
            reg_pend, atr_pend = reg[t], atr[t]
        if pos and (t == n - 1 or dias[t + 1] != dias[t]):
            fecha(cl[t] - pos * TICK, dias[t], t)
        eq[t] = cash
    return trades, pd.Series(eq, index=idx)


def vwap_regime(seg, anc):
    s = seg[anc:]
    tp = (s.h + s.l + s.c) / 3
    v = s.vol.astype(float)
    vw = (tp * v).cumsum() / v.cumsum()
    r = np.sign(s.c - vw)
    return r.reindex(seg.index).fillna(0).values


def rodar(m5, reg_mode, contra, favor):
    out = []
    for nome, seg, ini_op, ult in kit.segmentos(m5):
        for mes in pd.period_range(ini_op, ult, freq="M"):
            a = max(ini_op, mes.start_time); z = min(mes.end_time, ult + pd.Timedelta(days=1))
            jan = seg[a:z]
            if not len(jan): continue
            if reg_mode == "todos":
                reg = np.full(len(seg), 2.0)
            elif reg_mode == "oraculo":
                reg = np.full(len(seg), np.sign(jan.c.iloc[-1] - jan.o.iloc[0]))
            else:
                anc = max(mes.start_time, seg.index[0])
                reg = vwap_regime(seg[:z], anc)
                reg = np.concatenate([reg, np.zeros(len(seg) - len(reg))])
                if reg_mode == "invertido": reg = -reg
            tr, eq = simula(seg, a, z, reg, contra, favor)
            df = pd.DataFrame(tr, columns=kit.COLS)
            out.append(dict(janela=f"{mes} {nome} {a:%d}-{jan.index[-1]:%d}", contrato=nome,
                            mercado_pts=float(jan.c.iloc[-1] - jan.o.iloc[0]), trades=df, eq=eq))
    return out


def metricas(res):
    r = kit.resumo(res)
    t = pd.concat([x["trades"] for x in res])
    g, p = t.pnl[t.pnl > 0], -t.pnl[t.pnl < 0]
    r["payoff"] = round(g.mean() / p.mean(), 2) if len(g) and len(p) else None
    r["liq_janelas"] = [round(x["eq"].iloc[-1] - CAP0, 2) for x in res]
    r["janelas"] = [x["janela"] for x in res]
    return r


_M5 = None


def _task(args):
    global _M5
    if _M5 is None: _M5 = kit.carregar_m5()
    nome, reg_mode, contra, favor = args
    return nome, reg_mode, contra, favor, metricas(rodar(_M5, reg_mode, contra, favor))


CONTRA = [ORIG_C, (5, None, None), (7, None, None)]
CONTRA += [(None, k, None) for k in (0.5, 0.75, 1.0)]
CONTRA += [(None, k, m) for k in (0.5, 0.75, 1.0) for m in (1.0, 1.5, 2.0)]
FAVOR = ["orig", "9x21", "c21", "c34"]


def nomec(c):
    ee, k, m = c
    if c == ORIG_C: return "orig"
    if ee: return f"EMA{ee}"
    return f"stop{k}" + (f"/alvo{m}x" if m else "")


def main():
    m5 = kit.carregar_m5()
    base_kit = kit.resumo(kit.rodar_meses(m5))
    base = metricas(rodar(m5, "vwap", ORIG_C, "orig"))
    print("baseline kit :", base_kit, flush=True)
    print("copia s/ mods:", {k: v for k, v in base.items() if k not in ("liq_janelas", "janelas")}, flush=True)
    assert base["liquido_total"] == base_kit["liquido_total"] and base["trades"] == base_kit["trades"], "NAO REPRODUZ"
    assert abs(base["liquido_total"] - 4968.60) < 0.01 and base["trades"] == 988
    print("REPRODUZ baseline (+4968,60 / 988)", flush=True)

    jobs = [(f"{rm}|C:{nomec(c)}|F:{f}", rm, c, f) for rm in ("vwap", "oraculo") for c in CONTRA for f in FAVOR
            if not (c == ORIG_C and f == "orig")]
    jobs += [(f"{rm}|C:orig|F:{f}", rm, ORIG_C, f) for rm in ("todos", "invertido") for f in ("9x21", "c21", "c34")]
    print(f"variantes (alem do baseline): {len(jobs)}", flush=True)
    R = {}
    with ProcessPoolExecutor(max_workers=6) as ex:
        fs = [ex.submit(_task, j) for j in jobs]
        for f in as_completed(fs):
            nome, rm, c, fv, r = f.result()
            R[nome] = (rm, c, fv, r)
            print(f"{nome:42s} liq={r['liquido_total']:>9} jan+={r['janelas_pos']:>5} pior={r['pior_janela']:>8} "
                  f"PF={r['PF']} trades={r['trades']} DD={r['maior_DD_R$']}", flush=True)
    import pickle
    pickle.dump((base, R), open(AQUI / "hip_c_resultados.pkl", "wb"))
    relatorio(base, R)


def lin(nome, r, base_top):
    liq = r["liq_janelas"]
    lowo = r["liquido_total"] - liq[base_top]
    return (f"| {nome} | {r['liquido_total']:.2f} | {r['janelas_pos']} | {r['pior_janela']:.2f} | {r['PF']} | {r['pts/op']} | "
            f"{r['payoff']} | {r['acerto%']} | {r['trades']} | {r['maior_DD_R$']:.2f} / {r['maior_DD%']}% | {r['fator_recup']} | {lowo:.2f} |")


HDR = ("| variante | líquido R$ | janelas + | pior janela | PF | pts/op | payoff | acerto% | trades | maior DD R$/% | fator recup. | líq. s/ melhor janela do baseline |\n"
       "|---|---|---|---|---|---|---|---|---|---|---|---|")


def relatorio(base, R):
    bt = int(np.argmax(base["liq_janelas"]))
    L = ["# Hipótese C — saída por regime (a favor / contra o mês)\n",
         f"Variantes rodadas: **{len(R)}** (+ baseline). Baseline reproduzido exatamente (+R$4.968,60; 988 trades).",
         f"Janela de maior ganho do baseline (leave-one-out): {base['janelas'][bt]} ({base['liq_janelas'][bt]:.2f}).\n",
         "Nomenclatura: `regime|C:<saída contra>|F:<saída a favor>`; C: orig, EMA5/EMA7, stopK (K×ATR14), /alvoMx (M×stop).\n",
         "## Baseline e melhores (regime VWAP, por líquido)\n", HDR, lin("BASELINE", base, bt)]
    v = {k: x for k, x in R.items() if x[0] == "vwap"}
    for k, x in sorted(v.items(), key=lambda kv: -kv[1][3]["liquido_total"])[:15]:
        L.append(lin(k, x[3], bt))
    L += ["\n## Platô: média por opção (regime VWAP; delta de líquido vs baseline)\n"]
    for eixo, pos, chave in (("saída CONTRA", 1, nomec), ("saída A FAVOR", 2, str)):
        L += [f"**{eixo}** (média sobre as demais opções)\n", "| opção | líquido médio | delta | janelas+ média | n |", "|---|---|---|---|---|"]
        gr = {}
        for k, x in v.items(): gr.setdefault(chave(x[pos]), []).append(x[3])
        for o_, rs in gr.items():
            m = np.mean([r["liquido_total"] for r in rs]); jp = np.mean([int(r["janelas_pos"].split("/")[0]) for r in rs])
            L.append(f"| {o_} | {m:.0f} | {m - base['liquido_total']:+.0f} | {jp:.1f} | {len(rs)} |")
        L.append("")
    L += ["## Controles: a mesma saída solta em TODOS os trades / aplicada ao regime invertido\n", HDR, lin("BASELINE", base, bt)]
    for k, x in R.items():
        if x[0] in ("todos", "invertido"): L.append(lin(k, x[3], bt))
    L += ["\n## Oráculo (regime = direção real do mês) — só teto\n", HDR, lin("BASELINE", base, bt)]
    o = {k: x for k, x in R.items() if x[0] == "oraculo"}
    for k, x in sorted(o.items(), key=lambda kv: -kv[1][3]["liquido_total"])[:8]:
        L.append(lin(k, x[3], bt))
    L += ["\n## Mês a mês — baseline vs. 3 melhores (VWAP)\n"]
    top = sorted(v.items(), key=lambda kv: -kv[1][3]["liquido_total"])[:3]
    L.append("| janela | baseline | " + " | ".join(k for k, _ in top) + " |\n|---|---|" + "---|" * len(top))
    for i, jn in enumerate(base["janelas"]):
        L.append(f"| {jn} | {base['liq_janelas'][i]:.2f} | " + " | ".join(f"{x[3]['liq_janelas'][i]:.2f}" for _, x in top) + " |")
    (AQUI / "hip_c_saida_por_regime_auto.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L), flush=True)


if __name__ == "__main__":
    main()
