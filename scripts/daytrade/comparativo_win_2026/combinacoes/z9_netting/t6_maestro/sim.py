"""Z9-T6 EA maestro: posicao liquida = soma dos sinais; custo R$1/contrato por variacao da posicao liquida.
Premissa: cada sub-ordem de cada robo e' enviada separada e executa ao preco_entrada/preco_saida dele (bruto = soma isolada).
Variantes: T6 (sem teto), cap2, cap1 (|pos| <= teto; sinal que estouraria e' ignorado = operacao nao acontece)."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import base  # noqa: E402
PT, CAP0 = 0.20, base.CAPITAL


def filtra(ops, teto):
    if teto is None:
        return ops
    ev = sorted([(r.entrada, 1, i) for i, r in ops.iterrows()] + [(r.saida, 0 if r.saida > r.entrada else 2, i) for i, r in ops.iterrows()],
                key=lambda e: (e[0], e[1]))  # saida antes de entrada no mesmo instante
    pos, aceitas = 0, set()
    for t, tipo, i in ev:
        s = lado_sinal(ops.lado[i])
        if tipo == 1:
            if abs(pos + s) <= teto:
                pos += s; aceitas.add(i)
        elif i in aceitas:  # tipo 0 ou 2 (saida)
            pos -= s
    return ops.loc[sorted(aceitas)].reset_index(drop=True)


def lado_sinal(l):
    return 1 if str(l).upper() in ("C", "COMPRA", "BUY", "1", "LONG", "L") else -1


def simula(ops):
    ops = ops.copy(); ops["s"] = ops.lado.map(lado_sinal)
    ev = []
    for i, r in ops.iterrows():
        ev.append((r.entrada, i, +1)); ev.append((r.saida, i, -1 if r.saida > r.entrada else +2))
    ev.sort(key=lambda e: (e[0], e[2]))
    pos, aberto, real, custo = 0, set(), 0.0, 0.0
    min_real = min_mtm = CAP0; maxabs = 0; dur = {}; ult = None
    saldo_ev = []
    k = 0
    while k < len(ev):
        t = ev[k][0]
        if ult is not None and t.date() == ult.date():
            dur[abs(pos)] = dur.get(abs(pos), 0.0) + (t - ult).total_seconds() / 3600
        d0 = pos
        while k < len(ev) and ev[k][0] == t:
            _, i, tp = ev[k]
            s = ops.s[i]
            if tp == 1: pos += s; aberto.add(i)
            else: pos -= s; aberto.discard(i); real += ops.rs[i]
            k += 1
        custo += abs(pos - d0) * 1.0
        maxabs = max(maxabs, abs(pos))
        liq = CAP0 + real - custo
        mtm = liq + sum(ops.s[i] * (base.preco(t) - ops.preco_entrada[i]) * PT for i in aberto) if aberto else liq
        min_real = min(min_real, liq); min_mtm = min(min_mtm, mtm)
        saldo_ev.append((t, pos, liq, mtm)); ult = t
    s = pd.DataFrame(saldo_ev, columns=["t", "pos", "realizado", "mtm"])
    liq_final = CAP0 + real - custo
    pico = np.maximum.accumulate(np.r_[CAP0, s.mtm.to_numpy()])[1:]
    return dict(liq=round(real - custo, 2), bruto=round(real, 2), custo=round(custo, 2), ops=len(ops),
                contratos=int(2 * len(ops)), dd=round(float((pico - s.mtm).max()), 2), saldo_min_real=round(min_real, 2),
                saldo_min_mtm=round(min_mtm, 2), maxpos=maxabs, margem=100 * maxabs,
                quebra=bool(min_mtm <= 0), dur=dur), s


def main():
    rows, dist = [], []
    for ano in range(2022, 2027):
        ops = base.operacoes(ano)
        iso = base.resumo(ops)[ano]
        ck = float((ops.lado.map(lado_sinal) * (ops.preco_saida - ops.preco_entrada) * PT).sum() - ops.rs.sum())
        for nome, teto in (("T6", None), ("T6-cap2", 2), ("T6-cap1", 1)):
            r, s = simula(filtra(ops, teto))
            d = r.pop("dur"); tot = sum(d.get(k, 0) for k in d if k > 0)
            r.update(ano=ano, variante=nome, check_bruto_vs_precos=round(ck, 2))
            rows.append(r)
            for k, h in sorted(d.items()):
                dist.append(dict(ano=ano, variante=nome, abs_pos=k, horas=round(h, 1)))
            print(ano, nome, {k: v for k, v in r.items() if k not in ("ano", "variante")}, flush=True)
            if nome == "T6": s.to_csv(HERE / f"curva_T6_{ano}.csv", index=False)
        rows.append(dict(ano=ano, variante="isolada(5 contas)", liq=iso["liq"], ops=iso["ops"], dd=iso["dd"], quebra=iso["quebra"]))
        print(ano, "isolada", iso, flush=True)
    pd.DataFrame(rows).to_csv(HERE / "resumo.csv", index=False)
    pd.DataFrame(dist).to_csv(HERE / "dist_posicao.csv", index=False)


if __name__ == "__main__":
    main()
