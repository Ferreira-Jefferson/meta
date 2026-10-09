"""Calendário e horário na v4.1 (2026-10-09): vale a pena NÃO operar em certos dias ou horários?

Candidatos (pular o sinal): vencimento do WIN (quarta mais próxima do dia 15 dos meses pares), véspera, dia seguinte,
semana do vencimento; vencimento de opções de ações (3ª sexta), 2ª quarta do mês, dia da semana, início/fim do mês,
véspera/pós-feriado, 1ª sexta (payroll); janelas de horário da barra de confirmação.

Duas leituras:
  1. Funis do dono, 20 repetições:
     ramo R = 10 dias ruins -> top 10 -> 10 bons + 10 ruins (outros);
     ramo B = 10 dias bons -> top 10 -> 10 bons + 10 ruins.
     Mede quantas vezes cada candidato chega ao fim de cada ramo e se os ramos concordam.
  2. Decisão: IS inteiro (total E total/DD melhores, platô na família) -> OOS uma vez para quem passar.
Uso: python calendario.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import dados  # noqa: E402
import estrategia  # noqa: E402
import operacao  # noqa: E402
import stop  # noqa: E402

REPS, SEMENTE = 20, 20261010


def marcas_de_dia(sessoes):
    """DataFrame indexado pelos pregões com uma coluna booleana por marca de calendário."""
    d = pd.DatetimeIndex(sessoes); s = pd.Series(range(len(d)), index=d)
    venc = pd.DatetimeIndex(dados.vencimentos())
    eh_venc = d.isin(venc)
    i_venc = np.flatnonzero(eh_venc)
    vesp = np.zeros(len(d), bool); vesp[i_venc[i_venc > 0] - 1] = True
    pos = np.zeros(len(d), bool); pos[i_venc[i_venc < len(d) - 1] + 1] = True
    semana = d.to_period("W").isin(venc.to_period("W"))
    terc_sexta = (d.weekday == 4) & (d.day >= 15) & (d.day <= 21)
    i3 = np.flatnonzero(terc_sexta); v3 = np.zeros(len(d), bool); v3[i3[i3 > 0] - 1] = True
    mes = d.to_period("M")
    ordem_mes = s.groupby(mes).cumcount().to_numpy(); resto_mes = s.groupby(mes).cumcount(ascending=False).to_numpy()
    gap_ant = np.r_[1, np.diff(d.values).astype("timedelta64[D]").astype(int)]
    gap_prox = np.r_[np.diff(d.values).astype("timedelta64[D]").astype(int), 1]
    pos_feriado = (gap_ant > 3) | ((gap_ant > 1) & (d.weekday != 0))
    vesp_feriado = (gap_prox > 3) | ((gap_prox > 1) & (d.weekday != 4))
    m = {"vencimento WIN": eh_venc, "véspera do vencimento": vesp, "dia seguinte ao vencimento": pos,
         "véspera ou dia do vencimento": vesp | eh_venc, "semana do vencimento": semana,
         "venc. opções de ações (3ª sexta)": terc_sexta, "véspera da 3ª sexta": v3,
         "2ª quarta do mês": (d.weekday == 2) & (d.day >= 8) & (d.day <= 14), "1ª sexta (payroll)": (d.weekday == 4) & (d.day <= 7),
         "1º pregão do mês": ordem_mes == 0, "3 primeiros pregões do mês": ordem_mes < 3,
         "último pregão do mês": resto_mes == 0, "3 últimos pregões do mês": resto_mes < 3,
         "pós-feriado": pos_feriado, "véspera de feriado": vesp_feriado}
    for k, n in enumerate(("segunda", "terça", "quarta", "quinta", "sexta")): m[n] = d.weekday == k
    return pd.DataFrame(m, index=d)


HORAS = {"conf. antes das 10h": (0, 10), "conf. antes das 10h30": (0, 10.5), "conf. antes das 11h": (0, 11),
         "conf. 12h-14h": (12, 14), "conf. a partir das 15h": (15, 24), "conf. a partir das 16h": (16, 24),
         "conf. a partir das 17h": (17, 24)}
HORAS.update({f"conf. entre {h}h e {h + 1}h": (h, h + 1) for h in range(9, 18)})
FAMILIA = {"vencimento": ["vencimento WIN", "véspera do vencimento", "dia seguinte ao vencimento", "véspera ou dia do vencimento", "semana do vencimento"],
           "manhã": ["conf. antes das 10h", "conf. antes das 10h30", "conf. antes das 11h"],
           "tarde": ["conf. a partir das 15h", "conf. a partir das 16h", "conf. a partir das 17h"],
           "mês início": ["1º pregão do mês", "3 primeiros pregões do mês"], "mês fim": ["último pregão do mês", "3 últimos pregões do mês"]}


def candidatos(b, s, dias):
    marcas = marcas_de_dia([D["dia"] for D in dias])
    dia_sinal = np.array([dias[q]["dia"] for q in s.seg])
    fim_conf = b.index[s.pos.to_numpy()] + pd.Timedelta("15min")
    h = fim_conf.hour + fim_conf.minute / 60
    C = {k: marcas.loc[dia_sinal, k].to_numpy() for k in marcas.columns}
    C.update({k: (h > a) & (h <= z) for k, (a, z) in HORAS.items()})
    return C


def por_dia(tr, sessoes):
    return tr.groupby("dia").pts.sum().reindex(sessoes, fill_value=0.0)


def main():
    pd.set_option("display.width", 220)
    b, dias, s = estrategia.preparar("IS")
    sess = pd.DatetimeIndex([D["dia"] for D in dias])
    roda = lambda mask: operacao.operar(s[~mask] if mask is not None else s, dias, stop.inicial_v41, stop.estrutura)
    base = roda(None); rb = operacao.resumo(base); bd = por_dia(base, sess)
    C = candidatos(b, s, dias)
    D = {k: por_dia(tr, sess) - bd for k, tr in ((k, roda(m)) for k, m in C.items())}  # delta por pregão
    tab = []
    for k, m in C.items():
        r = operacao.resumo(roda(m))
        tab.append(dict(candidato=k, sinais_cortados=int(m.sum()), d_total=r["total"] - rb["total"], dd=r["dd"],
                        d_tdd=r["total_dd"] - rb["total_dd"]))
    tab = pd.DataFrame(tab).set_index("candidato")
    tab["melhora_IS"] = (tab.d_total > 0) & (tab.d_tdd > 0)
    # ---- funis do dono ----
    ruins, bons = bd[bd < 0].index.to_numpy(), bd[bd > 0].index.to_numpy()
    rng = np.random.default_rng(SEMENTE)
    cont = {k: dict(R=0, B=0, ambos=0) for k in C}
    for _ in range(REPS):
        fim = {}
        for ramo, pool in (("R", ruins), ("B", bons)):
            A = rng.choice(pool, 10, replace=False)
            V = np.r_[rng.choice(np.setdiff1d(bons, A), 10, replace=False), rng.choice(np.setdiff1d(ruins, A), 10, replace=False)]
            score = pd.Series({k: D[k].loc[A].sum() for k in C}) + rng.random(len(C)) * 1e-6  # empate: sorteio
            top = score.sort_values(ascending=False).index[:10]
            fim[ramo] = {k for k in top if D[k].loc[V].sum() > 0}
            for k in fim[ramo]: cont[k][ramo] += 1
        for k in fim["R"] & fim["B"]: cont[k]["ambos"] += 1
    tab = tab.join(pd.DataFrame(cont).T.rename(columns=lambda c: f"funil_{c}_de_{REPS}"))
    print(f"BASE IS: {rb['ops']} ops, total {rb['total']:+.0f}, DD {rb['dd']:.0f}, total/DD {rb['total_dd']:.2f}")
    print(tab.sort_values("d_total", ascending=False).round(2).to_string(), flush=True)
    # ---- decisão: IS inteiro + platô na família -> OOS ----
    passa = []
    for k in tab.index[tab.melhora_IS]:
        fam = next((f for f, ks in FAMILIA.items() if k in ks), None)
        viz = [x for x in FAMILIA.get(fam, []) if x != k]
        ok = not viz or (tab.loc[viz, "d_total"] > 0).mean() > 0.5
        print(f"IS melhora: {k} | família {fam}: vizinhos com total maior {int((tab.loc[viz, 'd_total'] > 0).sum())}/{len(viz)} -> {'PASSA' if ok else 'pico'}")
        if ok: passa.append(k)
    if not passa:
        print("Nada passa no IS: OOS não é aberto."); return
    bo, diaso, so = estrategia.preparar("OOS")
    Co = candidatos(bo, so, diaso)
    ro = operacao.resumo(operacao.operar(so, diaso, stop.inicial_v41, stop.estrutura))
    print(f"\nOOS BASE: {ro['ops']} ops, total {ro['total']:+.0f}, DD {ro['dd']:.0f}, total/DD {ro['total_dd']:.2f}")
    for k in passa:
        r = operacao.resumo(operacao.operar(so[~Co[k]], diaso, stop.inicial_v41, stop.estrutura))
        ok = r["total"] > ro["total"] and r["total_dd"] > ro["total_dd"]
        print(f"OOS {k}: cortou {int(Co[k].sum())} sinais, total {r['total']:+.0f} ({r['total'] - ro['total']:+.0f}), DD {r['dd']:.0f}, "
              f"t/DD {r['total_dd']:.2f} -> {'PASSA' if ok else 'falha'}")


if __name__ == "__main__":
    main()
