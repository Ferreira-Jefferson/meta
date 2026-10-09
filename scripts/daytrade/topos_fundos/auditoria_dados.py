"""Auditoria das bases M1 sem leiloes usadas no estudo (out-dez/21, IS 2022-set/25, OOS out/25-out/26).

Por pregao: 1a barra deve ser 09:00; ultima = 1 min antes do fim do continuo da grade oficial (fim_continuo); minutos
esperados = fim - 09:00; minutos faltando (buracos > 1 min); horarios duplicados. Dias: comparados com o calendario de
pregoes do Ibovespa (yfinance ^BVSP, so como calendario) -> dias faltando / sobrando.
"""
import sys
import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, "src")
from market_data_intraday.win_sem_leiloes import carrega_grade, fim_continuo  # noqa: E402
from dados import PERIODOS  # noqa: E402

# fim inclusivo para o calendário (PERIODOS usa fim exclusivo)
BASES = {nome: (arq, ini, str((pd.Timestamp(fim) - pd.Timedelta(days=1)).date())) for nome, (arq, ini, fim) in PERIODOS.items()}

g = carrega_grade(None)
ib = yf.download("^BVSP", start="2021-10-01", end="2026-10-08", progress=False, auto_adjust=False)
cal = pd.DatetimeIndex(ib.index.normalize())
linhas = []
for nome, (arq, a, z) in BASES.items():
    d = pd.read_parquet(arq)
    d = d[(d.index >= a) & (d.index < pd.Timestamp(z) + pd.Timedelta(days=1))]
    dup = int(d.index.duplicated().sum())
    dias = d.index.normalize()
    esperado = cal[(cal >= a) & (cal <= z)]
    faltam = esperado.difference(dias.unique()); sobram = dias.unique().difference(esperado)
    prob = []
    for dia, x in d.groupby(dias):
        fim = fim_continuo(dia, g)
        exp_min = int((fim - (dia + pd.Timedelta(hours=9))).total_seconds() // 60)
        t = x.index
        gaps = np.diff(t.values).astype("timedelta64[m]").astype(int)
        buracos = int((gaps - 1)[gaps > 1].sum())
        maior = int(gaps.max()) - 1 if len(gaps) else 0
        ini_ok = t[0] == dia + pd.Timedelta(hours=9)
        fim_ok = t[-1] == fim - pd.Timedelta(minutes=1)
        if not (ini_ok and fim_ok) or buracos > 0 or len(x) != exp_min:
            prob.append(dict(base=nome, dia=dia.date(), primeira=t[0].strftime("%H:%M"), ultima=t[-1].strftime("%H:%M"),
                             fim_grade=fim.strftime("%H:%M"), barras=len(x), esperadas=exp_min, min_faltando=buracos, maior_buraco=maior))
    P = pd.DataFrame(prob)
    linhas.append(dict(base=nome, pregoes=dias.nunique(), pregoes_calendario=len(esperado), faltam=len(faltam), sobram=len(sobram),
                       duplicados=dup, dias_com_problema=len(P),
                       min_faltando_total=int(P.min_faltando.sum()) if len(P) else 0, barras=len(d)))
    print(f"\n===== {nome}: {dias.nunique()} pregões na base, {len(esperado)} no calendário")
    if len(faltam): print("  dias do calendário que faltam na base:", [x.date() for x in faltam])
    if len(sobram): print("  dias na base fora do calendário:", [x.date() for x in sobram])
    print("  horários duplicados:", dup)
    if len(P):
        pd.set_option("display.width", 200); print(P.to_string(index=False))
print("\nRESUMO"); print(pd.DataFrame(linhas).to_string(index=False))
