"""Demos (b) tamanho, (c) mao pequena quando o sinal e fraco, (d) parada no dia.
TODA vantagem aqui e HIPOTETICA (parametro), nao medida. Geometria base alvo 75 / stop 150 pts
(nulo 66,7%); custo 2 pts + 5 de deslize no stop. Capital de partida = minimo real R$250.
Ruina = caixa < R$100 (nao segura 1 contrato)."""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import motor as m

_raw = json.load(open(Path(__file__).parent / "indice_vol.json"))
IDX = {(k.split("|")[0] == "1", int(k.split("|")[1])): v for k, v in _raw.items()}
T0, S0 = 75.0, 150.0
NULO = m.nulo_p(T0, S0)
D, DIAS_MES = 250, 21
SLOTS = 8
VOL_MIN = np.array([m.vol_do_horario(IDX, True, x) for x in range(24 * 60)])


def gera(P, lam, seed, sigma_dia=0.0):
    rng = np.random.default_rng(seed)
    nsig = np.minimum(rng.poisson(lam, size=(P, D)), SLOTS)
    u = rng.random((P, D, SLOTS))
    minuto = rng.integers(9 * 60 + 30, 17 * 60, size=(P, D, SLOTS))
    vidx = VOL_MIN[minuto]
    shift = rng.normal(0, sigma_dia, size=(P, D)) if sigma_dia > 0 else np.zeros((P, D))
    tier = rng.random((P, D, SLOTS))
    return dict(P=P, nsig=nsig, u=u, vidx=vidx, shift=shift, tier=tier)


def simula(G, p_fn, politica, parada=None, caixa0=m.CAPITAL_MINIMO, n0=100.0):
    """p_fn(tier_u)->p verdadeiro do sinal. politica(ctx)->(contratos, T, S) por caminho.
    O p ESTIMADO vem do historico sombra (todos os sinais, operados ou nao)."""
    P = G["P"]
    cash = np.full(P, caixa0, float); vivo = np.ones(P, bool); t_ruina = np.full(P, np.inf)
    k = np.zeros(P); n = np.zeros(P)
    curva = np.zeros((P, D + 1)); curva[:, 0] = caixa0
    res_tr = np.zeros((P, D, SLOTS))
    for d in range(D):
        res_dia = np.zeros(P); nops = np.zeros(P); nstops = np.zeros(P)
        for j in range(SLOTS):
            ativo = vivo & (G["nsig"][:, d] > j)
            if not ativo.any():
                continue
            p_true = np.clip(p_fn(G["tier"][:, d, j]) + G["shift"][:, d], 0.01, 0.99)
            ganhou = G["u"][:, d, j] < p_true
            ctx = dict(cash=cash, k=k, n=n, vidx=G["vidx"][:, d, j], tier=G["tier"][:, d, j], n0=n0)
            ctrt, T, S = politica(ctx)
            if parada is not None:
                pode = (res_dia > -parada.perda_max_brl) & (nops < parada.n_max_ops) & (nstops < parada.n_max_stops) \
                    & (res_dia < parada.ganho_trava_brl)
            else:
                pode = True
            op = ativo & (ctrt > 0) & pode
            pts = np.where(ganhou, T - m.CUSTO_PTS, -(S + m.DESLIZE_STOP_PTS + m.CUSTO_PTS))
            r = np.where(op, pts * m.VALOR_PONTO * ctrt, 0.0)
            cash = cash + r; res_dia += r; nops += op; nstops += (op & ~ganhou)
            res_tr[:, d, j] = r
            k = k + np.where(ativo, ganhou, 0); n = n + ativo
            novo = vivo & (cash < m.MARGEM_CRUA)
            t_ruina[novo] = d + 1; vivo = vivo & ~novo
        curva[:, d + 1] = cash
    return dict(curva=curva, res=res_tr, t_ruina=t_ruina, vivo=vivo)


def metricas(R, caixa0=m.CAPITAL_MINIMO):
    P = R["curva"].shape[0]; c = R["curva"]
    final = c[:, -1]
    ru = ~R["vivo"]
    dd = []; ul = []; mp = []; seq = []; pm = []
    mes = np.repeat(np.arange(D // DIAS_MES + 1), DIAS_MES)[:D]
    for i in range(P):
        cv = c[i]
        if ru[i]:
            cv = cv[: int(R["t_ruina"][i]) + 1]
        dd.append(m.drawdown_max(cv)[0]); ul.append(m.ulcer_index(cv))
        dia_res = np.diff(cv)
        mm = mes[: len(dia_res)]
        ms = np.unique(mm)
        mp.append(np.mean([dia_res[mm == q].sum() > 0 for q in ms]))
        pm.append(min(dia_res[mm == q].sum() for q in ms))
        x = R["res"][i].ravel(); x = x[x != 0]
        seq.append(m.pior_sequencia(x)[0] if len(x) else 0)
    tr = R["t_ruina"][ru]
    return dict(liq_med=float(np.median(final - caixa0)), liq_medio=float(np.mean(final - caixa0)),
                p5=float(np.percentile(final - caixa0, 5)), p95=float(np.percentile(final - caixa0, 95)),
                ruina=float(ru.mean()), t_ruina_med=(float(np.median(tr)) if len(tr) else float("nan")),
                maxdd=float(np.mean(dd)), ulcer=float(np.mean(ul)), meses_pos=float(np.mean(mp)),
                pior_mes=float(np.mean(pm)), pior_seq=float(np.mean(seq)),
                ops=float(np.mean((R["res"] != 0).sum(axis=(1, 2)))))


# ---------- politicas
def _marg(cash):
    return np.where(cash < m.MARGEM_CRUA, 0, np.maximum(1, np.floor(cash / m.MARGEM_POR_CONTRATO_ESCALA)))


def pol_fixo(nc):
    def f(c):
        return np.minimum(nc, _marg(c["cash"])).astype(int), np.full_like(c["cash"], T0), np.full_like(c["cash"], S0)
    return f


def pol_kelly(encolhido, fracao=0.25, n0=100.0, teto=0.25, usa_tier=None):
    def f(c):
        g, l = m.ganho_perda(T0, S0)
        if usa_tier is not None:
            p = usa_tier(c["tier"])
        elif encolhido:
            p = (c["k"] + n0 * NULO) / (c["n"] + n0)
        else:
            p = np.where(c["n"] > 0, c["k"] / np.maximum(c["n"], 1), 0.0)
        ct = m.tamanho_vec(p, g, l, c["cash"], fracao_kelly=fracao, teto_pior_caso=teto)
        return ct, np.full_like(c["cash"], T0), np.full_like(c["cash"], S0)
    return f


def pol_vol(risco=0.10, teto=0.25):
    def f(c):
        v = c["vidx"]
        S = np.maximum(5, np.round(S0 * v / 5) * 5); T = np.maximum(5, np.round(T0 * v / 5) * 5)
        perda_brl = (S + m.DESLIZE_STOP_PTS + m.CUSTO_PTS) * m.VALOR_PONTO
        n = np.maximum(np.floor(risco * c["cash"] / perda_brl), 1)
        n = np.where(perda_brl <= teto * c["cash"], n, 0)
        return np.minimum(n, _marg(c["cash"])).astype(int), T, S
    return f


def p_edge(delta):
    return lambda u: np.full_like(u, NULO + delta)


def fmt(df):
    pd.set_option("display.width", 250)
    return df.round(3).to_string()


def demo_b(P=2000):
    cenarios = [("nulo (sem vantagem)", 0.0, 1.0), ("+4pp", 0.04, 1.0), ("+15pp raro (tipo R29)", 0.15, 0.3)]
    pols = [("fixo 1", pol_fixo(1)), ("Kelly 1/4 ingenuo", pol_kelly(False)),
            ("Kelly 1/4 encolhido n0=100", pol_kelly(True)), ("tamanho por volatilidade", pol_vol())]
    out = []
    for nome, dl, lam in cenarios:
        G = gera(P, lam, seed=11)
        for pn, pf in pols:
            r = metricas(simula(G, p_edge(dl), pf)); r.update(cenario=nome, politica=pn); out.append(r)
    df = pd.DataFrame(out).set_index(["cenario", "politica"])
    df.to_csv("demo_b.csv", sep=";", decimal=",")
    return df


def demo_c(P=1500):
    def p_tier(u):  # HIPOTETICO: forte 20% (+12pp), medio 30% (+4pp), fraco 50% (-2pp)
        return NULO + np.where(u < 0.2, 0.12, np.where(u < 0.5, 0.04, -0.02))
    out = []
    for cap in (250.0, 1000.0):
        G = gera(P, 1.0, seed=21)
        pols = [("sempre 1 contrato (entra em tudo)", pol_fixo(1)), ("sempre 2 contratos (entra em tudo)", pol_fixo(2)),
                ("Kelly 1/4 por tipo", pol_kelly(False, usa_tier=p_tier)),
                ("Kelly 1/2 por tipo", pol_kelly(False, fracao=0.5, usa_tier=p_tier))]
        for pn, pf in pols:
            r = metricas(simula(G, p_tier, pf, caixa0=cap), cap); r.update(capital=cap, politica=pn); out.append(r)
    df = pd.DataFrame(out).set_index(["capital", "politica"])
    df.to_csv("demo_c.csv", sep=";", decimal=",")
    return df


def demo_d(P=2000):
    regras = [("sem parada", None), ("max 2 operacoes/dia", m.ParadaDia(n_max_ops=2)),
              ("max 1 stop/dia", m.ParadaDia(n_max_stops=1)), ("perda max R$40/dia", m.ParadaDia(perda_max_brl=40.0)),
              ("perda max R$40 + max 2 stops", m.ParadaDia(perda_max_brl=40.0, n_max_stops=2))]
    cen = [("nulo, dias iid", 0.0, 0.0), ("+4pp, dias iid", 0.04, 0.0),
           ("+4pp, dias ruins persistem (sigma 6pp)", 0.04, 0.06), ("nulo, dias ruins persistem (sigma 6pp)", 0.0, 0.06)]
    out = []
    for nome, dl, sg in cen:
        G = gera(P, 3.0, seed=31, sigma_dia=sg)
        for rn, pr in regras:
            r = metricas(simula(G, p_edge(dl), pol_fixo(1), parada=pr)); r.update(cenario=nome, regra=rn); out.append(r)
    df = pd.DataFrame(out).set_index(["cenario", "regra"])
    df.to_csv("demo_d.csv", sep=";", decimal=",")
    return df


if __name__ == "__main__":
    print(fmt(dict(b=demo_b, c=demo_c, d=demo_d)[sys.argv[1]]()))
