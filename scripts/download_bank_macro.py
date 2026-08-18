"""Baixa series macro/setoriais REAIS do BCB SGS especificas do setor bancario
para uso como sinal em estrategias de trading de bancos (ITUB4, BBDC4, BBAS3,
SANB11, BPAC11, BRSR6, ABCB4, etc.).

Uso: python scripts/download_bank_macro.py

Nao mexe em `src/market_data/download.py` nem em `BCB_MACRO_SERIES` (usado
pelo pipeline oficial do robo campeao em producao) — este e um modulo/script
separado que reaproveita a mesma mecanica de fetch (chunk de 10 anos,
User-Agent "curl/8.0" que a API do BCB exige) via
`market_data.download._bcb_fetch`.

Todos os codigos abaixo foram CONFIRMADOS por chamada real a API em 2026-08-18
(`.../dados/ultimos/5?formato=json`) antes de entrarem nesta lista — nenhum
foi assumido de memoria. Cada serie tem a fonte/descricao oficial do catalogo
SGS (https://dadosabertos.bcb.gov.br) citada no comentario.

ACHADO IMPORTANTE (verificado via chamada real com dataInicial=01/01/2010):
todas as series abaixo, EXCETO `saldo_credito_sfn` (codigo 20539, que comeca
em 01/2010), so tem historico a partir de 03/2011 — e quando o BCB passou a
publicar as estatisticas de credito na metodologia atual (segmentacao
livre/direcionado, PF/PJ). Pedir `HISTORY_START` (2010-01-01) para essas
series e seguro: a API simplesmente devolve dados a partir de 03/2011, sem erro.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from core.config import DATA_DIR, HISTORY_START
from market_data.download import _bcb_fetch  # reaproveita paginacao + UA "curl/8.0"


# Codigos SGS confirmados em 2026-08-18 (ver docstring do modulo). Fonte oficial
# de cada descricao: catalogo de series do Banco Central
# (https://dadosabertos.bcb.gov.br/dataset/<codigo>-...).
BANK_MACRO_SERIES: dict[str, dict] = {
    "inadimplencia_pf": {
        "code": 21084,
        "desc": "Inadimplencia da carteira de credito - Pessoas fisicas - Total "
                "(% da carteira com atraso > 90 dias). Mensal.",
    },
    "inadimplencia_pj": {
        "code": 21083,
        "desc": "Inadimplencia da carteira de credito - Pessoas juridicas - Total "
                "(% da carteira com atraso > 90 dias). Mensal.",
    },
    "concessoes_credito": {
        "code": 20631,
        "desc": "Concessoes de credito - Total (PF + PJ, recursos livres + "
                "direcionados). R$ milhoes/mes, novas operacoes contratadas no periodo.",
    },
    "spread_bancario": {
        "code": 20783,
        "desc": "Spread medio das operacoes de credito - Total. Diferenca entre a "
                "taxa media de juros das novas operacoes e o custo medio de captacao. % a.a.",
    },
    "saldo_credito_sfn": {
        "code": 20539,
        "desc": "Saldo da carteira de credito - Total (Sistema Financeiro Nacional, "
                "recursos livres + direcionados). R$ milhoes, saldo em final de periodo.",
    },
    "taxa_juros_credito": {
        "code": 20714,
        "desc": "Taxa media de juros das operacoes de credito - Total (PF + PJ, "
                "recursos livres + direcionados). % a.a.",
    },
}


def download_bank_macro(
    series: dict[str, dict] = BANK_MACRO_SERIES,
    start: str = HISTORY_START,
    out_dir: Path = DATA_DIR,
) -> dict[str, Path]:
    """Baixa as series macro bancarias do BCB SGS ate hoje.

    Idempotente: reescreve o parquet a cada rodada. Se a API falhar para uma
    serie, preserva o parquet local existente (mesmo padrao de
    `market_data.download.download_macro`) em vez de zerar dado valido.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y-%m-%d")
    written: dict[str, Path] = {}
    for name, meta in series.items():
        path = out_dir / f"{name}.parquet"
        try:
            df = _bcb_fetch(meta["code"], start=start, end=today)
        except Exception as e:  # urllib.error.URLError, TimeoutError, RuntimeError
            if path.exists():
                print(f"[bank_macro] {name} (sgs.{meta['code']}): falha na API ({e}); "
                      f"mantendo parquet local")
            else:
                print(f"[bank_macro] {name} (sgs.{meta['code']}): falha na API ({e}); "
                      f"sem parquet local")
            continue
        df.to_parquet(path)
        written[name] = path
    return written


def _print_summary(series: dict[str, dict], written: dict[str, Path]) -> None:
    print(f"\n{'='*78}\n  RESUMO — macro bancario BCB SGS ({len(written)}/{len(series)} series)\n{'='*78}")
    for name, meta in series.items():
        path = written.get(name)
        if path is None:
            print(f"\n[FALHOU] {name} (sgs.{meta['code']}) — {meta['desc']}")
            continue
        df = pd.read_parquet(path)
        df = df.sort_index()
        start_d = df.index.min().date()
        end_d = df.index.max().date()
        last3 = df["valor"].tail(3)
        vals = ", ".join(f"{idx.date()}={v:.4f}" for idx, v in last3.items())
        print(f"\n[OK] {name}  (sgs.{meta['code']})")
        print(f"     {meta['desc']}")
        print(f"     periodo: {start_d} -> {end_d}  ({len(df)} pontos)")
        print(f"     ultimos 3 valores: {vals}")
    print(f"\n{'='*78}\n")


def main() -> None:
    print(f"\n{'='*78}\n  DOWNLOAD — macro/setorial bancario BCB SGS "
          f"({len(BANK_MACRO_SERIES)} series, desde {HISTORY_START})\n{'='*78}")
    written = download_bank_macro()
    _print_summary(BANK_MACRO_SERIES, written)


if __name__ == "__main__":
    main()
