"""copa_win: a posicao do fechamento na barra (CLV) ACRESCENTA algo ao
baseline trivial, ou so' repete "ja estou ganhando"?

A ponta solta da linha de trajetoria. O CLV medio desde a entrada separa
vencedor de perdedor nas DUAS janelas (AUC 0,605 IS / 0,689 OOS aos 10 min,
p<0,001 nas duas) -- e' a unica variavel do banco estruturalmente desacoplada
do deslocamento: mede onde o preco FECHOU dentro do range do minuto, nao o
quanto ele andou.

Mas AUC absoluto nao responde nada. O banco de perguntas foi explicito: **o
competidor nao e' a moeda, e' o baseline trivial** -- "quanto estou ganhando
agora" (`pos`) e "quanto falta para o pregao fechar" (`T_rest`). Quase toda
variavel de trajetoria e' proxy disso. A pergunta unica deste script e':

    AUC(baseline + CLV) - AUC(baseline), fora da amostra.

Se o incremento for ~0, o CLV e' redundante e a linha de trajetoria fecha com
resultado negativo limpo. Se for material, existe informacao nova.

## Desenho

- Coorte: trades ainda ABERTOS em tau (nao condicionada ao desfecho, que
  seria olhar o futuro). tau in {10, 20} min.
- Desfecho: o trade termina com pnl > 0.
- Baseline: `pos` (posicao do fechamento na escala -1 stop / 0 entrada / +1
  alvo, em tau) + `t_rest` (minutos de tau ate o corte de achatamento).
- Teste: baseline + `clv_medio` (media do CLV das barras ate tau, ja
  ajustado pelo lado).
- Ajuste no IS, leitura no OOS. Nenhum parametro escolhido olhando o OOS.
- Significancia do incremento por PERMUTACAO do proprio CLV dentro do OOS
  (embaralha so' a coluna do CLV, preserva baseline e desfecho): se o
  incremento observado cair dentro da distribuicao gerada assim, ele e'
  ruido.

Sem scipy/sklearn (convencao do repo): logistica por Newton/IRLS, AUC pela
estatistica U.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = ROOT / "scratch"
CORTE_OOS = pd.Timestamp("2026-06-13")
FLATTEN_UTC = pd.Timestamp("21:20:00").time()   # corte de achatamento do WIN@ (producao)
N_PERM = 20000


def br(x, c=3):
    if pd.isna(x):
        return "-"
    return f"{x:,.{c}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def auc(y, s):
    y, s = np.asarray(y, bool), np.asarray(s, float)
    if y.sum() == 0 or (~y).sum() == 0:
        return np.nan
    r = pd.Series(np.concatenate([s[y], s[~y]])).rank().to_numpy()
    u = r[:y.sum()].sum() - y.sum() * (y.sum() + 1) / 2
    return u / (y.sum() * (~y).sum())


def logistica(X, y, iters=80, ridge=1e-6):
    X = np.column_stack([np.ones(len(X)), X])
    b = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(X @ b, -30, 30)))
        W = np.clip(p * (1 - p), 1e-9, None)
        H = X.T @ (X * W[:, None]) + ridge * np.eye(X.shape[1])
        passo = np.linalg.solve(H, X.T @ (y - p) - ridge * b)
        b = b + passo
        if np.max(np.abs(passo)) < 1e-10:
            break
    return b


def prever(X, b):
    X = np.column_stack([np.ones(len(X)), X])
    return 1 / (1 + np.exp(-np.clip(X @ b, -30, 30)))


def monta(tau):
    tr = pd.read_csv(SCRATCH / "copawin_trajetoria_trades_producao_2026_09_15.csv")
    ba = pd.read_csv(SCRATCH / "copawin_trajetoria_barras_producao_2026_09_15.csv")
    ba = ba.sort_values(["trade_id", "bar_idx"]).copy()
    rng = (ba["high"] - ba["low"]).replace(0, np.nan)
    lado = np.where(ba["lado"] == "long", 1.0, -1.0)
    ba["clv"] = (((ba["close"] - ba["low"]) - (ba["high"] - ba["close"])) / rng) * lado

    dur = ba.groupby("trade_id")["minutos_desde_entrada"].max()
    vivos = dur[dur > tau].index
    sub = ba[(ba["minutos_desde_entrada"] <= tau) & (ba["trade_id"].isin(vivos))]
    f = sub.groupby("trade_id").agg(
        clv_medio=("clv", "mean"),
        pos=("pos_fechamento_norm", "last"),
        ts_tau=("ts", "last"))
    f = f.join(tr.set_index("trade_id")[["pnl_brl", "data"]])
    f["venceu"] = f["pnl_brl"] > 0
    f["data"] = pd.to_datetime(f["data"])
    ts = pd.to_datetime(f["ts_tau"], utc=True)
    fim = ts.dt.normalize() + pd.Timedelta(hours=FLATTEN_UTC.hour, minutes=FLATTEN_UTC.minute)
    f["t_rest"] = (fim - ts).dt.total_seconds() / 60.0
    return f.dropna(subset=["clv_medio", "pos", "t_rest"])


def main():
    print("=" * 104)
    print("copa_win -- o CLV ACRESCENTA ao baseline trivial (posicao + tempo restante)?")
    print("=" * 104)
    rng = np.random.default_rng(20260915)
    for tau in (10, 20):
        f = monta(tau)
        ist, oos = f[f["data"] < CORTE_OOS], f[f["data"] >= CORTE_OOS]
        print(f"\n--- tau = {tau} min | coorte aberta {len(f)} "
              f"(IS {len(ist)} / OOS {len(oos)}) | vencedores {int(f['venceu'].sum())} ---")
        mu, sd = ist[["pos", "t_rest", "clv_medio"]].mean(), ist[["pos", "t_rest", "clv_medio"]].std(ddof=0)
        Zi = (ist[["pos", "t_rest", "clv_medio"]] - mu) / sd
        Zo = (oos[["pos", "t_rest", "clv_medio"]] - mu) / sd
        yi, yo = ist["venceu"].to_numpy(float), oos["venceu"].to_numpy(bool)

        base_cols, teste_cols = ["pos", "t_rest"], ["pos", "t_rest", "clv_medio"]
        bb = logistica(Zi[base_cols].to_numpy(), yi)
        bt = logistica(Zi[teste_cols].to_numpy(), yi)
        a_base_is = auc(ist["venceu"].to_numpy(bool), prever(Zi[base_cols].to_numpy(), bb))
        a_test_is = auc(ist["venceu"].to_numpy(bool), prever(Zi[teste_cols].to_numpy(), bt))
        s_base = prever(Zo[base_cols].to_numpy(), bb)
        s_test = prever(Zo[teste_cols].to_numpy(), bt)
        a_base, a_test = auc(yo, s_base), auc(yo, s_test)

        print(f"  {'modelo':<26}{'AUC IS':>10}{'AUC OOS':>11}")
        print(f"  {'baseline (pos + t_rest)':<26}{br(a_base_is):>10}{br(a_base):>11}")
        print(f"  {'baseline + CLV':<26}{br(a_test_is):>10}{br(a_test):>11}")
        print(f"  {'INCREMENTO no OOS':<26}{'':>10}{br(a_test - a_base):>11}")
        print(f"  (CLV sozinho, sem baseline, no OOS: {br(auc(yo, Zo['clv_medio'].to_numpy()))})")

        # permutacao: embaralha SO' o CLV, refaz ajuste e leitura
        obs = a_test - a_base
        nulo = np.empty(N_PERM)
        Zi_np, Zo_np = Zi[teste_cols].to_numpy(), Zo[teste_cols].to_numpy()
        for i in range(N_PERM):
            Zi_p, Zo_p = Zi_np.copy(), Zo_np.copy()
            Zi_p[:, 2] = rng.permutation(Zi_p[:, 2])
            Zo_p[:, 2] = rng.permutation(Zo_p[:, 2])
            b = logistica(Zi_p, yi, iters=25)
            nulo[i] = auc(yo, prever(Zo_p, b)) - a_base
        p = (np.sum(nulo >= obs) + 1) / (N_PERM + 1)
        print(f"  nulo por permutacao do CLV: media {br(nulo.mean())} dp {br(nulo.std())} "
              f"IC95% [{br(np.quantile(nulo, .025))} ; {br(np.quantile(nulo, .975))}]")
        print(f"  p (unicaudal) do incremento: {br(p, 4)}"
              f"{'   <<< fora do nulo' if p < 0.05 else '   -> dentro do ruido'}")
    print("\nFIM.")


if __name__ == "__main__":
    main()
