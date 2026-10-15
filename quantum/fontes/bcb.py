"""Banco Central — SGS (gratuito, sem chave). Série 12: CDI diário (% ao dia).

Vira um índice acumulado (base 1,0) para comparar com a carteira: o "100% do
CDI" do vídeo. A API limita cada consulta a 10 anos, então baixa em janelas.
Cada janela fica em `brutos/bcb/cdi/sgs12_<inicio>_<fim>.json`.
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd

from .. import config
from . import arquivo

URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json&dataInicial={ini}&dataFinal={fim}"


def baixar_cdi(inicio: str = config.INICIO_PRECOS) -> pd.DataFrame:
    ano0 = int(inicio[:4])
    hoje = date.today()
    partes = []
    for a in range(ano0, hoje.year + 1, 5):
        ini, fim = date(a, 1, 1), min(date(a + 4, 12, 31), hoje)
        destino = arquivo.caminho("bcb", "cdi", f"sgs12_{ini:%Y}_{fim:%Y}.json")
        aberta = fim.year >= hoje.year - 1  # janela que ainda recebe dias novos
        url = URL.format(ini=f"{ini:%d/%m/%Y}", fim=f"{fim:%d/%m/%Y}")
        p = arquivo.baixar(url, destino, "bcb", max_idade_h=12 if aberta else None)
        partes.extend(json.loads(p.read_text(encoding="utf-8")))
    df = pd.DataFrame(partes)
    df["data"] = pd.to_datetime(df.data, format="%d/%m/%Y")
    df["taxa"] = pd.to_numeric(df.valor) / 100.0
    df = df.drop_duplicates("data").sort_values("data")
    df["valor"] = (1 + df.taxa).cumprod()
    return pd.DataFrame({"serie": "CDI", "data": df.data.dt.strftime("%Y-%m-%d"), "valor": df.valor})
