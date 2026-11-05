"""Olhar para trás e repetir: WIN M5, pedido do dono em 2026-10-15.

Mecanismo: no instante T o robô olha os últimos L minutos e pergunta "que regra teria ganho aqui?". Escolhe, numa
biblioteca FIXA de regras (gatilho + confirmação + saída), a de maior resultado líquido nos trades que começaram
e terminaram dentro da janela, e só aceita se ela ganhou de fato. Depois espera até W minutos pelo MESMO sinal; se
aparecer, entra e sai pela saída da regra. Fechada a posição (ou vencido W sem trade), olha para trás de novo.

Variantes: A = pode escolher de novo a mesma regra; B = nunca a regra que acabou de usar ("não ficar repetindo").
Execução (desenho fechado do repo): entrada por limite no close da barra do sinal, válida 2 barras, só enche se o
preço passar 1 tick além; alvo por limite (mesma regra de fila); stop a mercado, pelo pior entre a abertura e o
stop; níveis ancorados no preço de entrada; zera no close da última barra contínua. 1 contrato, custo 10 pts.

Régua escrita ANTES de rodar:
  - "bom" num conjunto de dias = líquido > 0 E p < 0,10 contra o nulo (mesmo ciclo, escolha ao acaso entre as regras
    que TAMBÉM ganharam no retrovisor). O nulo isola a pergunta: escolher a melhor do passado recente ajuda?
  - A config literal do dono é L30/W30/A/min1. Ela é a pré-registrada; as outras 47 entram com Benjamini-Hochberg
    q=0,10 sobre os 48 p-valores (p combinado dos dois conjuntos = máximo dos dois).
  - Fase 2 (10 dias novos) só roda para o que for "bom" nos DOIS conjuntos.

Dias: últimos dois meses (2026-08-14 a 2026-10-14; 09/10 fora, a base só vai até 11:19). Sorteio com semente fixa:
um bloco de 10 pregões seguidos, 10 aleatórios do resto, e 10 aleatórios do que sobrar ficam para a fase 2.

Uso: python scripts/daytrade/olhar_para_tras/olhar_para_tras.py [--fase 2 --configs L30W30Am1,...]
"""
import argparse
import os
import sys
import zlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "src"))
from backtest.intraday.report import LinhaResultado, maxdd_brl, tabela, num_br  # noqa: E402
from market_data_intraday.bases_versionadas import le_win  # noqa: E402

INI, FIM, FORA = "2026-08-14", "2026-10-15", {"2026-10-09"}
AQUECE = "2026-06-01"
TICK, FURA, CUSTO, VALIDADE, PT_BRL = 5.0, 5.0, 10.0, 2, 0.20
CAPITAL, MARGEM = 250.0, 100.0  # WIN: margem R$100 x 2 x 1,25 (piso real de partida)
CORTE_SINAL = "17:45"
SEMENTE, N_NULO = 20261015, 200

GATILHOS = ["cor", "rompe3", "rompe6", "cruz_mme9_21", "cruz_preco_mme21", "seq3", "ifr7", "recuo_mme9",
            "cruz_vwap", "barra_interna"]
CONFIRMA = ["nenhuma", "vwap", "inclin_mme21"]
SAIDAS = [("fixa", k, m) for k in (0.5, 1.0, 1.5) for m in (0.5, 1.0, 1.5, 2.0, None)] + \
         [("trail_atr", 1.0, None), ("trail_mme9", 1.0, None)]
N_SINAIS = len(GATILHOS) * 2 * len(CONFIRMA)
N_REGRAS = N_SINAIS * len(SAIDAS)


# ---------------------------------------------------------------- dados
def carrega():
    m1 = le_win("m1_WIN$N.parquet")
    m1 = m1[(m1.index >= AQUECE) & (m1.index < FIM)]
    m1 = m1[~m1.index.normalize().isin(pd.to_datetime(sorted(FORA)))]
    b = m1.resample("5min").agg(dict(open="first", high="max", low="min", close="last", real_volume="sum")).dropna()
    b["dia"] = b.index.normalize()
    pc = b.close.shift(1).where(b.dia == b.dia.shift(1))
    tr = pd.concat([b.high - b.low, (b.high - pc).abs(), (b.low - pc).abs()], axis=1).max(axis=1)
    b["atr"] = tr.rolling(14, min_periods=5).mean()  # conhecido no close da própria barra
    b["e9"] = b.close.ewm(span=9, adjust=False).mean()
    b["e21"] = b.close.ewm(span=21, adjust=False).mean()
    d = b.close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 7, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 7, adjust=False).mean()
    b["ifr"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    tp = (b.high + b.low + b.close) / 3
    b["vwap"] = (tp * b.real_volume).groupby(b.dia).cumsum() / b.real_volume.groupby(b.dia).cumsum()
    return b[b.index >= INI]


def sinais_do_dia(D):
    """sig[g, t] in {-1, 0, +1}: lado do trade da regra de sinal g no close da barra t."""
    o, h, l, c, e9, e21, ifr, vw, a = (D[k] for k in ("open", "high", "low", "close", "e9", "e21", "ifr", "vwap", "atr"))
    n = len(c)
    def prev(x, k=1):
        y = np.full(n, np.nan); y[k:] = x[:-k]; return y
    cp, e9p, e21p, ifrp, vwp = prev(c), prev(e9), prev(e21), prev(ifr), prev(vw)
    hmax = {N: pd.Series(h).shift(1).rolling(N).max().to_numpy() for N in (3, 6)}
    lmin = {N: pd.Series(l).shift(1).rolling(N).min().to_numpy() for N in (3, 6)}
    alta = c > o
    baixa = c < o
    base = {
        "cor": (c - o > 0.3 * a, o - c > 0.3 * a),
        "rompe3": (c > hmax[3], c < lmin[3]),
        "rompe6": (c > hmax[6], c < lmin[6]),
        "cruz_mme9_21": ((e9 > e21) & (e9p <= e21p), (e9 < e21) & (e9p >= e21p)),
        "cruz_preco_mme21": ((c > e21) & (cp <= e21p), (c < e21) & (cp >= e21p)),
        "seq3": (alta & prev(alta.astype(float)).astype(bool) & prev(alta.astype(float), 2).astype(bool),
                 baixa & prev(baixa.astype(float)).astype(bool) & prev(baixa.astype(float), 2).astype(bool)),
        "ifr7": ((ifr > 30) & (ifrp <= 30), (ifr < 70) & (ifrp >= 70)),
        "recuo_mme9": ((e9 > e21) & (l <= e9) & (c > e9), (e9 < e21) & (h >= e9) & (c < e9)),
        "cruz_vwap": ((c > vw) & (cp <= vwp), (c < vw) & (cp >= vwp)),
        "barra_interna": ((prev(h) <= prev(h, 2)) & (prev(l) >= prev(l, 2)) & (c > prev(h)),
                          (prev(h) <= prev(h, 2)) & (prev(l) >= prev(l, 2)) & (c < prev(l))),
    }
    corte = D["corte"]
    sig = np.zeros((N_SINAIS, n), dtype=np.int8)
    g = 0
    for nome in GATILHOS:
        lg, sh = base[nome]
        lado0 = np.where(np.nan_to_num(lg).astype(bool), 1, np.where(np.nan_to_num(sh).astype(bool), -1, 0))
        lado0[:2] = 0
        lado0[corte:] = 0
        lado0[np.isnan(a)] = 0
        for d in (1, -1):
            lado = lado0 * d
            for cf in CONFIRMA:
                if cf == "nenhuma":
                    ok = np.ones(n, bool)
                elif cf == "vwap":
                    ok = np.sign(c - vw) == lado
                else:
                    ok = np.sign(e21 - e21p) == lado
                sig[g] = np.where(ok, lado, 0)
                g += 1
    return sig


def rnd(x):
    return np.round(x / TICK) * TICK


def trades_do_dia(D):
    """Para cada lado, barra de sinal e saída: barra de entrada (-1 = não encheu), barra de saída e pts líquidos."""
    o, h, l, c, a, e9 = (D[k] for k in ("open", "high", "low", "close", "atr", "e9"))
    n = len(c)
    ent = np.full((2, n, len(SAIDAS)), -1, dtype=np.int32)
    sai = np.full((2, n, len(SAIDAS)), -1, dtype=np.int32)
    pts = np.full((2, n, len(SAIDAS)), np.nan)
    for si, s in enumerate((1, -1)):
        for t in range(n - 1):
            if np.isnan(a[t]):
                continue
            lim = c[t]
            for ei, (tipo, k, m) in enumerate(SAIDAS):
                stop0 = rnd(lim - s * k * a[t])
                u, px = -1, np.nan
                for v in range(t + 1, min(t + 1 + VALIDADE, n)):
                    tocou_stop = l[v] <= stop0 if s == 1 else h[v] >= stop0
                    furou = l[v] <= lim - FURA if s == 1 else h[v] >= lim + FURA
                    if tocou_stop or furou:
                        u, px = v, (min(o[v], lim) if s == 1 else max(o[v], lim))
                        break
                if u < 0:
                    continue
                stop = rnd(px - s * k * a[t])
                alvo = None if m is None else rnd(px + s * m * a[t])
                saida, vs = c[-1], n - 1
                for v in range(u, n):
                    ot = px if v == u else o[v]
                    if (l[v] <= stop) if s == 1 else (h[v] >= stop):
                        saida, vs = (min(ot, stop) if s == 1 else max(ot, stop)), v
                        break
                    if alvo is not None and v > u and ((h[v] >= alvo + FURA) if s == 1 else (l[v] <= alvo - FURA)):
                        saida, vs = (max(o[v], alvo) if s == 1 else min(o[v], alvo)), v
                        break
                    if tipo == "trail_atr":
                        novo = rnd(c[v] - s * k * a[t])
                        stop = max(stop, novo) if s == 1 else min(stop, novo)
                    elif tipo == "trail_mme9" and (e9[v] - px) * s > 0:
                        novo = rnd(e9[v])
                        stop = max(stop, novo) if s == 1 else min(stop, novo)
                ent[si, t, ei], sai[si, t, ei], pts[si, t, ei] = u, vs, s * (saida - px) - CUSTO
    return ent, sai, pts


def prepara_dia(b, dia):
    x = b[b.dia == dia]
    D = {k: x[k].to_numpy(float) for k in ("open", "high", "low", "close", "atr", "e9", "e21", "ifr", "vwap")}
    D["hora"] = x.index.strftime("%H:%M").to_numpy()
    D["corte"] = int(np.searchsorted(D["hora"], CORTE_SINAL, side="right"))
    D["dia"] = str(dia.date())
    D["sig"] = sinais_do_dia(D)
    D["ent"], D["sai"], D["pts"] = trades_do_dia(D)
    # vista por regra r = g * len(SAIDAS) + e: lado, entrada, saída, pts em cada barra de sinal
    sig = D["sig"]
    lado_r = np.repeat(sig, len(SAIDAS), axis=0)  # (N_REGRAS, n)
    e_idx = np.tile(np.arange(len(SAIDAS)), N_SINAIS)[:, None]
    si = np.where(lado_r == -1, 1, 0)
    t_idx = np.arange(sig.shape[1])[None, :]
    D["lado_r"] = lado_r
    D["ent_r"] = D["ent"][si, t_idx, e_idx]
    D["sai_r"] = D["sai"][si, t_idx, e_idx]
    D["pts_r"] = D["pts"][si, t_idx, e_idx]
    return D


# ---------------------------------------------------------------- o ciclo
def retrovisor(D, T, nL):
    """Resultado de cada regra nos trades que começaram e terminaram em [T-nL, T-1], uma posição por vez."""
    ocupado = np.full(N_REGRAS, -1, dtype=np.int64)
    total = np.zeros(N_REGRAS)
    cont = np.zeros(N_REGRAS, dtype=np.int32)
    for t in range(max(T - nL, 0), T):
        at = (D["lado_r"][:, t] != 0) & (t > ocupado)
        if not at.any():
            continue
        e, s, p = D["ent_r"][:, t], D["sai_r"][:, t], D["pts_r"][:, t]
        sem = at & (e < 0)
        ocupado[sem] = t + VALIDADE
        com = at & (e >= 0)
        fecha = com & (s <= T - 1)
        total[fecha] += p[fecha]
        cont[fecha] += 1
        ocupado[fecha] = s[fecha]
        ocupado[com & ~fecha] = 10 ** 9
    return total, cont


def roda_dia(D, nL, nW, variante, min_n, modo="melhor", rng=None, estilo="normal"):
    """estilo: normal = segue a regra que mais ganhou; inverso = mesma escolha, entra do lado CONTRÁRIO ao sinal
    (mesmo stop/alvo); pior = segue a regra que mais PERDEU no retrovisor. O nulo usa o mesmo estilo."""
    n = len(D["hora"])
    T, ultima, out = nL, -1, []
    while T < D["corte"]:
        total, cont = retrovisor(D, T, nL)
        elegivel = (cont >= min_n) & ((total < 0) if estilo == "pior" else (total > 0))
        if variante == "B" and ultima >= 0:
            elegivel[ultima] = False
        if modo == "acaso_todas":
            elegivel = np.ones(N_REGRAS, bool)
        if not elegivel.any():
            T += 1
            continue
        if modo == "melhor":
            sc = -total if estilo == "pior" else total
            score = np.where(elegivel, sc + 1e-6 * cont, -np.inf)
            r = int(np.argmax(score))
        else:
            r = int(rng.choice(np.flatnonzero(elegivel)))
        t, fim_janela, operou = T, min(T + nW, D["corte"]), False
        while t < fim_janela:
            if D["lado_r"][r, t] != 0:
                if estilo == "inverso":
                    si, ei = (1 if D["lado_r"][r, t] == 1 else 0), r % len(SAIDAS)
                    e, s, pts = D["ent"][si, t, ei], D["sai"][si, t, ei], D["pts"][si, t, ei]
                else:
                    e, s, pts = D["ent_r"][r, t], D["sai_r"][r, t], D["pts_r"][r, t]
                if e < 0:
                    t += VALIDADE + 1
                    continue
                out.append(dict(dia=D["dia"], regra=r, t=t, ent=int(e), sai=int(s), pts=pts, hora=D["hora"][t]))
                ultima, T, operou = r, s + 1, True
                break
            t += 1
        if not operou:
            ultima, T = r, fim_janela
    return out


ESTILO = "normal"


def roda(dias, cfg, modo="melhor", rng=None):
    nL, nW, var, mn = cfg
    tr = []
    for D in dias:
        tr += roda_dia(D, nL, nW, var, mn, modo, rng, ESTILO)
    return pd.DataFrame(tr, columns=["dia", "regra", "t", "ent", "sai", "pts", "hora"])


def nome_regra(r):
    g, e = divmod(r, len(SAIDAS))
    gi, resto = divmod(g, 2 * len(CONFIRMA))
    di, ci = divmod(resto, len(CONFIRMA))
    tipo, k, m = SAIDAS[e]
    sai = f"S{k}A{m}" if tipo == "fixa" else f"{tipo}{k}"
    return f"{GATILHOS[gi]}/{'seg' if di == 0 else 'contra'}/{CONFIRMA[ci]}/{sai}"


def rotulo(cfg):
    nL, nW, var, mn = cfg
    return f"L{nL * 5}W{nW * 5}{var}m{mn}"


def linha_padrao(variante, tr, dias, extras):
    pnl = tr.pts.to_numpy() * PT_BRL if len(tr) else np.zeros(0)
    eq = pd.Series(CAPITAL + np.cumsum(pnl)) if len(pnl) else pd.Series([CAPITAL])
    liq = float(pnl.sum())
    dd = maxdd_brl(pd.concat([pd.Series([CAPITAL]), eq]))
    pico = np.maximum.accumulate(np.r_[CAPITAL, eq.to_numpy()])
    ddpct = float(((pico - np.r_[CAPITAL, eq.to_numpy()]) / pico).max())
    aviso = "fila 1 tick" + (" CAIXA<MARGEM" if eq.min() < MARGEM else "")
    return LinhaResultado(variante=variante, liquido_brl=liq, maxdd_brl=dd,
                          win_rate_pct=100.0 * (pnl > 0).mean() if len(pnl) else 0.0, trades=len(pnl),
                          pregoes=len(dias), retorno_pct=100 * liq / CAPITAL, maxdd_pct=100 * ddpct,
                          capital_final=CAPITAL + liq, extras=extras, aviso=aviso)


# ---------------------------------------------------------------- paralelo
_CONJ = {}


def _init(conj, estilo):
    global _CONJ, ESTILO
    _CONJ, ESTILO = conj, estilo


def unidade(cfg):
    buf = StringIO()
    res = {}
    with redirect_stdout(buf):
        for nome, dias in _CONJ.items():
            tr = roda(dias, cfg)
            rng = np.random.default_rng(SEMENTE + zlib.crc32((rotulo(cfg) + nome).encode()))
            nulo = np.array([roda(dias, cfg, "acaso_positivas", rng).pts.sum() for _ in range(N_NULO)])
            nulo_t = np.array([roda(dias, cfg, "acaso_todas", rng).pts.sum() for _ in range(N_NULO // 4)])
            p = (1 + (nulo >= tr.pts.sum()).sum()) / (1 + len(nulo))
            res[nome] = dict(tr=tr, nulo=nulo, nulo_t=nulo_t, p=p)
    return cfg, res, buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fase", type=int, default=1)
    ap.add_argument("--configs", default="")
    ap.add_argument("--estilo", default="normal", choices=["normal", "inverso", "pior"])
    args = ap.parse_args()

    b = carrega()
    todos = sorted(b.dia.unique())
    rng = np.random.default_rng(SEMENTE)
    i0 = int(rng.integers(0, len(todos) - 9))
    seguidos = todos[i0:i0 + 10]
    resto = [d for d in todos if d not in seguidos]
    aleat = sorted(rng.choice(resto, 10, replace=False))
    resto2 = [d for d in resto if d not in aleat]
    fase2 = sorted(rng.choice(resto2, 10, replace=False))
    fmt = lambda ds: " ".join(pd.Timestamp(d).strftime("%d/%m") for d in ds)
    print(f"{len(todos)} pregões em {INI}..2026-10-14 (09/10 fora)", flush=True)
    print(f"seguidos:   {fmt(seguidos)}\naleatórios: {fmt(aleat)}\nfase 2:     {fmt(fase2)}", flush=True)
    print(f"estilo: {args.estilo}", flush=True)
    print(f"biblioteca: {N_REGRAS} regras ({N_SINAIS} sinais x {len(SAIDAS)} saídas)", flush=True)

    usar = {"seguidos": seguidos, "aleatorios": aleat} if args.fase == 1 else {"fase2": fase2}
    conj = {k: [prepara_dia(b, d) for d in v] for k, v in usar.items()}
    print("tabelas de trade prontas", flush=True)

    if args.configs:
        cfgs = []
        for c in args.configs.split(","):
            L, rest = c[1:].split("W")
            W, rest2 = rest[:-3], rest[-3:]
            cfgs.append((int(L) // 5, int(W) // 5, rest2[0], int(rest2[2])))
    else:
        cfgs = [(L // 5, W // 5, v, mn) for L in (30, 60, 90, 120) for W in (30, 60, 90) for v in "AB" for mn in (1, 2)]

    resultados = {}
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1), initializer=_init, initargs=(conj, args.estilo)) as ex:
        futs = [ex.submit(unidade, c) for c in cfgs]
        for f in as_completed(futs):
            cfg, res, _ = f.result()
            resultados[cfg] = res
            partes = [f"{k}: {num_br(r['tr'].pts.sum() * PT_BRL, 0)} R$ ({len(r['tr'])} tr, p={num_br(r['p'], 3)})"
                      for k, r in res.items()]
            print(f"{rotulo(cfg):14s} " + " | ".join(partes), flush=True)

    extras = ("nulo med R$", "nulo p90 R$", "acaso tot R$", "p nulo", "dias +")
    for nome, dias in usar.items():
        linhas = []
        for cfg in cfgs:
            r = resultados[cfg][nome]
            tr = r["tr"]
            dpos = (tr.groupby("dia").pts.sum() > 0).sum() if len(tr) else 0
            linhas.append(linha_padrao(rotulo(cfg), tr, dias, {
                "nulo med R$": num_br(np.median(r["nulo"]) * PT_BRL, 0),
                "nulo p90 R$": num_br(np.quantile(r["nulo"], 0.9) * PT_BRL, 0),
                "acaso tot R$": num_br(np.median(r["nulo_t"]) * PT_BRL, 0),
                "p nulo": num_br(r["p"], 3), "dias +": f"{dpos}/{len(dias)}"}))
        print(f"\n=== {nome} ({len(dias)} pregões, 1 contrato, capital R${num_br(CAPITAL, 0)}) ===")
        print(tabela(linhas, extras, 13), flush=True)

    # BH sobre o p combinado (máximo dos conjuntos) — só fase 1
    if args.fase == 1:
        ps = np.array([max(resultados[c][k]["p"] for k in usar) for c in cfgs])
        liq_ok = np.array([all(resultados[c][k]["tr"].pts.sum() > 0 for k in usar) for c in cfgs])
        ordem = np.argsort(ps)
        m = len(ps)
        corte = 0
        for i, j in enumerate(ordem, 1):
            if ps[j] <= 0.10 * i / m:
                corte = i
        passa = {cfgs[j] for j in ordem[:corte]}
        print("\nBH q=0,10 (p = pior dos dois conjuntos):")
        for j in ordem[:8]:
            c = cfgs[j]
            print(f"  {rotulo(c):14s} p={num_br(ps[j], 3)} líquido>0 nos dois={liq_ok[j]} "
                  f"{'PASSA' if c in passa and liq_ok[j] else ''}", flush=True)
        lit = (6, 6, "A", 1)
        print(f"literal L30W30Am1: p seg={num_br(resultados[lit]['seguidos']['p'], 3)} "
              f"p ale={num_br(resultados[lit]['aleatorios']['p'], 3)}")

    # regras mais escolhidas na literal / melhor
    for cfg in cfgs[:1] if args.fase == 2 else [(6, 6, "A", 1)]:
        for nome in usar:
            tr = resultados[cfg][nome]["tr"]
            if len(tr):
                tr = tr.assign(nome=tr.regra.map(nome_regra))
                top = tr.groupby("nome").pts.agg(["count", "sum"]).sort_values("count", ascending=False).head(6)
                print(f"\nregras mais usadas {rotulo(cfg)} {nome}:\n{(top * [1, PT_BRL]).round(1).to_string()}")
                dia = tr.groupby("dia").pts.sum() * PT_BRL
                print("por dia R$: " + " ".join(f"{d[5:]}:{v:+.0f}" for d, v in dia.items()))


if __name__ == "__main__":
    main()
