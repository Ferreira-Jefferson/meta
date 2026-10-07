"""Z9 -- base comum dos testes de convivencia em conta NETTING (todos os robos no mesmo WIN, 1 posicao liquida).

Carrega as operacoes ISOLADAS de cada robo (replay de cada EA sozinho, versao padrao atual) de 2022 a 2026, com a
regra do gap (G1, k=1,0) aplicada nos 4 EAs que a tem (o WinGapBarra1 nao tem: e' um robo de gap). Cada operacao
isolada e' tratada como o "sinal" do robo: ele QUER estar posicionado em `lado` de `entrada` ate' `saida`.
Aproximacao (documentar em todo resultado): o robo bloqueado/interrompido nao muda as operacoes seguintes dele.

API:
  operacoes(ano) -> DataFrame (estrategia, entrada, saida, lado, preco_entrada, preco_saida, rs) ordenado por entrada
  preco(ts)      -> last do ultimo tick com tempo <= ts (ordem a mercado, regra do Testador; ticks reais a partir de
                    2026-02-20, antes 4 ticks sinteticos por M1 -- ver dados.py)
  resumo(df_ops, custo=2.0) -> dict por ano: liquido c/ custo, ops, acerto, maior queda (saldo de R$1.000), quebra
Uso direto: python base.py  -> confere os totais isolados por robo e ano.
"""
import sys
from datetime import date
from functools import lru_cache
from pathlib import Path
import numpy as np, pandas as pd

Z9 = Path(__file__).resolve().parent
AQ = Z9.parents[1]
sys.path.insert(0, str(AQ))
import dados, filtro_gap  # noqa: E402

C = AQ / "combinacoes"
ROBOS = ["WinGapBarra1", "WinCincoMedias", "WinDeslocamentoMatinal", "WinRetanguloEma34", "Win_c1"]
FONTES_2225 = {"WinCincoMedias": C / "y_tempos/cinco/trades/cinco_M120_2022_2025.csv",
               "WinDeslocamentoMatinal": C / "x_fixas/x0b/resultados_2022_2025/WinDeslocamentoMatinal.csv",
               "Win_c1": C / "y_tempos/win/trades/Win_c1_M60_2225.csv",
               "WinRetanguloEma34": C / "z5_f3_varredura/trades/k0.5_2022_2025.csv",
               "WinGapBarra1": AQ / "resultados_anos_gap_barra1/WinGapBarra1_2022_2025.csv"}
COM_GAP = {"WinCincoMedias", "WinDeslocamentoMatinal", "Win_c1", "WinRetanguloEma34"}
CAPITAL, CUSTO = 1000.0, 2.0


@lru_cache(maxsize=1)
def _todas() -> pd.DataFrame:
    bl = filtro_gap.bloqueados_padrao()
    ps = []
    for r in ROBOS:
        for f in (FONTES_2225[r], AQ / "resultados" / f"{r}.csv"):
            t = pd.read_csv(f)
            t["estrategia"] = r
            ps.append(t)
    t = pd.concat(ps, ignore_index=True)
    t["entrada"] = pd.to_datetime(t.entrada.astype(str), format="ISO8601")
    t["saida"] = pd.to_datetime(t.saida.astype(str), format="ISO8601")
    gap = t.estrategia.isin(COM_GAP) & t.entrada.dt.date.isin(bl)
    t = t[~gap & (t.entrada.dt.date <= date(2026, 10, 5))]
    t["ano"] = t.entrada.dt.year
    t["prio"] = t.estrategia.map({r: i for i, r in enumerate(ROBOS)})
    return t.sort_values(["entrada", "prio"]).reset_index(drop=True)[
        ["ano", "estrategia", "entrada", "saida", "lado", "preco_entrada", "preco_saida", "rs", "motivo"]]


def operacoes(ano: int) -> pd.DataFrame:
    t = _todas()
    return t[t.ano == ano].reset_index(drop=True)


@lru_cache(maxsize=1)
def _m1_2225() -> pd.DataFrame:
    return pd.read_parquet(dados.DADOS / "m1_WIN$N_2022_2025.parquet")


@lru_cache(maxsize=400)
def _ticks(dia: date):
    if dia.year >= 2026:
        t, p, _, _ = dados.ticks(dia)
        return t, p
    b = _m1_2225()
    t, p, _ = dados._sinteticos(b[b.index.date == dia])
    return t, p


def preco(ts) -> float:
    ts = pd.Timestamp(ts)
    t, p = _ticks(ts.date())
    i = np.searchsorted(t, dados.ms(ts), side="right") - 1
    return float(p[max(i, 0)])


def resumo(ops: pd.DataFrame, custo: float = CUSTO) -> dict:
    """ops: colunas ano, saida, rs (R$ bruto por operacao, 1 contrato; use qtd se houver). Cada ano recomeca em R$1.000."""
    out = {}
    for ano, g in ops.sort_values("saida").groupby("ano"):
        q = g["qtd"] if "qtd" in g else 1.0
        v = (g.rs - custo * q).to_numpy()
        s = CAPITAL + np.cumsum(v)
        dd = float((np.maximum.accumulate(np.r_[CAPITAL, s])[1:] - s).max()) if len(s) else 0.0
        qb = g.saida.iloc[int(np.argmax(s <= 0))] if (s <= 0).any() else None
        out[int(ano)] = dict(liq=round(float(v.sum()), 2), ops=int(len(v)),
                             acerto=round(100 * float((v > 0).mean()), 1) if len(v) else None,
                             dd=round(dd, 2), quebra=str(qb)[:10] if qb is not None else None)
    return out


if __name__ == "__main__":
    t = _todas()
    for r in ROBOS:
        print(r, {a: v["liq"] for a, v in resumo(t[t.estrategia == r]).items()}, flush=True)
    print("soma isolada:", {a: v["liq"] for a, v in resumo(t).items()})
    print("preco teste:", preco("2026-03-10 10:30:00"), preco("2023-05-10 10:30:00"))
