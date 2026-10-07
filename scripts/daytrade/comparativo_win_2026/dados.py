"""Base comum do comparativo WIN 2026 -- o que o Testador do MT5 entregaria a cada EA.

Fonte: WIN$N (preco cru do contrato principal), baixado por `baixa_dados.py`.
  - `m1()`: barras M1 de 2025-10-01 a 2026-10-05 (a folga de 2025 aquece medias/ATR, como o historico que o
    Testador carrega antes da data inicial).
  - `ticks(dia)`: ticks do pregao. De 2026-02-20 em diante sao os ticks REAIS da corretora (so' `last`; o WIN$N
    nao traz bid/ask, entao bid = ask = last). Antes disso a corretora nao tem tick: geramos 4 ticks por M1 no
    padrao do Testador ("todos os ticks" gerado de M1): abertura, extremo mais proximo, outro extremo, fechamento.

Regras de execucao do Testador que todo port deve seguir (as mesmas do MT5 com simbolo de bolsa):
  - ordem a mercado executa no `last` do tick em que foi enviada (nao ha spread: bid = ask = last);
  - stop (SL ou ordem stop) dispara quando o `last` toca/atravessa o nivel e executa no `last` desse tick
    (gap -> sai pior que o nivel);
  - limite (TP, BuyLimit/SellLimit) enche quando o `last` toca o nivel e executa NO PRECO DO LIMITE
    (se o tick ja' abre alem do limite, executa no limite -- o Testador nao da' melhora de preco);
  - tudo no horario do servidor (o mesmo das barras).
"""
from datetime import date
from functools import lru_cache
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DADOS = ROOT / "data" / "comparativo_win_2026"
INICIO, FIM = date(2026, 1, 1), date(2026, 10, 5)
TICK = 5.0       # tick do WIN, pontos
RS_PONTO = 0.20  # R$ por ponto por contrato
CAPITAL = 1000.0


@lru_cache(maxsize=1)
def m1() -> pd.DataFrame:
    """M1 do WIN$N: index = abertura da barra (servidor); open/high/low/close/tick_volume/real_volume."""
    return pd.read_parquet(DADOS / "m1_WIN$N.parquet")


def dias() -> list:
    """Pregoes de 2026 dentro do periodo do comparativo."""
    return sorted(d for d in set(m1().index.date) if INICIO <= d <= FIM)


def _sinteticos(barras: pd.DataFrame):
    o, h, l, c = (barras[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    v = barras.real_volume.to_numpy(np.int64)
    t0 = barras.index.values.astype("datetime64[ms]").astype(np.int64)
    alta = c >= o
    p = np.stack([o, np.where(alta, l, h), np.where(alta, h, l), c], axis=1).ravel()
    t = np.stack([t0, t0 + 15000, t0 + 30000, t0 + 59000], axis=1).ravel()
    vv = np.stack([v // 4, v // 4, v // 4, v - 3 * (v // 4)], axis=1).ravel()
    return t, p, vv


def ticks(dia: date):
    """(t_ms, last, volume, real) do pregao. t_ms = epoch em ms no horario do servidor (como as barras)."""
    arq = DADOS / "ticks" / f"{dia}.npz"
    if arq.exists():
        z = np.load(arq)
        return z["t"], z["p"].astype(float), z["v"], True
    b = m1()
    t, p, v = _sinteticos(b[b.index.date == dia])
    return t, p, v, False


def ms(ts) -> int:
    """pd.Timestamp/datetime -> epoch ms (mesma escala dos ticks)."""
    return int(pd.Timestamp(ts).value // 10**6)


def ts(t_ms: int) -> pd.Timestamp:
    return pd.Timestamp(int(t_ms), unit="ms")


# Esquema de saida de todo port: uma linha por operacao FECHADA, em ordem de saida.
COLUNAS = ["estrategia", "entrada", "saida", "lado", "qtd", "preco_entrada", "preco_saida", "motivo", "pontos", "rs"]


def trade(estrategia, t_ent, t_sai, lado, qtd, pe, px, motivo) -> dict:
    pts = lado * (px - pe)
    return dict(estrategia=estrategia, entrada=str(ts(t_ent)), saida=str(ts(t_sai)), lado=int(lado), qtd=float(qtd),
                preco_entrada=float(pe), preco_saida=float(px), motivo=motivo, pontos=float(pts),
                rs=round(float(pts * RS_PONTO * qtd), 2))


def salvar(estrategia: str, trades: list) -> Path:
    out = Path(__file__).resolve().parent / "resultados" / f"{estrategia}.csv"
    out.parent.mkdir(exist_ok=True)
    pd.DataFrame(trades, columns=COLUNAS).to_csv(out, index=False)
    return out
