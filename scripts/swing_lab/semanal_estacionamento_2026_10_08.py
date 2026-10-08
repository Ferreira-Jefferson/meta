"""Onde deixar o dinheiro quando o filtro de small caps esta desligado.

Contexto (2026-10-08): o filtro rs>m21 (SMLL/IBOV acima da MME21 da razao)
melhorou a carteira no IS e no OOS ficando FORA nos regimes ruins; na
VALIDACAO ficou fora o ano inteiro (0 operacoes) enquanto o BOVA11 fez +41%.
Ate aqui o caixa parado rendia 0%.

DECLARADO ANTES DE RODAR -- todas: recuo MME9 + stop inicial + ATR (14x2 e
21x3), R$1.000, R$1,90/ordem + 0,21%/perna, K=3 e K=5:
  A  sem filtro, caixa a 0% (como ate agora)
  B  sem filtro, caixa rende CDI
  C  com filtro, caixa rende CDI
  D  com filtro; filtro DESLIGADO -> o caixa livre compra BOVA11 na abertura do
     primeiro pregao da semana; filtro LIGADO -> vende o BOVA11 e o caixa fica
     para as acoes. Posicoes em acao abertas seguem as proprias saidas.
     Caixa que sobra rende CDI.
  Referencias: BOVA11 comprar e segurar; so CDI.
  Sucesso: D termina acima do BOVA11 comprar e segurar no IS E no OOS, com
  MaxDD no maximo 10 pontos pior que o dele.

CDI = Selic diaria do BCB (SGS 11, `data/raw/selic.parquet`, % ao dia); o CDI
anda ~0,1 ponto abaixo da Selic. Compra de BOVA11 so com caixa >= R$100,
para a taxa fixa nao comer a ordem.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base_mt5 as base  # noqa: E402
from semanal_linha_de_base_2026_10_08 import CAP0, PCT, TAXA, br, bh  # noqa: E402
from semanal_small_caps_2026_10_08 import estado_indices, medir  # noqa: E402
from concurrent.futures import ProcessPoolExecutor, as_completed  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MIN_BOVA = 100.0


def selic_dia() -> pd.Series:
    return pd.read_parquet(ROOT / "data" / "raw" / "selic.parquet")["valor"] / 100


def carteira(trades, cl, K, ini, fim, ocioso, filtro=None, bova=None, selic=None, semente=None):
    """ocioso: 'zero' | 'cdi' | 'bova'. `filtro`: bool semanal (sexta); vale do
    pregao seguinte ate a proxima sexta. `semente`: em vez do ranking de 12m,
    sinais do mesmo dia entram em ordem SORTEADA (mede quanto do resultado e
    sorte da selecao quando ha mais sinais que vagas)."""
    ent: dict[str, list] = {}
    for t in trades:
        ent.setdefault(t["entrada_data"], []).append(t)
    rng = np.random.default_rng(semente) if semente is not None else None
    for k in sorted(ent):
        v = ent[k]
        v.sort(key=lambda t: (-(t["pct12m"] or 0), t["ticker"]))  # desempate fixo: sem ele a ordem dos processos paralelos decidia
        if rng is not None:
            ent[k] = [v[i] for i in rng.permutation(len(v))]
    dias = cl.loc[ini:fim].index
    cash, taxas, pos, eq, bq, semanas_bova, n = CAP0, 0.0, [], [], 0, 0, 0
    sem_ant = None
    for dia in dias:
        ds = dia.strftime("%Y-%m-%d")
        if ocioso != "zero" and cash > 0:
            cash *= 1 + float(selic.asof(dia))
        semana = dia.to_period("W-FRI")
        if ocioso == "bova" and semana != sem_ant:
            ligado = bool(filtro.loc[:dia - pd.Timedelta(days=1)].iloc[-1])
            px = float(bova["open"].asof(dia))
            if ligado and bq:
                cash += bq * px * (1 - PCT) - TAXA; taxas += TAXA; bq = 0
            elif not ligado and cash >= MIN_BOVA:
                q = int((cash - TAXA) // (px * (1 + PCT)))
                if q > 0:
                    cash -= q * px * (1 + PCT) + TAXA; taxas += TAXA; bq += q
            semanas_bova += not ligado
        sem_ant = semana
        for fase in (0, 1):  # fecha, abre, fecha de novo (estopada no dia da entrada)
            for p in [p for p in pos if p["t"]["saida_data"] == ds]:
                cash += p["q"] * p["t"]["saida"] * (1 - PCT) - TAXA; taxas += TAXA; n += 1
                pos.remove(p)
            if fase == 1:
                break
            for t in ent.get(ds, []):
                if len(pos) >= K or any(p["t"]["ticker"] == t["ticker"] for p in pos):
                    continue
                pat = cash + sum(p["q"] * cl.at[dia, p["t"]["ticker"]] for p in pos)
                q = int((min(cash, pat / K) - TAXA) // (t["entrada"] * (1 + PCT)))
                if q < 1:
                    continue
                cash -= q * t["entrada"] * (1 + PCT) + TAXA; taxas += TAXA
                pos.append({"t": t, "q": q})
        eq.append(cash + sum(p["q"] * cl.at[dia, p["t"]["ticker"]] for p in pos)
                  + (bq * float(bova["close"].asof(dia)) if bq else 0))
    e = pd.Series(eq, index=dias)
    return dict(final=float(e.iloc[-1]), dd=float((e / e.cummax() - 1).min()), n=n + len(pos), taxas=taxas,
                bova=semanas_bova / max(1, len(set(d.to_period("W-FRI") for d in dias))))


def main() -> None:
    idx = estado_indices()
    rs = idx["rs>m21"]
    bova = pd.read_parquet(base.PASTA / "BOVA11.parquet")[["open", "close"]].loc[: base.PESQUISA[1]]
    selic = selic_dia()
    for conjunto in ("is", "oos"):
        ini, fim = base.janela(conjunto)
        tks = base.papeis(conjunto)
        trades, r52, closes = [], {}, {}
        with ProcessPoolExecutor(max_workers=2) as ex:
            for f in as_completed([ex.submit(medir, tk, conjunto, ["base", "rs>m21"], idx) for tk in tks]):
                tk, tr, r, c = f.result()
                trades += tr; closes[tk] = c
                if r:
                    r52[tk] = pd.Series(r)
        pct = pd.DataFrame(r52).rank(axis=1, pct=True)
        for t in trades:
            s = t["semana_sinal"]
            v = pct.at[s, t["ticker"]] if s in pct.index else np.nan
            t["pct12m"] = None if pd.isna(v) else float(v)
        cl = pd.DataFrame(closes).sort_index().ffill().loc[:fim]
        b = bh(bova["close"], ini, fim)
        cdi = CAP0 * float(np.prod(1 + selic.loc[ini:fim]))
        print(f"\n== {conjunto.upper()} — {len(tks)} papéis, {ini} a {fim}", flush=True)
        print(f"  BOVA11 comprar e segurar   R${br(b['final'], 0, pct=False, sinal=False):>6s}  MaxDD {br(b['dd'], 1)}", flush=True)
        print(f"  só CDI                     R${br(cdi, 0, pct=False, sinal=False):>6s}  MaxDD 0,0%", flush=True)
        for v in ("atr14x2", "atr21x3"):
            for nome, filtro, ocioso in (("A sem filtro, caixa 0%", "base", "zero"), ("B sem filtro, CDI", "base", "cdi"),
                                         ("C filtro, CDI", "rs>m21", "cdi"), ("D filtro, BOVA11 parado", "rs>m21", "bova")):
                tv = [t for t in trades if t["filtro"] == filtro and t["var"] == v]
                cel = []
                for K in (3, 5):
                    r = carteira(tv, cl, K, ini, fim, ocioso, rs, bova, selic)
                    extra = f" BOVA11 {r['bova']:.0%} das sem." if ocioso == "bova" else ""
                    cel.append(f"K{K} R${br(r['final'], 0, pct=False, sinal=False):>6s} dd{br(r['dd'], 0):>5s} n={r['n']:3d}{extra}")
                print(f"  {v} {nome:24s} " + " | ".join(cel), flush=True)


if __name__ == "__main__":
    main()
