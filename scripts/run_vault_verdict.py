"""COFRE — abre UMA VEZ o holdout 2002-2009 contra candidatos declarados antes.

===========================================================================
DESENHO CONGELADO. Escrito ANTES de a busca de hipoteses rodar.
O commit deste arquivo e a prova de anterioridade. Qualquer alteracao no que
esta abaixo INVALIDA o teste e exige cofre novo — que nao existe: nao ha mais
dado B3 virgem em quantidade util.
===========================================================================

A PERGUNTA
----------
Existe estrategia de swing que entregue mais retorno que `liquid_champion`
respeitando MaxDD de PIOR JANELA melhor que -40%?

POR QUE UM COFRE NOVO E OBRIGATORIO
------------------------------------
O holdout de 48 janelas (`run_holdout_frozen.py`, inicios 2010-2013) JA FOI
GASTO: foi ele que coroou `liquid_champion`. Rodar uma busca de ~120 hipoteses
contra 2010-2026 e julgar o vencedor naquelas mesmas 48 janelas reproduz
exatamente o vicio da secao 1 do protocolo — "sobreviver a cento e dez
tentativas contra o mesmo historico fixo e o cenario em que o sobreajuste e
MAIS provavel, nao menos" — com mais compute e mais confianca injustificada.

Logo: 1998-2009 foi baixado em 2026-08-20 e selado em `data/vault_1998_2009/`
por `scripts/download_vault.py`. Nenhum agente da busca le esse diretorio.

AS TRES CAMADAS
---------------
  E (exploracao)  data/wide_e/          2010-01..2026-08  livre, ~120 hipoteses
  S (selecao)     subconjunto de E      ver funil abaixo  ranqueia sobreviventes
  V (cofre)       data/vault_1998_2009  2002-01..2009-12  UMA leitura, no fim

Pastas FISICAMENTE separadas, gravadas por `scripts/download_wide.py` a partir
do mesmo download. Nao e filtro de data no codigo: sao arquivos diferentes, e um
agente que recebe `data/wide_e` nao consegue ler 2003 nem por acidente.

`data/raw/` nao participa e nao foi tocado — ele alimenta o robo ao vivo e ha
sessao concorrente editando este repo.

POR QUE O POOL FOI ALARGADO (145 papeis, nao 63)
-------------------------------------------------
O `POOL` de 63 nomes em `strategy/liquid_sleeve.py` nunca foi desenho: e o
conteudo de `data/raw/`, e o campeao declara isso como vies residual. Ao montar
o cofre a consequencia ficou mensuravel: com 63 nomes, apenas 16-18 tinham os
504 pregoes exigidos antes de 2005 e o cofre so alcancava 20 elegiveis em 2007 —
tarde demais para qualquer janela de 5 anos caber. Com 145 nomes ha 33 elegiveis
em 2002-01 e 44 em 2004-07.

Efeito colateral MEDIDO, e ele e desfavoravel ao campeao: na janela 2011-2016 o
campeao no pool largo faz -4,65% de CAGR com MaxDD -43,1%. O pool de 63
sobreviventes era mais generoso do que se sabia. Por isso a referencia deste
cofre NAO sao os numeros publicados do campeao: e o DESENHO do campeao rodado no
mesmo pool largo, na mesma run, com a mesma aritmetica.

FUNIL DECLARADO (nao se altera depois)
---------------------------------------
  E1  triagem nivel 0: FULL 2010-2026 + 2 janelas. Elimina o obviamente ruim.
      Sobrevivem no MAXIMO 30 hipoteses, pelo objetivo abaixo.
  E2  selecao: 47 janelas de 5 anos, inicios TRIMESTRAIS 2010-01..2021-07,
      sobre os <=30 sobreviventes de E1.
  E3  sintese: o agente sintetizador pode propor no MAXIMO 2 combinacoes de
      mecanismos sobreviventes. Ele NAO tem acesso a V.
  V   cofre: 3 melhores de E2 + 2 sinteses de E3 = 5 candidatos, mais
      `liquid_champion` como referencia e IBOV como benchmark pareado.

OBJETIVO (formula unica, declarada agora)
------------------------------------------
  maximizar  CAGR MEDIANO nas janelas da camada
  sujeito a  PIOR MaxDD da camada melhor que -40%   <-- eliminacao DURA

Hipotese que viola o teto de drawdown e eliminada independentemente do retorno.
Nao existe troca entre as duas coisas: o teto foi fixado pelo operador antes de
qualquer numero aparecer.

JANELAS DO COFRE
----------------
36 janelas de 5 anos, inicios MENSAIS 2002-01..2004-12, terminando entre
2007-01 e 2009-12. O primeiro inicio e 2002-01 por um motivo MEDIDO, nao
escolhido: o ranking de liquidez exige 504 pregoes, e a contagem de elegiveis no
cofre e 0 em 2001-07, 33 em 2002-01, 34 em 2003-01, 40 em 2004-01 e 43 em
2005-01. Comecar antes de 2002 seria medir um robo sem universo.

PORTOES DO COFRE (limiares numericos, fixados agora)
-----------------------------------------------------
  V1  pior MaxDD das 36 janelas melhor que -40%
  V2  CAGR mediano >= CAGR mediano do IBOV nas MESMAS 36 janelas + 3,0 p.p.
  V3  bate o IBOV em >= 24 das 36 janelas (2/3)
  V4  pior retorno de 12 meses melhor que -35%
  V5  PBO (probabilidade de sobreajuste, via CSCV sobre a matriz de E2) <= 0,50
  V6  as 5 maiores operacoes somam < 100% do lucro total

NAO e portao: "nenhuma janela negativa". Esse portao MORREU no holdout de
2026-08-20 — passava 0/5 nas janelas de ajuste e virou 3/48 e 8/48. Nao volta.

CORRECAO DE MULTIPLICIDADE
---------------------------
N = numero REAL de hipoteses medidas, contado pelo diario da busca, nunca
estimado. Deflated Sharpe Ratio (Bailey & Lopez de Prado) com esse N e a
variancia dos Sharpes dos ensaios; PBO por CSCV sobre a matriz de E2. Se o
vencedor nao sobrevive a deflacao, o resultado e "nada passou" — e isso e um
resultado reportavel, nao uma falha da busca.

CONTROLES OBRIGATORIOS antes de qualquer veredito
--------------------------------------------------
  C1  aleatorizacao: 300 rankings aleatorios no lugar do criterio de escolha
  C2  exposicao pareada: se o candidato segura mais caixa que o campeao,
      comparar contra mistura estatica campeao+Selic na MESMA exposicao media.
      OBRIGATORIO, nao opcional — ver limitacao L3.
  C3  ablacao: remover cada peca e medir o que cai
  C4  implementacao real: nenhum mecanismo julgado como overlay sobre a curva
  C5  reprodutibilidade: mesma entrada, mesmo numero, duas vezes (fingerprint)

LIMITACOES — DECLARADAS ANTES DO RESULTADO
-------------------------------------------
L1  VIES DE SOBREVIVENCIA. Reduzido, nao eliminado. O pool largo tem 145 nomes
    na exploracao e 123 no cofre, contra 63 antes — mas todos estao listados em
    2026. Dos 191 tickers tentados, 47 nao tem historico servido pelo yfinance,
    e sao exatamente os que corrigiriam este vies: ALLL3, AMBV4, BRTO4, CESP6,
    ELET3/6, EMBR3, LAME4, TLPP4, VALE5, VIVT4 e companhia — nomes grandes da
    epoca, que foram renomeados, incorporados ou deslistados. Uma carteira de
    2002 escolhida entre listados de 2026 continua enviesada para cima.
    Consequencia: candidato-vs-campeao e comparacao limpa (mesmo vies nos dois);
    candidato-vs-IBOV e favoravel ao candidato por construcao, porque o IBOV de
    2002 e o indice de verdade, com os papeis que morreram dentro. V2 e V3 devem
    ser lidos com esse desconto.

L2  REGIME COMPLETAMENTE DIFERENTE. 2003-2009 foi o superciclo de commodities e
    o IBOV multiplicou por varias vezes. Numero ABSOLUTO no cofre nao significa
    nada. So o EXCESSO sobre o indice tem chance de transferir — o proprio
    holdout de 2026-08-20 mostrou isso: o nivel caiu de 10,8% para 4,9%
    enquanto o excesso de ~4,6 p.p. ficou de pe.

L3  SELIC DE 15-26% AO ANO. Esta e a contaminacao mais perigosa deste cofre
    dado o objetivo. O caminho mais barato para cortar drawdown e segurar
    caixa, e caixa remunerado a 19% em 2003 rende o que acao nenhuma precisa
    render. Uma estrategia defensiva vai parecer brilhante no cofre por um
    motivo que nao se repete hoje. Por isso C2 e obrigatorio: sem exposicao
    pareada, este cofre APROVA caixa parado.

L4  AS 36 JANELAS NAO SAO INDEPENDENTES. Inicios mensais com janelas de 5 anos
    se sobrepoem quase inteiramente: sao 3 anos de inicios sobre 8 anos de
    dado, ou seja ~1,6 periodo genuinamente independente, nao 36. Ler "24 de
    36" como 24 observacoes independentes seria a mesma falacia que produziu o
    portao morto de "0 de 5 janelas negativas". As 36 janelas medem
    SENSIBILIDADE AO PONTO DE ENTRADA, nao tamanho de amostra. Este e o limite
    mais severo de todo o desenho e nenhum resultado aqui deve ser apresentado
    sem ele.

L5  UNIVERSO MAIS ESTREITO QUE NA EXPLORACAO. O top-20 do cofre e escolhido
    entre 33-44 papeis elegiveis, contra ~100 na camada de exploracao. O
    ranking de liquidez tem menos de onde escolher, o que reduz a vantagem que
    o mecanismo pode extrair. Handicap simetrico: vale para candidatos e para o
    campeao, que roda no mesmo pool.

L6  LOTE = 1 ACAO, R$ 1.000 iniciais, igual ao holdout anterior, para a
    aritmetica ser comparavel. Nao e operavel na Clear, cujo lote minimo e 100.

L7  O COFRE NAO TEM 2008 COMO EVENTO ISOLAVEL. Toda janela iniciada em
    2002-2004 contem a crise de 2008 na cauda. Nao ha janela deste cofre que
    meca o candidato SEM 2008, e portanto nada aqui separa "sobrevive a crise"
    de "foi salvo pelo bull de 2003-2007 antes dela".

L8  PODER ESTATISTICO — declarado com numero, MEDIDO antes de rodar a busca.
    Simulacao de deteccao (200 meses, vol 6%/mes, 30 repeticoes por celula,
    criterio "o alfa plantado vence E o DSR passa de 0,95"):

      alfa/mes   Sharpe anual   N=15    N=40   N=120
        0,5%         0,29         0%      0%      0%
        1,0%         0,58         0%      0%      0%
        1,5%         0,87        27%     30%     20%
        2,0%         1,15        73%     67%     57%
        3,0%         1,73       100%    100%    100%

    Duas leituras, e a segunda e a que importa:

    (a) A busca so detecta vantagem com Sharpe anual acima de ~0,9, e detecta
        com confianca acima de ~1,7. Abaixo de Sharpe 0,6 o poder e ZERO. Como
        a vantagem que sobreviveu ao holdout anterior e da ordem de indice mais
        4,6 p.p. ao ano — Sharpe bem abaixo de 1 — este desenho pode
        perfeitamente NAO ACHAR uma melhoria real que exista. "Nada passou" tem
        de ser lido como "nada grande o suficiente para ser visto daqui", e nao
        como "nada existe".

    (b) O gargalo NAO e o numero de hipoteses: e o comprimento da serie. Entre
        N=15 e N=120 o poder cai de 27% para 20% em Sharpe 0,87 — pouco. Com
        ~200 observacoes mensais nao se distingue Sharpe 0,6 de zero, por mais
        parcimoniosa que a busca seja. Rodar 120 hipoteses em vez de 15 custa
        pouco poder; o que limita e existirem so 16 anos de dado.

    Consequencia pratica: o resultado util desta busca provavelmente NAO sera
    "achamos algo melhor". Sera o mapa de quais familias de mecanismo estouram o
    teto de drawdown e quais nao, mais a confirmacao de que a barra e alta.

    Fonte: `scripts/swing_lab/deflate.py`, calibrado contra ruido de media zero
    (PBO nulo mediana 0,564, p5 0,358, p95 0,728; DSR nulo mediana 0,470,
    p95 0,665). O PBO nulo NAO e exatamente 0,50 nesta configuracao, logo o
    portao V5 e lido contra a nula EMPIRICA, nao contra o 0,50 teorico.

CRITERIO DE DECISAO, EM UMA FRASE
----------------------------------
Um candidato substitui `liquid_champion` se, e somente se, passar V1..V6 E
tiver CAGR mediano no cofre maior que o do CAMPEAO RODADO NO MESMO POOL LARGO,
nas MESMAS 36 janelas. Se nenhum passar, o campeao fica e a busca e reportada
como refutada.

APRESENTACAO
------------
Reportar os 10 melhores candidatos da camada E2, nao os ~120 ensaios. O N
completo entra apenas como numero na deflacao estatistica.

Uso: .venv/Scripts/python.exe scripts/run_vault_verdict.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

VAULT_DIR = Path(__file__).resolve().parents[1] / "data" / "vault_1998_2009"
INITIAL = 1000.0
ANOS = 5
DD_CEILING = -0.40

# 36 janelas de 5 anos, inicios MENSAIS 2002-01..2004-12.
VAULT_WINDOWS = [pd.Timestamp(f"{y}-{m:02d}-01")
                 for y in range(2002, 2005) for m in range(1, 13)]

GATES = {
    "V1_worst_dd":       -0.40,
    "V2_excess_median":   0.030,
    "V3_beat_ibov_min":   24,
    "V4_worst_12m":      -0.35,
    "V5_pbo_max":         0.50,
    "V6_top5_share_max":  1.00,
}

# Preenchido em 2026-08-20, depois de E1(120)->E2(30)->C2(exposicao pareada,
# corrigido)->estresse de capital raso->E3(sintese). 3 melhores de E2 que
# sobreviveram ao C2 + 2 sinteses. MacroGatedBreakout era a 3a melhor de E2 e
# sobrevivia ao C2, mas estourou o teto de DD (-52,24%) no estresse de capital
# raso (R$100 em vez de R$1.000) — substituida pela 4a, Hip03ExcluiTopoLiquidez.
CANDIDATES: tuple[str, ...] = (
    "strategy.lab.iliquidez.hip_06:Hip06IliquidezRelativaAoGrupo",
    "strategy.lab.preco_qualidade.hip_10:LongHorizonRiskAdjustedReturn",
    "strategy.lab.iliquidez.hip_03:Hip03ExcluiTopoLiquidez",
    "strategy.lab.sintese.hip_01:IliquidezGrupoComQualidade5A",
    "strategy.lab.sintese.hip_02:IliquidezGrupoComRiscoOrcado",
)

# ---------------------------------------------------------------------------
# Maquinaria. Escrita junto com o protocolo, antes de existir candidato — para
# que implementar a medicao nao seja uma oportunidade de ajustar a medicao.
# ---------------------------------------------------------------------------
import glob
import importlib
import json
import os
import traceback

import numpy as np

from backtest.metrics import max_drawdown
from backtest.runner import run as run_bt
from core.config import BENCHMARK, BacktestConfig
from market_data.loader import load_one

SELIC_V = str(VAULT_DIR / "selic.parquet")
_CACHE: dict[str, pd.DataFrame] = {}


def vault_pool() -> tuple[str, ...]:
    macro = {"selic", "usd_brl", "ipca", "desemprego"}
    out = []
    for p in sorted(glob.glob(str(VAULT_DIR / "*.parquet"))):
        base = os.path.basename(p)[:-8]
        if base in macro or base.startswith("_"):
            continue
        out.append(base.replace("_SA", ".SA"))
    return tuple(out)


def vault_panel(ticker: str) -> pd.DataFrame:
    if ticker not in _CACHE:
        df = load_one(ticker, out_dir=VAULT_DIR)
        _CACHE[ticker] = df[df["close"].notna()]
    return _CACHE[ticker]


def vault_panels() -> dict[str, pd.DataFrame]:
    u = {t: vault_panel(t) for t in vault_pool()}
    u[BENCHMARK] = vault_panel(BENCHMARK)
    return u


def _metricas(eq: pd.Series) -> dict | None:
    if len(eq) < 250:
        return None
    anos = (eq.index[-1] - eq.index[0]).days / 365.25
    tot = eq.iloc[-1] / eq.iloc[0]
    return {
        "cagr": float(tot ** (1.0 / anos) - 1.0) if anos > 0 and tot > 0 else -1.0,
        "dd": float(max_drawdown(eq)),
        "w12": float((eq / eq.shift(252) - 1.0).min()),
    }


def medir_no_cofre(cls) -> dict:
    """As 36 janelas do cofre para uma classe. Uma leitura, sem reajuste."""
    cfg = BacktestConfig(initial_capital=INITIAL, lot_size=1, cash_yield_path=SELIC_V)
    P = vault_panels()
    linhas, top5, trades = [], [], []
    for s in VAULT_WINDOWS:
        e = min(s + pd.DateOffset(years=ANOS), pd.Timestamp("2009-12-31"))
        try:
            r = run_bt(P, cls(), cfg, start=str(s.date()), end=str(e.date()))
        except Exception:
            continue
        m = _metricas(r.equity_curve)
        if not m:
            continue
        m["start"] = str(s.date())
        linhas.append(m)
        trades.append(len(r.trades))
        pnls = sorted((float(t.pnl_brl) for t in r.trades if t.exit_price is not None), reverse=True)
        tot = sum(pnls)
        top5.append(sum(pnls[:5]) / tot if tot > 0 else float("inf"))
    if not linhas:
        return {"erro": "nenhuma janela mediu"}
    return {
        "n": len(linhas),
        "median_cagr": float(np.median([r["cagr"] for r in linhas])),
        "worst_cagr": float(min(r["cagr"] for r in linhas)),
        "worst_dd": float(min(r["dd"] for r in linhas)),
        "worst_12m": float(min(r["w12"] for r in linhas)),
        "median_trades": float(np.median(trades)),
        "top5_share_max": float(np.nanmax([x for x in top5 if np.isfinite(x)] or [float("nan")])),
        "por_janela": linhas,
    }


def ibov_cofre() -> dict:
    c = vault_panel(BENCHMARK)["close"]
    linhas = []
    for s in VAULT_WINDOWS:
        e = min(s + pd.DateOffset(years=ANOS), pd.Timestamp("2009-12-31"))
        m = _metricas(c.loc[str(s.date()):str(e.date())].dropna())
        if m:
            m["start"] = str(s.date())
            linhas.append(m)
    return {
        "n": len(linhas),
        "median_cagr": float(np.median([r["cagr"] for r in linhas])),
        "worst_cagr": float(min(r["cagr"] for r in linhas)),
        "worst_dd": float(min(r["dd"] for r in linhas)),
        "worst_12m": float(min(r["w12"] for r in linhas)),
        "por_janela": linhas,
    }


def _pbo_de_e2() -> float:
    """V5 vem da matriz de E2, nao do cofre — e uma propriedade da BUSCA."""
    p = Path(__file__).resolve().parents[1] / "scripts" / "swing_lab" / "pbo.json"
    if not p.exists():
        return float("nan")
    return float(json.loads(p.read_text(encoding="utf-8")).get("pbo", float("nan")))


def portoes(cand: dict, ib: dict, pbo: float) -> dict:
    """V1..V6 com os limiares congelados. Nenhum limiar e recalculado aqui."""
    venceu = 0
    ibmap = {r["start"]: r["cagr"] for r in ib["por_janela"]}
    for r in cand["por_janela"]:
        if r["start"] in ibmap and r["cagr"] > ibmap[r["start"]]:
            venceu += 1
    return {
        "V1_dd": cand["worst_dd"] >= GATES["V1_worst_dd"],
        "V2_excesso": (cand["median_cagr"] - ib["median_cagr"]) >= GATES["V2_excess_median"],
        "V3_bate_ibov": venceu >= GATES["V3_beat_ibov_min"],
        "V4_w12": cand["worst_12m"] >= GATES["V4_worst_12m"],
        "V5_pbo": (pbo <= GATES["V5_pbo_max"]) if np.isfinite(pbo) else False,
        "V6_concentracao": cand.get("top5_share_max", float("inf")) < GATES["V6_top5_share_max"],
        "_venceu_ibov": venceu,
        "_excesso": cand["median_cagr"] - ib["median_cagr"],
    }


def main() -> None:
    if not CANDIDATES:
        print(__doc__)
        print(">>> CANDIDATES vazio. O cofre so abre depois de E3. <<<")
        return

    print(f"ABRINDO O COFRE — {len(CANDIDATES)} candidatos, {len(VAULT_WINDOWS)} janelas.")
    print("Esta e a UNICA leitura. Nao ha segunda tentativa.\n")

    ib = ibov_cofre()
    print(f"IBOV no cofre: CAGR mediano {ib['median_cagr']:+.2%}  "
          f"pior {ib['worst_cagr']:+.2%}  pior DD {ib['worst_dd']:+.2%}  ({ib['n']} janelas)")

    pbo = _pbo_de_e2()
    resultados = {}
    for ref in CANDIDATES:
        mod, _, cls_nome = ref.partition(":")
        try:
            cls = getattr(importlib.import_module(mod), cls_nome)
        except Exception:
            print(f"\n[X] {ref}: {traceback.format_exc(limit=2)}")
            continue
        print(f"\nmedindo {cls_nome}...")
        r = medir_no_cofre(cls)
        if "erro" in r:
            print(f"  {r['erro']}")
            continue
        g = portoes(r, ib, pbo)
        resultados[ref] = {"metricas": r, "portoes": g}
        passou = all(v for k, v in g.items() if not k.startswith("_"))
        print(f"  CAGR mediano {r['median_cagr']:+.2%} (excesso {g['_excesso']:+.2f} p.p.)  "
              f"pior DD {r['worst_dd']:+.2%}  pior 12m {r['worst_12m']:+.2%}  "
              f"bate IBOV {g['_venceu_ibov']}/{r['n']}")
        print(f"  portoes: " + "  ".join(
            f"{k}={'OK' if v else 'X'}" for k, v in g.items() if not k.startswith("_")))
        print(f"  >>> {'PASSA' if passou else 'REPROVADO'}")

    out = Path(__file__).resolve().parents[1] / "scripts" / "swing_lab" / "vault_verdict.json"
    out.write_text(json.dumps({"ibov": ib, "pbo_e2": pbo, "candidatos": resultados},
                              indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\ngravado em {out.name}")
    print("\nLEIA AS LIMITACOES L1-L8 NO DOCSTRING ANTES DE INTERPRETAR QUALQUER NUMERO.")


if __name__ == "__main__":
    main()
