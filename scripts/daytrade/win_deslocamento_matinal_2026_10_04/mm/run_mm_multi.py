"""Confirmacao com varias medias (EMA sobre M5/M15) sobre win_deslocamento_matinal.
Uso: run_mm_multi.py [analise]   (sem argumento: roda IS e OOS e depois analisa)"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import comum as c  # noqa: E402


def _ema(prev, x, n):
    a = 2.0 / (n + 1)
    return x if prev is None else prev + a * (x - prev)


@dataclass
class WinMulti(c.WinDeslocamentoMatinal):
    periodos: tuple = ()          # () = sem filtro
    modo: str = ""                # 'P' preco do lado de todas; 'O' empilhadas; 'PO' ambas
    tf: int = 5                   # minutos da barra das EMAs
    _bk: object = field(default=None, init=False, repr=False)
    _last: float = field(default=0.0, init=False, repr=False)
    _n: int = field(default=0, init=False, repr=False)
    _emas: dict = field(default_factory=dict, init=False, repr=False)
    n_aquec_min: int = field(default=10**9, init=False, repr=False)

    def _fecha(self):
        for n in self.periodos:
            self._emas[n] = _ema(self._emas.get(n), self._last, n)
        self._n += 1

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        b = ts.floor(f"{self.tf}min")
        if self._bk is not None and b != self._bk:
            self._fecha()
        self._bk = b
        self._last = bar.close
        antes = len(self.sinais)
        acts = super().on_bar(ts, bar, positions, session_pnl_brl)
        if not acts or not self.periodos:
            return acts
        a = acts[0]
        lado = 1.0 if a.side == "long" else -1.0
        px = bar.close
        # barra do bucket corrente completa na decisao (10:29): EMA provisoria incluindo-a
        e = [_ema(self._emas.get(n), px, n) for n in self.periodos]
        self.n_aquec_min = min(self.n_aquec_min, self._n)
        ok = self._n >= 3 * max(self.periodos)          # aquecido (barras fechadas)
        if ok and "P" in self.modo:
            ok = all(lado * (px - v) > 0 for v in e)
        if ok and "O" in self.modo:
            ok = all(lado * (e[i] - e[i + 1]) > 0 for i in range(len(e) - 1))
        if not ok:
            del self.sinais[antes:]
            return []
        return acts


CELULAS = {
    "BASE": {},
    "A_e10": dict(periodos=(10,), modo="P"),
    "E100": dict(periodos=(100,), modo="P"),
    "P3": dict(periodos=(10, 21, 50), modo="P"),
    "O3": dict(periodos=(10, 21, 50), modo="O"),
    "PO3": dict(periodos=(10, 21, 50), modo="PO"),
    "P4": dict(periodos=(10, 21, 50, 100), modo="P"),
    "O4": dict(periodos=(10, 21, 50, 100), modo="O"),
    "PO4": dict(periodos=(10, 21, 50, 100), modo="PO"),
    "P3_M15": dict(periodos=(10, 21, 50), modo="P", tf=15),
    "P4_M15": dict(periodos=(10, 21, 50, 100), modo="P", tf=15),
}
BASE = dict(desloc_min_atr=0.3, stop_atr=None, alvo_atr=None)


def unid(cid, ini, fim, prem):
    c.WinDeslocamentoMatinal = WinMulti
    r = c.unidade("WIN@", ini, fim, {**BASE, **CELULAS[cid]}, prem, True)
    r["cid"] = cid
    r["texto"] = r["texto"].replace(c.nome_celula(BASE), f"{cid:<7}", 1)
    return r


JAN = {"IS": ("2021-10-01", "2024-12-31"), "OOS": ("2025-01-01", "2026-09-30")}


def roda(modo):
    ini, fim = JAN[modo]
    out, cab = [], False
    with ProcessPoolExecutor(max_workers=3) as ex:
        fut = [ex.submit(unid, i, ini, fim, p) for i in CELULAS for p in ("P2", "P0")]
        for f in as_completed(fut):
            r = f.result()
            if not cab:
                print(r["cab"], flush=True); cab = True
            print(f"[{modo} {r['premissa']}] " + r["texto"], flush=True)
            out.append(r)
    (HERE / f"saida_multi_{modo}.json").write_text(json.dumps(out, default=str), encoding="utf-8")


# ---------------------------------------------------------------- analise
def dd(p):
    eq = np.cumsum(p); pico = np.maximum.accumulate(np.concatenate([[0], eq]))[1:]
    return float((pico - eq).max())


def seq(p):
    m = k = 0
    for v in p:
        k = k + 1 if v < 0 else 0; m = max(m, k)
    return m


def ic(t):
    from types import SimpleNamespace
    tr = [SimpleNamespace(entry_ts=pd.Timestamp(x["entry_ts"]), pnl_brl=x["pnl"]) for x in t]
    return c.estatisticas(tr)


def metr(t):
    if not t:
        return {}
    p = np.array([x["pnl"] for x in t]); g = p[p > 0]; l = p[p < 0]
    st = [x for x in t if x["reason"] == "STOP"]; fl = [x for x in t if x["reason"] != "STOP"]
    s = ic(t); md = dd(p)
    gm = g.mean() if len(g) else 0.0; pm = -l.mean() if len(l) else np.nan
    return {"n": len(p), "liq": p.sum(), "r_op": p.mean(), "ic": f"[{s['ic_lo']:.0f};{s['ic_hi']:.0f}]",
            "acerto": 100 * (p > 0).mean(), "be": s["be"], "gan": gm, "perda": pm, "payoff": gm / pm if pm == pm else np.nan,
            "fator": g.sum() / -l.sum() if len(l) else np.nan, "stops": len(st), "stop_rs": sum(x["pnl"] for x in st),
            "fim_dia": len(fl), "fim_win": 100 * sum(x["pnl"] > 0 for x in fl) / max(len(fl), 1),
            "maxdd": md, "fr": p.sum() / md if md else np.nan, "seq": seq(p)}


def cortados(base, filt):
    k = {x["entry_ts"][:10] for x in filt}
    cc = [x for x in base if x["entry_ts"][:10] not in k]
    return len(cc), sum(x["pnl"] for x in cc), sum(x["reason"] == "STOP" for x in cc)


def analisa():
    md = ["# Confirmacao com varias medias (EMA) -- win_deslocamento_matinal\n",
          "EMA sobre M5 (M15 onde indicado), decisao 10:30, fila P2, capital reposto por pregao. "
          "OOS ja vista na rodada anterior (nao cega): veredito = consistencia IS + OOS + ano a ano.\n"]
    anos_t = {}
    for modo in ("IS", "OOS"):
        rs = json.loads((HERE / f"saida_multi_{modo}.json").read_text())
        d = {(r["cid"], r["premissa"]): r["trades"] for r in rs}
        rows = []
        for cid in CELULAS:
            for prem in ("P2", "P0"):
                m = metr(d[(cid, prem)]); m.update(celula=cid, prem=prem)
                if cid != "BASE":
                    cn = cortados(d[("BASE", prem)], d[(cid, prem)])
                    m.update(cort_n=cn[0], cort_rs=cn[1], cort_stops=cn[2])
                rows.append(m)
        df = pd.DataFrame(rows).set_index(["celula", "prem"])
        df.reset_index().to_csv(HERE / f"multi_{modo}.csv", index=False, sep=";", decimal=",")
        p2 = df.xs("P2", level="prem")
        show = ["n", "liq", "r_op", "ic", "acerto", "be", "gan", "perda", "payoff", "fator", "stops", "stop_rs", "fim_dia", "fim_win", "maxdd", "fr", "seq"]
        md.append(f"\n## {modo} (P2)\n")
        md.append("|celula|" + "|".join(show) + "|\n|" + "---|" * (len(show) + 1))
        for cid, r in p2.iterrows():
            md.append(f"|{cid}|" + "|".join(r[k] if isinstance(r[k], str) else f"{r[k]:.1f}" for k in show) + "|")
        md.append(f"\n### Cortados vs BASE ({modo}, P2)\n\n|celula|n cortados|soma R$|stops entre eles|\n|---|---|---|---|")
        for cid, r in p2.iterrows():
            if cid != "BASE":
                md.append(f"|{cid}|{int(r['cort_n'])}|{r['cort_rs']:.1f}|{int(r['cort_stops'])}|")
        for cid in CELULAS:
            ap = {}
            for x in d[(cid, "P2")]:
                y = int(x["entry_ts"][:4]); ap[y] = ap.get(y, 0.0) + x["pnl"]
            anos_t.setdefault(cid, {}).update(ap)
    md.append("\n## Liquido por ano (P2)\n\n|celula|2022|2023|2024|2025|2026|anos > BASE|\n|---|---|---|---|---|---|---|")
    for cid, a in anos_t.items():
        sup = sum(a.get(y, 0) > anos_t["BASE"].get(y, 0) for y in (2022, 2023, 2024, 2025, 2026))
        md.append(f"|{cid}|" + "|".join(f"{a.get(y, 0):.0f}" for y in (2022, 2023, 2024, 2025, 2026)) + f"|{sup}/5|")
    (HERE / "RESUMO_MM_MULTI.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "analise":
        analisa()
    else:
        roda("IS"); roda("OOS"); analisa()
