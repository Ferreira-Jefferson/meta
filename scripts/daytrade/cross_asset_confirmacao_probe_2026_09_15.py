"""Sonda (estagio 1) da hipotese de CONFIRMACAO CRUZADA WIN@ x WDO@.

Pergunta do dono (2026-09-15): mesmo os dois andando no MESMO minuto, quando
os dois JA estao se movendo em confirmacao mutua (um sobe, o outro desce, de
forma sustentada), da' pra pegar UM PEDACO do movimento seguinte com UMA PERNA
so'?

Isto NAO e' o que ja foi medido:
  - `copa_cross_asset_refuted_2026_08_26` mediu corr(WIN_t, WDO_t+k) --
    incremento contra incremento, defasagem k. Deu |r|<0,04 pra todo k!=0.
    Correlacao linear global perto de zero e' compativel com efeito
    CONDICIONAL a um estado: a media global dilui o estado.
  - `win_wdo_spread_relativo_2026_08_27` mediu REVERSAO da diferenca, com
    posicao nas DUAS pernas (piso de custo R$13-15,50/round-trip). Aqui e'
    CONTINUACAO na direcao, UMA perna (piso R$0,50).

Desenho (convencao "o minimo que refuta primeiro" -- feedback_teste_pequeno_
valida_hipotese): estagio 1 e' estatistica pura, sem motor e sem execucao. So'
se sobreviver ao nulo com Bonferroni vale montar IntradayStrategy e rodar com
fidelidade de fila + desenho de execucao fechado.

NULO: repareamento de dia. O dia do instrumento CONFIRMADOR e' embaralhado
contra o dia do instrumento OPERADO. Isso preserva a autocorrelacao e a
estrutura intradiaria de cada serie e destroi SO' a relacao cruzada -- ou seja,
mede exatamente "a confirmacao do outro adiciona alguma coisa alem do proprio
momentum?". O controle `so_proprio` (condicionar so' na perna operada) esta'
reportado lado a lado pelo mesmo motivo.

Sem look-ahead: os limiares de "movimento forte" sao quantis calculados SO' no
IS (< 2026-06-13) e reaplicados sem recalibrar no OOS.
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
#: resultado vai para scratch/, NUNCA para o diretorio de codigo -- CSV
#: solto em scripts/ vira arquivo novo no `git status` e acaba commitado.
SAIDA = RAIZ / "scratch" / "cross_asset_confirmacao_probe_2026_09_15.csv"

CORTE_IS = pd.Timestamp("2026-06-13", tz="America/Sao_Paulo")

JANELAS_N = [1, 3, 5, 15]        # minutos de confirmacao (olhando pra tras)
QUANTIS = [0.60, 0.75, 0.90]     # forca minima do movimento, quantil de |delta|
HORIZONTES_H = [5, 15, 30]       # minutos a frente (a resposta)
POLARIDADES = ["oposto", "mesmo"]
PERNAS = ["WDO", "WIN"]

N_PERM = 6000
SEED = 20260915

# familia de testes = 4 x 3 x 3 x 2 x 2, VEZES 2 (continuacao e reversao)
N_TESTES = (len(JANELAS_N) * len(QUANTIS) * len(HORIZONTES_H)
            * len(POLARIDADES) * len(PERNAS) * 2)
ALPHA_BONF = 0.05 / N_TESTES

VALOR_PONTO = {"WDO": 10.0, "WIN": 0.20}   # R$ por ponto, 1 contrato
TICK_PONTOS = {"WDO": 0.5, "WIN": 5.0}
CUSTO_RT = 0.50                             # R$/contrato/round-trip, 1 perna


# ----------------------------------------------------------------- base -----
def carregar_matrizes():
    w = pd.read_parquet("data/raw_intraday/WIN_A_.parquet")[["close"]].rename(
        columns={"close": "win"})
    d = pd.read_parquet("data/raw_intraday/WDO_A_.parquet")[["close"]].rename(
        columns={"close": "wdo"})
    w.index = w.index.tz_convert("America/Sao_Paulo")
    d.index = d.index.tz_convert("America/Sao_Paulo")
    j = w.join(d, how="inner").dropna().sort_index()
    j["dia"] = j.index.normalize()

    dias = pd.DatetimeIndex(sorted(j["dia"].unique()))
    max_bars = int(j.groupby("dia").size().max())
    W = np.full((len(dias), max_bars), np.nan)
    D = np.full((len(dias), max_bars), np.nan)
    for i, dia in enumerate(dias):
        sub = j[j["dia"] == dia]
        W[i, : len(sub)] = sub["win"].to_numpy()
        D[i, : len(sub)] = sub["wdo"].to_numpy()
    is_mask = np.asarray(dias < CORTE_IS)
    return W, D, dias, is_mask


def delta_tras(M: np.ndarray, n: int) -> np.ndarray:
    """Variacao em PONTOS dos ultimos `n` minutos, dentro do proprio dia."""
    out = np.full_like(M, np.nan)
    out[:, n:] = M[:, n:] - M[:, :-n]
    return out


def delta_frente(M: np.ndarray, h: int) -> np.ndarray:
    """Variacao em PONTOS dos proximos `h` minutos, dentro do proprio dia."""
    out = np.full_like(M, np.nan)
    out[:, :-h] = M[:, h:] - M[:, :-h]
    return out


# ------------------------------------------------------------ estatistica ---
def stat(sinal_op: np.ndarray, sinal_conf: np.ndarray, fwd_op: np.ndarray,
         thr_op: float, thr_conf: float, polaridade: str,
         linhas: np.ndarray) -> tuple[float, int, float]:
    """Media de R$ por operacao (em PONTOS assinados), n e taxa de acerto.

    A aposta e' CONTINUACAO da perna operada: se ela vem subindo forte e a
    outra confirma, compra; se vem caindo forte e a outra confirma, vende.
    `polaridade` diz o que conta como confirmacao -- 'oposto' (o normal, dado
    que r<0) ou 'mesmo' (controle).
    """
    so = sinal_op[linhas]
    sc = sinal_conf[linhas]
    fw = fwd_op[linhas]

    forte_op = np.abs(so) >= thr_op
    forte_cf = np.abs(sc) >= thr_conf
    if polaridade == "oposto":
        confirma = np.sign(so) * np.sign(sc) < 0
    else:
        confirma = np.sign(so) * np.sign(sc) > 0

    sel = forte_op & forte_cf & confirma & np.isfinite(fw)
    n = int(sel.sum())
    if n == 0:
        return float("nan"), 0, float("nan")
    assinado = np.sign(so[sel]) * fw[sel]     # pontos a favor da aposta
    return float(np.mean(assinado)), n, float(np.mean(assinado > 0))


def stat_so_proprio(sinal_op, fwd_op, thr_op, linhas):
    """Controle: condiciona SO' no momentum da propria perna."""
    so = sinal_op[linhas]
    fw = fwd_op[linhas]
    sel = (np.abs(so) >= thr_op) & np.isfinite(fw)
    n = int(sel.sum())
    if n == 0:
        return float("nan"), 0, float("nan")
    assinado = np.sign(so[sel]) * fw[sel]
    return float(np.mean(assinado)), n, float(np.mean(assinado > 0))


def rodar_celula(args):
    (perna, n_jan, q, h, polaridade, W, D, is_mask) = args
    # semente deterministica (nada de hash() de string -- e' randomizado por processo)
    semente = (SEED + PERNAS.index(perna) * 10_000 + n_jan * 1_000
               + QUANTIS.index(q) * 100 + h + POLARIDADES.index(polaridade) * 7)
    rng = np.random.default_rng(semente)

    M_op, M_cf = (D, W) if perna == "WDO" else (W, D)
    sinal_op = delta_tras(M_op, n_jan)
    sinal_cf = delta_tras(M_cf, n_jan)
    fwd_op = delta_frente(M_op, h)

    idx_is = np.where(is_mask)[0]
    idx_oos = np.where(~is_mask)[0]

    # limiares: quantis calculados SO' no IS, reaplicados no OOS sem recalibrar
    thr_op = float(np.nanquantile(np.abs(sinal_op[idx_is]), q))
    thr_cf = float(np.nanquantile(np.abs(sinal_cf[idx_is]), q))

    vp = VALOR_PONTO[perna]
    res = {"perna": perna, "N": n_jan, "q": q, "H": h, "pol": polaridade,
           "thr_op_pts": thr_op, "thr_conf_pts": thr_cf}

    for rotulo, linhas in (("is", idx_is), ("oos", idx_oos)):
        m, n, acerto = stat(sinal_op, sinal_cf, fwd_op, thr_op, thr_cf, polaridade, linhas)
        mp, npp, ap = stat_so_proprio(sinal_op, fwd_op, thr_op, linhas)
        res[f"{rotulo}_rs"] = m * vp
        res[f"{rotulo}_n"] = n
        res[f"{rotulo}_acerto"] = acerto
        res[f"{rotulo}_proprio_rs"] = mp * vp
        res[f"{rotulo}_proprio_n"] = npp
        res[f"{rotulo}_proprio_acerto"] = ap

        # nulo: embaralha os DIAS do confirmador contra os do operado
        if n > 0 and np.isfinite(m):
            nulos = np.empty(N_PERM)
            for p in range(N_PERM):
                ordem = rng.permutation(linhas)
                sc_perm = sinal_cf[ordem]
                so = sinal_op[linhas]
                fw = fwd_op[linhas]
                forte = (np.abs(so) >= thr_op) & (np.abs(sc_perm) >= thr_cf)
                if polaridade == "oposto":
                    conf = np.sign(so) * np.sign(sc_perm) < 0
                else:
                    conf = np.sign(so) * np.sign(sc_perm) > 0
                sel = forte & conf & np.isfinite(fw)
                nulos[p] = np.mean(np.sign(so[sel]) * fw[sel]) if sel.any() else np.nan
            nulos = nulos[np.isfinite(nulos)]
            # unilateral: o real e' MAIOR que o nulo? (aposta e' ganhar dinheiro)
            # DUAS caudas na mesma permutacao: a aposta pode ser CONTINUACAO
            # (real acima do nulo) ou REVERSAO (real abaixo). Medir so' uma
            # deixa a sonda cega pra metade da resposta -- a familia de testes
            # ja' esta' contada com as duas (N_TESTES x 2).
            res[f"{rotulo}_p"] = float((np.sum(nulos >= m) + 1) / (len(nulos) + 1))
            res[f"{rotulo}_p_rev"] = float((np.sum(nulos <= m) + 1) / (len(nulos) + 1))
            res[f"{rotulo}_pctil"] = float(np.mean(nulos < m))
            res[f"{rotulo}_nulo_medio_rs"] = float(np.mean(nulos)) * vp
        else:
            res[f"{rotulo}_p"] = float("nan")
            res[f"{rotulo}_p_rev"] = float("nan")
            res[f"{rotulo}_pctil"] = float("nan")
            res[f"{rotulo}_nulo_medio_rs"] = float("nan")

    return res


def main():
    print(f"[base] carregando WIN@ x WDO@ M1 casados...", flush=True)
    W, D, dias, is_mask = carregar_matrizes()
    print(f"[base] {len(dias)} pregoes ({is_mask.sum()} IS / {(~is_mask).sum()} OOS), "
          f"{W.shape[1]} barras max/dia", flush=True)
    print(f"[familia] {N_TESTES} testes -> alpha Bonferroni = {ALPHA_BONF:.2e} "
          f"({N_PERM} permutacoes, p minimo {1/(N_PERM+1):.2e})", flush=True)
    print(f"[custo] piso de 1 perna = R${CUSTO_RT:.2f}/round-trip\n", flush=True)

    tarefas = [(perna, n, q, h, pol, W, D, is_mask)
               for perna in PERNAS for n in JANELAS_N for q in QUANTIS
               for h in HORIZONTES_H for pol in POLARIDADES]

    linhas = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(rodar_celula, t): t for t in tarefas}
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            linhas.append(r)
            marca = "  <<<" if (r["is_p"] < ALPHA_BONF and r["is_rs"] > CUSTO_RT) else ""
            print(f"[{i:>3}/{len(tarefas)}] {r['perna']} N={r['N']:>2} q={r['q']:.2f} "
                  f"H={r['H']:>2} {r['pol']:>6} | IS R${r['is_rs']:+7.2f} "
                  f"(proprio R${r['is_proprio_rs']:+7.2f}) acerto {r['is_acerto']:.1%} "
                  f"n={r['is_n']:>6} p={r['is_p']:.4f}{marca}", flush=True)

    df = pd.DataFrame(linhas).sort_values("is_rs", ascending=False)
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(SAIDA, index=False)

    print("\n" + "=" * 100)
    print(f"TOP 10 POR IS -- CONTINUACAO (de {len(df)} celulas)")
    print("=" * 100)
    cols = ["perna", "N", "q", "H", "pol", "is_rs", "is_proprio_rs", "is_acerto",
            "is_n", "is_p", "is_p_rev", "oos_rs", "oos_acerto", "oos_n", "oos_p"]
    print(df[cols].head(10).to_string(index=False,
          float_format=lambda v: f"{v:.4f}"))

    df["is_rs_rev"] = -df["is_rs"]
    df["oos_rs_rev"] = -df["oos_rs"]
    cont = df[(df["is_p"] < ALPHA_BONF) & (df["is_rs"] > CUSTO_RT)].copy()
    cont["direcao"] = "continuacao"
    rev = df[(df["is_p_rev"] < ALPHA_BONF) & (df["is_rs_rev"] > CUSTO_RT)].copy()
    rev["direcao"] = "reversao"
    sobrev = pd.concat([cont, rev])

    print("\n" + "=" * 100)
    print("TOP 10 POR IS -- REVERSAO (a mesma condicao, aposta invertida)")
    print("=" * 100)
    inv = df.sort_values("is_rs_rev", ascending=False).head(10)
    print(inv[["perna", "N", "q", "H", "pol", "is_rs_rev", "is_acerto", "is_n",
               "is_p_rev", "oos_rs_rev", "oos_n"]].to_string(
        index=False, float_format=lambda v: f"{v:.4f}"))

    print("\n" + "=" * 100)
    print(f"SOBREVIVENTES DO IS (p < {ALPHA_BONF:.2e} E bruto > R${CUSTO_RT:.2f}, "
          f"as duas direcoes): {len(sobrev)} de {2 * len(df)} testes")
    print("=" * 100)
    if len(sobrev):
        print(sobrev[["direcao"] + cols].to_string(index=False,
              float_format=lambda v: f"{v:.4f}"))
        oos_bruto = np.where(sobrev["direcao"] == "reversao",
                             sobrev["oos_rs_rev"], sobrev["oos_rs"])
        oos_p = np.where(sobrev["direcao"] == "reversao",
                         sobrev["oos_p_rev"], sobrev["oos_p"])
        conf = sobrev[(oos_bruto > CUSTO_RT) & (oos_p < 0.05)]
        print(f"\n  ... e que TAMBEM passam no OOS (bruto > custo e p<0,05): {len(conf)}")
        if len(conf):
            print(conf[["direcao"] + cols].to_string(index=False,
                  float_format=lambda v: f"{v:.4f}"))
    else:
        print("  nenhuma.")

    print("\n[csv] scripts/daytrade/cross_asset_confirmacao_probe_2026_09_15.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
