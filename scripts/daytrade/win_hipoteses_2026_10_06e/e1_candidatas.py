"""Features e1 (volume de alta x baixa; recuo x impulso) + candidatas congeladas.
Todas usam so' velas FECHADAS ate' a barra do sinal t (inclusive). Funcionam com ano=2025 (nao rodado).
base: 'v' (volume), 'rng' (h-l) ou 'corpo' (|c-o|) -- os dois ultimos sao o controle de preco."""
import numpy as np
import pandas as pd


def _base(d, base):
    if base == "v":
        return d["v"].astype(float)
    if base == "rng":
        return (d["h"] - d["l"]).astype(float)
    return (d["c"] - d["o"]).abs().astype(float)


def feat_alta_baixa(d, N, L, pond=False, base="v"):
    w = _base(d, base)
    s = np.sign(d["c"] - d["o"])
    if pond:
        rng = (d["h"] - d["l"]).replace(0, np.nan)
        w = w * (d["c"] - d["o"]).abs() / rng
    va = (w * (s > 0)).rolling(N).sum()
    vb = (w * (s < 0)).rolling(N).sum()
    r = (va / (va + vb)).values
    with np.errstate(invalid="ignore"):
        return r >= L, r <= 1 - L          # NaN -> False


def feat_recuo(d, N, L, modo="baixo", base="v"):
    """razao = media(w das velas CONTRA o sinal) / media(w das velas A FAVOR), ultimas N velas ate' t.
    modo 'baixo': entra se razao < L (sem recuo conta como ok; sem vela a favor falha).
    modo 'alto' : entra se razao >= L (sem recuo falha)."""
    w = _base(d, base).values
    s = np.sign((d["c"] - d["o"]).values)
    out = []
    for lado in (1, -1):
        fav = pd.Series(np.where(s == lado, w, 0.0)); nf = pd.Series((s == lado).astype(float))
        con = pd.Series(np.where(s == -lado, w, 0.0)); nc = pd.Series((s == -lado).astype(float))
        sf, nf_ = fav.rolling(N).sum().values, nf.rolling(N).sum().values
        sc, nc_ = con.rolling(N).sum().values, nc.rolling(N).sum().values
        with np.errstate(invalid="ignore", divide="ignore"):
            mf = sf / nf_; mc = sc / nc_
            r = mc / mf
        if modo == "baixo":
            ok = ((nc_ == 0) & (nf_ > 0)) | ((nc_ > 0) & (nf_ > 0) & (r < L))
        else:
            ok = (nc_ > 0) & (nf_ > 0) & (r >= L)
        out.append(np.asarray(ok, bool))
    return out[0], out[1]


# ---- candidatas congeladas (preenchidas apos a rodada) ----
CANDIDATAS = {}
