"""Hipóteses novas desenhadas sem olhar dados (analista, 2026-10-09), sobre a v4.1.

H1 reentrada depois de stop no mesmo pregão (bloquear / só mesmo lado / reentrar com 1 contrato / só se foi o pivô)
H3 simplificação: tirar um filtro de cada vez; stop fixo
H4 robustez de execução: validade da ordem, fila (FURA), preço do limite
H5 robustez: folga do aperto pela MME38, aquecimento do H4
H6 mão pela volatilidade diária (1 contrato em vol alta)

Critério: pregões de TESTE do IS (fora dos 40 da descoberta): total E total/DD melhores, e comparação pareada por pregão
(bootstrap de 5.000 sobre os pregões) com P(delta > 0) >= 0,90. Quem passar vai ao OOS uma vez.
H4/H5 são de robustez: o que se lê é a distância da base (penhasco ou platô), não "passa".
Uso: python novas.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import estrategia  # noqa: E402
import filtros  # noqa: E402
import indicadores as ind  # noqa: E402
import operacao  # noqa: E402
import stop  # noqa: E402

N_DESC, SEM_DESC = 40, 20261009


# ---------- H1: depois de um stop no pregão ----------
def apos_stop(tr, s, modo):
    """Pós-processa a sequência do dia (exato para 'bloquear' e '1 contrato': as operações seguintes só existem depois da saída)."""
    piv = s.set_index("pos").stop
    out = []
    for _, g in tr.groupby("seg", sort=False):
        parou = None
        for e in g.itertuples():
            if parou is not None:
                if modo == "bloquear": continue
                if modo == "mesmo lado" and e.lado == parou[0]: continue
                if modo == "só se foi o pivô" and parou[1]: continue
                if modo == "1 contrato": e = e._replace(pts=e.pts / 2)
            out.append(e)
            if e.motivo == "stop" and parou is None: parou = (e.lado, e.stop_ini == piv[e.pos])
    return pd.DataFrame(out).drop(columns="Index")


# ---------- H6: volatilidade diária ----------
def vol_alta(b, n=20, limiar=1.0):
    d = b.groupby("dia").agg(h=("high", "max"), l=("low", "min"), c=("close", "last"))
    tr = pd.concat([d.h - d.l, (d.h - d.c.shift()).abs(), (d.l - d.c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean().shift(1)
    med = atr.shift(1).rolling(250, min_periods=60).median()
    return (atr / med > limiar)


def mao_vol(tr, b, n=20, limiar=1.0):
    alta = vol_alta(b, n, limiar).reindex(tr.dia).fillna(False).to_numpy()
    return tr.assign(pts=np.where(alta, tr.pts / 2, tr.pts))


# ---------- infraestrutura ----------
class Ajuste:
    """Troca constantes de módulo durante uma rodada (robustez de parâmetros)."""
    def __init__(self, **kv): self.kv = kv
    def __enter__(self):
        self.velho = {}
        for k, v in self.kv.items():
            mod, nome = k.split(".")
            m = {"operacao": operacao, "stop": stop, "filtros": filtros, "estrategia": estrategia}[mod]
            self.velho[k] = (m, nome, getattr(m, nome)); setattr(m, nome, v)
    def __exit__(self, *a):
        for m, nome, v in self.velho.values(): setattr(m, nome, v)


def limite_deslocado(off_fn):
    orig = operacao.entrada_limitada
    return lambda D, t0, lado, lim, st: orig(D, t0, lado, lim + lado * off_fn(D, t0), st)




def _ramo(b, s, qual):
    L = s.lado.to_numpy()
    if qual == "estoc":
        k = np.asarray(ind.estocastico(b, 14, 3))[s.pos.to_numpy()]
        return np.where(L == 1, k, 100 - k) < 70
    ten, fim = filtros.tendencia_h4(b)
    i = np.searchsorted(fim, b.index.values[s.pos.to_numpy()] + np.timedelta64(15, "m"), side="right") - 1
    return (i >= filtros.AQUECIMENTO_H4) & (ten[np.maximum(i, 0)] == 0)


def sem(*fora, extra=()):
    return tuple(f for f in estrategia.FILTROS_V41 if f not in fora) + tuple(extra)


def variantes():
    """nome -> (grupo, dict(filtros=..., ajuste=..., mover=..., pos=f(tr, b, s)))"""
    V = {}
    for m in ("bloquear", "mesmo lado", "1 contrato", "só se foi o pivô"):
        V[f"após stop no dia: {m}"] = ("H1", dict(pos=lambda tr, b, s, m=m: apos_stop(tr, s, m)))
    for nome, f in (("sem MMS17×34", filtros.mms17_acima_mms34), ("sem MMS72 inclinada", filtros.mms72_open_inclinada),
                    ("sem lado da abertura", filtros.lado_da_abertura)):
        V[nome] = ("H3", dict(filtros=sem(f)))
    V["sem MMS17×34 e sem MMS72"] = ("H3", dict(filtros=sem(filtros.mms17_acima_mms34, filtros.mms72_open_inclinada)))
    V["sinal bom só pelo Estocástico"] = ("H3", dict(filtros=sem(filtros.sinal_bom, extra=(lambda b, s: _ramo(b, s, "estoc"),))))
    V["sinal bom só pelo H4 neutro"] = ("H3", dict(filtros=sem(filtros.sinal_bom, extra=(lambda b, s: _ramo(b, s, "h4"),))))
    V["stop fixo (não move)"] = ("H3", dict(mover=lambda st, t, p, D: st))
    for v in (2, 4, 6): V[f"validade da ordem {v} barras"] = ("H4", dict(ajuste={"operacao.VALIDADE": v}))
    for f in (15, 20): V[f"fila: passar {f} pts"] = ("H4", dict(ajuste={"operacao.FURA": f}))
    V["limite 1 tick pior"] = ("H4", dict(ajuste={"operacao.entrada_limitada": limite_deslocado(lambda D, t0: 5)}))
    V["limite 0,1 ATR melhor"] = ("H4", dict(ajuste={"operacao.entrada_limitada": limite_deslocado(lambda D, t0: -0.1 * D["atr"][t0 - 1])}))
    for f in (0.10, 0.50, 0.75): V[f"folga do aperto {f} ATR"] = ("H5", dict(ajuste={"stop.FOLGA_MIN_ATR": f}))
    for a in (0, 20, 40): V[f"aquecimento H4 {a} barras"] = ("H5", dict(ajuste={"filtros.AQUECIMENTO_H4": a}))
    for n, lim in ((20, 1.0), (20, 0.9), (20, 1.1), (20, 1.25), (10, 1.0), (40, 1.0)):
        V[f"1 contrato se ATR{n} diário > {lim} x mediana"] = ("H6", dict(pos=lambda tr, b, s, n=n, lim=lim: mao_vol(tr, b, n, lim)))
    return V


def rodar(periodo, v, cache):
    aj = v.get("ajuste", {})
    with Ajuste(**aj):
        chave = (periodo, v.get("filtros"), aj.get("filtros.AQUECIMENTO_H4"))
        if chave not in cache:
            with Ajuste(**({"estrategia.FILTROS_V41": v["filtros"]} if "filtros" in v else {})):
                cache[chave] = estrategia.preparar(periodo)
        b, dias, s = cache[chave]
        tr = operacao.operar(s, dias, stop.inicial_v41, v.get("mover", stop.estrutura))
    return v["pos"](tr, b, s) if "pos" in v else tr


def pareado(tr, base, dias_teste, rng):
    d = (tr.groupby("dia").pts.sum().reindex(dias_teste, fill_value=0) - base.groupby("dia").pts.sum().reindex(dias_teste, fill_value=0)).to_numpy()
    boots = d[rng.integers(0, len(d), (5000, len(d)))].sum(axis=1)
    return (boots > 0).mean()


def main():
    cache = {}; rng = np.random.default_rng(7)
    base = rodar("IS", {}, cache)
    datas = np.array(sorted(base.dia.unique()))
    desc = set(np.random.default_rng(SEM_DESC).choice(datas, N_DESC, replace=False))
    sess = [D["dia"] for D in cache[("IS", None, None)][1]]
    dias_teste = pd.DatetimeIndex([d for d in sess if d not in desc])
    teste = lambda tr: tr[tr.dia.isin(dias_teste)]
    rb = operacao.resumo(teste(base))
    print(f"BASE v4.1 TESTE ({len(dias_teste)} pregões): {rb['ops']} ops, total {rb['total']:+.0f}, DD {rb['dd']:.0f}, t/DD {rb['total_dd']:.2f}", flush=True)
    rows, passa = [], []
    for nome, (g, v) in variantes().items():
        tr = rodar("IS", v, cache); r = operacao.resumo(teste(tr)); p = pareado(tr, base, dias_teste, rng)
        ok = r["total"] > rb["total"] and r["total_dd"] > rb["total_dd"] and p >= 0.90
        rows.append(dict(grupo=g, variante=nome, ops=r["ops"], total=r["total"], d_total=r["total"] - rb["total"],
                         d_pct=100 * (r["total"] / rb["total"] - 1), dd=r["dd"], tdd=r["total_dd"], P_melhor=p, passa=ok))
        print(f"{g} {nome:48s} ops {r['ops']:3d} total {r['total']:+8.0f} ({100 * (r['total'] / rb['total'] - 1):+6.1f}%) DD {r['dd']:6.0f} "
              f"t/DD {r['total_dd']:5.2f} P(melhor) {p:.2f}{'  PASSA' if ok else ''}", flush=True)
        if ok and g not in ("H4", "H5"): passa.append((nome, v))
    pd.DataFrame(rows).to_csv(Path(__file__).with_name("resultado_is.csv"), index=False)
    if not passa:
        print("Nenhuma hipótese de melhoria passou no TESTE: OOS não é aberto."); return
    bo = rodar("OOS", {}, cache); ro = operacao.resumo(bo)
    print(f"\nOOS BASE: {ro['ops']} ops, total {ro['total']:+.0f}, DD {ro['dd']:.0f}, t/DD {ro['total_dd']:.2f}")
    for nome, v in passa:
        r = operacao.resumo(rodar("OOS", v, cache))
        ok = r["total"] > ro["total"] and r["total_dd"] > ro["total_dd"]
        print(f"OOS {nome}: total {r['total']:+.0f} ({r['total'] - ro['total']:+.0f}), DD {r['dd']:.0f}, t/DD {r['total_dd']:.2f} -> {'PASSA' if ok else 'falha'}")


if __name__ == "__main__":
    main()
