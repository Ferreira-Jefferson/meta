"""Baixa um pool LARGO da B3 e grava em DUAS pastas fisicamente separadas.

Por que existe
--------------
O `POOL` de 63 papeis em `strategy/liquid_sleeve.py` nao e um desenho: e o
conteudo de `data/raw/`, e o proprio docstring do campeao declara isso como
vies residual. A consequencia so apareceu ao montar o cofre 1998-2009: apenas
16-18 daqueles papeis tem os 504 pregoes exigidos antes de 2005, contra os 20
que o robo precisa para montar universo. Com o pool antigo, o cofre chega a 20
elegiveis so em 2007 — tarde demais para qualquer janela de 5 anos caber.

Alargar o pool resolve dois problemas ao mesmo tempo:
  1. torna o cofre mensuravel (universo existe desde ~2002);
  2. reduz o vies de selecao, porque 63 sobreviventes de 2026 e uma amostra
     muito mais estreita que a bolsa negociavel da epoca.

Separacao fisica como mecanismo de cegueira
-------------------------------------------
Grava DUAS pastas a partir do mesmo download:

  data/wide_e/            2010-01-01 .. hoje    camada de EXPLORACAO
  data/vault_1998_2009/   1998-01-01 .. 2009-12 COFRE, selado

Nao e uma pasta com filtro de data no codigo: sao arquivos diferentes. Um
agente de busca que receba `data/wide_e` nao tem como ler 2003 nem por
acidente, e e isso que faz o cofre ser cego de verdade.

`data/raw/` NAO e tocado. Ele alimenta o robo ao vivo e o painel, e ha sessao
concorrente editando este repo — mexer ali trocaria o universo do campeao em
producao no meio de uma busca.

Vies que CONTINUA de pe, e precisa continuar declarado
------------------------------------------------------
Todo ticker desta lista esta vivo (ou pelo menos listado) em 2026. Quem quebrou
ou saiu da bolsa entre 2000 e hoje nao entra, porque o yfinance nao serve
historico de papel deslistado. O pool largo REDUZ o vies — nao o elimina.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from market_data.download import download_macro, download_one, save_parquet
from market_data.quality import consensus_calendar, fill_gaps

ROOT = Path(__file__).resolve().parents[1]
DIR_E = ROOT / "data" / "wide_e"
DIR_V = ROOT / "data" / "vault_1998_2009"

START = "1998-01-01"
VAULT_END = "2009-12-31"
EXPLORE_START = "2010-01-01"

# Pool largo: nomes da B3 com chance real de historico longo, mais o pool atual.
# Inclui classes duplicadas (ITUB3/ITUB4, VALE3/VALE5) de proposito — o filtro
# de liquidez escolhe qual classe gira mais na data, que e a decisao certa.
CANDIDATOS: tuple[str, ...] = (
    # bancos e financeiro
    "BBAS3.SA", "BBDC3.SA", "BBDC4.SA", "ITUB3.SA", "ITUB4.SA", "ITSA3.SA",
    "ITSA4.SA", "SANB4.SA", "SANB11.SA", "BRSR6.SA", "BEES3.SA", "BEES4.SA",
    "BGIP4.SA", "BMEB3.SA", "BMEB4.SA", "BPAN4.SA", "PINE4.SA", "ABCB4.SA",
    "BAZA3.SA", "BRIV4.SA", "BMGB4.SA", "BPAC11.SA", "CRIV4.SA", "IDVL4.SA",
    "PSSA3.SA", "SULA11.SA", "BBSE3.SA", "CXSE3.SA", "IRBR3.SA", "CIEL3.SA",
    # siderurgia, mineracao, metalurgia
    "VALE3.SA", "VALE5.SA", "CSNA3.SA", "GGBR3.SA", "GGBR4.SA", "GOAU3.SA",
    "GOAU4.SA", "USIM3.SA", "USIM5.SA", "USIM6.SA", "BRAP3.SA", "BRAP4.SA",
    "FESA3.SA", "FESA4.SA", "PMAM3.SA", "MTSA4.SA", "TKNO4.SA", "CMIN3.SA",
    # petroleo, quimica, papel
    "PETR3.SA", "PETR4.SA", "UGPA3.SA", "UGPA4.SA", "CSAN3.SA", "RPMG4.SA",
    "BRKM3.SA", "BRKM5.SA", "UNIP6.SA", "SUZB3.SA", "SUZB5.SA", "KLBN3.SA",
    "KLBN4.SA", "KLBN11.SA", "FIBR3.SA", "VCPA4.SA", "DTEX3.SA", "EUCA4.SA",
    # energia e saneamento
    "CMIG3.SA", "CMIG4.SA", "CPLE3.SA", "CPLE6.SA", "CPFE3.SA", "ELET3.SA",
    "ELET6.SA", "ELPL4.SA", "EMAE4.SA", "ENBR3.SA", "EQTL3.SA", "LIGT3.SA",
    "TRPL4.SA", "CESP6.SA", "COCE5.SA", "CLSC4.SA", "REDE4.SA", "GEPA4.SA",
    "AFLT3.SA", "ENGI4.SA", "ENGI11.SA", "TAEE11.SA", "ALUP11.SA", "EGIE3.SA",
    "TBLE3.SA", "SBSP3.SA", "CSMG3.SA", "SAPR4.SA", "SAPR11.SA", "CGAS3.SA",
    "CGAS5.SA", "MSPA4.SA", "ENEV3.SA",
    # telecom
    "VIVT3.SA", "VIVT4.SA", "TIMS3.SA", "TCSL4.SA", "TLPP4.SA", "BRTO4.SA",
    "OIBR3.SA", "OIBR4.SA", "TELB4.SA",
    # consumo e varejo
    "LREN3.SA", "PCAR3.SA", "PCAR4.SA", "GUAR3.SA", "HGTX3.SA", "BTOW3.SA",
    "LAME3.SA", "LAME4.SA", "CGRA4.SA", "GRND3.SA", "ALPA3.SA", "ALPA4.SA",
    "SLED4.SA", "WHRL4.SA", "MNDL3.SA", "BOBR4.SA", "ETER3.SA", "DURA4.SA",
    # alimentos e bebidas
    "ABEV3.SA", "AMBV4.SA", "BRFS3.SA", "PRGA3.SA", "JBSS3.SA", "MRFG3.SA",
    "SMTO3.SA", "MDIA3.SA",
    # industria e bens de capital
    "WEGE3.SA", "EMBR3.SA", "POMO3.SA", "POMO4.SA", "ROMI3.SA", "KEPL3.SA",
    "MYPK3.SA", "RAPT3.SA", "RAPT4.SA", "LEVE3.SA", "TUPY3.SA", "FRAS3.SA",
    "INEP4.SA", "MWET4.SA", "SHUL4.SA", "TASA4.SA", "BDLL4.SA", "RSUL4.SA",
    "EALT4.SA", "TOTS3.SA", "POSI3.SA",
    # saude e farma
    "RADL3.SA", "RADL4.SA", "PNVL3.SA", "PNVL4.SA", "DASA3.SA", "FLRY3.SA",
    "ODPV3.SA", "HYPE3.SA", "HAPV3.SA", "RDOR3.SA", "MATD3.SA", "AALR3.SA",
    "BLAU3.SA",
    # construcao, shoppings, logistica
    "CYRE3.SA", "GFSA3.SA", "EZTC3.SA", "MRVE3.SA", "TCSA3.SA", "RSID3.SA",
    "EVEN3.SA", "JHSF3.SA", "TRIS3.SA", "BRML3.SA", "MULT3.SA", "IGTA3.SA",
    "CCRO3.SA", "ECOR3.SA", "ALLL3.SA", "GOLL4.SA", "RENT3.SA", "TGMA3.SA",
    "LOGN3.SA", "LPSB3.SA",
    # ETFs (o pool atual os inclui; o filtro de liquidez decide)
    "BOVA11.SA", "GOLD11.SA", "IMAB11.SA",
    # indice
    "^BVSP",
)


def main() -> None:
    DIR_E.mkdir(parents=True, exist_ok=True)
    DIR_V.mkdir(parents=True, exist_ok=True)

    frames: dict[str, pd.DataFrame] = {}
    sem_dado: list[str] = []
    for t in CANDIDATOS:
        try:
            df = download_one(t, start=START)
        except Exception:
            sem_dado.append(t)
            continue
        if df.empty or len(df) < 250:
            sem_dado.append(t)
            continue
        frames[t] = df

    print(f"baixados: {len(frames)}  |  sem dado: {len(sem_dado)}")

    # Calendario de consenso e fill_gaps por CAMADA — o calendario da B3 de 2003
    # nao tem nada a ver com o de 2020, e um consenso unico sobre 28 anos
    # inventaria sessao em todo feriado que mudou de data.
    for nome, dst, lo, hi in (
        ("cofre",      DIR_V, START,         VAULT_END),
        ("exploracao", DIR_E, EXPLORE_START, None),
    ):
        camada = {}
        for t, df in frames.items():
            sl = df.loc[lo:hi] if hi else df.loc[lo:]
            if len(sl) >= 250:
                camada[t] = sl
        cal = consensus_calendar(camada)
        for t, df in camada.items():
            if cal is not None:
                df, _ = fill_gaps(df, cal)
            save_parquet(t, df, out_dir=dst)
        download_macro(start=lo, out_dir=dst)
        print(f"[{nome}] {len(camada)} papeis gravados em {dst.name}")

    print(f"\nsem dado: {sorted(sem_dado)}")


if __name__ == "__main__":
    main()
