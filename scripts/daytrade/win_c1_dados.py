"""Dados da pagina win_c1: roda o replay de ticks (win_replay_ticks) e monta, por operacao, os candles M5 do dia,
roxa/verde e a trajetoria do stop. Saida: .claude/artifacts/win_c1/c1_dados.json (lista, mais recente primeiro).
Janelas j1/j2 = C1 sem BE (Win.mq5 v2.04 / BreakEvenMinutos=0); j1be/j2be = C1 com BE a mercado (v2.05, 15 min, colchao 7 pts).
Uso: python win_c1_dados.py            -> recalcula so' as janelas BE e preserva as demais ja' gravadas no json
     python win_c1_dados.py --tudo     -> recalcula todas"""
import json, sys
from datetime import date
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import win_replay_ticks as rp

OUT = rp.ROOT / ".claude" / "artifacts" / "win_c1"
BE = {"be_minutos": 15, "be_colchao_pts": 7.0}
JANELAS = [   # ordem = ordem das abas (mais recente primeiro)
    dict(id="j1be", ativo="WINV26", ini=date(2026, 8, 12), fim=date(2026, 10, 1), params=BE),
    dict(id="j2be", ativo="WIN@D", ini=date(2026, 6, 2), fim=date(2026, 10, 1), params=BE),
    dict(id="j1", ativo="WINV26", ini=date(2026, 8, 12), fim=date(2026, 10, 1), params={}),
    dict(id="j2", ativo="WIN@D", ini=date(2026, 6, 2), fim=date(2026, 10, 1), params={}),
]
MOT = {"stop": "stop_roxa", "canal": "canal", "esticada": "esticada", "zera": "fim de pregão", "stop_alcancado": "stop_alcancado", "break_even": "break_even"}
fmt = lambda s: pd.Timestamp(s).strftime("%Y-%m-%d %H:%M:%S")


_M1 = {}


def _ticks_sinteticos(ativo, dia):
    """WIN@D nao tem bid/ask (so' last): ticks sinteticos a partir das M1 -- abertura, extremos (ordem pela cor da barra) e
    fechamento, com bid = ask = preco. Sem spread: otimista em nivel."""
    m1 = _M1[ativo]
    x = m1[m1.index.date == dia]
    t, px = [], []
    for ts, r in zip(x.index, x.itertuples()):
        seq = (r.open, r.low, r.high, r.close) if r.close >= r.open else (r.open, r.high, r.low, r.close)
        for q, v in enumerate(seq):
            t.append(pd.Timestamp(ts).value // 10**6 + q * 15000); px.append(v)
    px = np.array(px, dtype=float)
    return np.array(t, dtype=np.int64), px, px, px


def janela(j):
    p = dict(rp.PARAMS_PADRAO)
    if j["ativo"] == "WIN@D":
        _M1[j["ativo"]] = rp.carregar_m1(j["ativo"], j["ini"], j["fim"])
        rp.carregar_ticks = _ticks_sinteticos
    pr = lambda k, n, m: print(f"  [{j['id']} {k}/{n}] {m}", flush=True) if k % 10 == 0 else None
    r = rp.replay(j["ini"], j["fim"], 0.0, "fixa", j.get("params", {}), j["ativo"], pr)
    bem = int(j.get("params", {}).get("be_minutos", 0))
    bars = rp.preparar_barras(rp.carregar_m1(j["ativo"], j["ini"], j["fim"]), p)
    t = pd.DataFrame(r["trades"])
    t["te"], t["tx"] = pd.to_datetime(t.te), pd.to_datetime(t.tx)
    t = t.sort_values("te").reset_index(drop=True)
    dias = []
    for dia, g in t.groupby("dia"):
        b = bars[bars.index.date == date.fromisoformat(dia)]
        W, S, A = b.wma.to_numpy(), b.smma.to_numpy(), b.atr.to_numpy()
        ops = []
        for o in g.itertuples():
            k0 = b.index.searchsorted(o.te.floor("5min") - pd.Timedelta(minutes=5))  # vela do sinal
            path = []
            for k in range(k0, len(b)):
                tb = b.index[k] + pd.Timedelta(minutes=5)
                if tb > o.tx: break
                if np.isnan(A[k]): continue
                path.append([fmt(tb if k > k0 else o.te), float(rp._arred(W[k] + o.d * p["k_atr"] * A[k]))])
            dl = o.te.floor("5min") + pd.Timedelta(minutes=bem) if bem else None   # vencimento do BE (abertura da M5 de entrada + N min)
            ops.append(dict(te=fmt(o.te), ts=fmt(o.tx), d=int(o.d), e=o.pe, x=o.px, rs=round(o.rs, 2), mot=MOT[o.mot],
                            pts=int(round((o.px - o.pe) * o.d)), stop=path, **({"dl": fmt(dl)} if dl is not None and dl <= o.tx else {})))
        dias.append(dict(dia=dia, liq=round(float(g.rs.sum()), 2), n=len(g), win=int((g.rs > 0).sum()),
            t=[fmt(i) for i in b.index], o=b.open.tolist(), h=b.high.tolist(), l=b.low.tolist(), c=b.close.tolist(),
            w=[None if pd.isna(v) else round(v, 1) for v in b.wma], s=[None if pd.isna(v) else round(v, 1) for v in b.smma], ops=ops))
    tt = t.sort_values("tx")
    por_hora = []
    for h, g in t.groupby(t.te.dt.hour):
        gg, pp = g.rs[g.rs > 0].sum(), -g.rs[g.rs < 0].sum()
        por_hora.append(dict(h=int(h), n=len(g), liq=round(float(g.rs.sum()), 2), win=round(100 * float((g.rs > 0).mean()), 1), pf=round(float(gg / pp), 2) if pp else None))
    curva = [[fmt(x), round(float(v), 2)] for x, v in zip(tt.tx, tt.rs.cumsum())]
    return dict(id=j["id"], be=bem, ativo=j["ativo"], ini=str(j["ini"]), fim=str(j["fim"]), resumo=r["resumo"], por_mes=r["por_mes"], por_hora=por_hora,
                curva=curva, dias=dias, sem_ticks=r["dias_sem_ticks"], avisos=r["avisos"],
                por_motivo=[dict(mot=MOT[m], n=len(g), liq=round(float(g.rs.sum()), 2)) for m, g in t.groupby("mot")])


if __name__ == "__main__":
    from concurrent.futures import ProcessPoolExecutor, as_completed
    OUT.mkdir(parents=True, exist_ok=True)
    arq = OUT / "c1_dados.json"
    antigo = {r["id"]: r for r in json.loads(arq.read_text(encoding="utf-8"))} if arq.exists() else {}
    fazer = [j for j in JANELAS if "--tudo" in sys.argv or j["id"].endswith("be") or j["id"] not in antigo]
    novo = dict(antigo)
    with ProcessPoolExecutor(min(8, len(fazer))) as ex:
        fu = {ex.submit(janela, j): j["id"] for j in fazer}
        for f in as_completed(fu):
            r = f.result(); novo[r["id"]] = r
            print(r["id"], r["ativo"], r["resumo"], r["sem_ticks"], r["avisos"][:2], r["por_motivo"], flush=True)
    res = [novo[j["id"]] for j in JANELAS]
    arq.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
