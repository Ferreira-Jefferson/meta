"""Acompanhamento da escada v4.1: o resultado recente está dentro do que o histórico congelado prevê?

Separa AZAR NORMAL de PROBLEMA. Referência = operações da v4.1 no IS + OOS congelados (estrategia.rodar), em pts
por contrato já com o custo. Duas séries recentes são comparadas com ela:

  backtest  a v4.1 rodada nos dados recentes (base versionada + pregão de hoje até a última M15 fechada, montada
            como o OOS: desde 2025-10-01). Mede se a ESTRATÉGIA mudou de comportamento (regime).
  real      os negócios do EA na conta do MT5 com o magic da escada (avulso ou robô ES do WinMaestro). Mede se a
            EXECUÇÃO acompanha o backtest. Convertido para pts por contrato (R$ / 0,20 / contratos).

Regras (congeladas em 2026-10-09, pedido do dono):
  - Resultado de k operações seguidas: percentil contra TODAS as sequências de k operações seguidas da
    referência. < p25 = atenção; < p5 = ALERTA -- só com >= 10 operações (ajuste de 2026-10-09, antes de qualquer
    uso: com 1-3 operações o percentil é o tamanho de UMA perda, e um alarme de 5% consultado toda semana dispara à toa).
  - Acerto: só com >= 30 operações; binomial unilateral contra o acerto da referência; p < 0,05 = ALERTA.
  - Mês: cada mês abaixo do p5 dos meses da referência é marcado; 2 meses seguidos assim = ALERTA FORTE.
Um mês ruim isolado (~1 em 20) é esperado; o que importa é a persistência.

Uso: python scripts/daytrade/topos_fundos/acompanhamento.py [--desde 2026-10-01] [--sem-real]
"""
import argparse
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI)); sys.path.insert(0, str(AQUI.parent))
import dados  # noqa: E402
import escada  # noqa: E402
import estrategia  # noqa: E402
import indicadores as ind  # noqa: E402
import operacao  # noqa: E402
import stop  # noqa: E402

MAGIC = 41041015
REAIS_POR_PONTO = 0.20
MIN_OPS_ACERTO = 30
MIN_OPS_RESULTADO = 10      # abaixo disso o percentil mede o tamanho de uma perda isolada, não a estratégia


# ------------------------------------------------------------------ séries
def referencia():
    """Operações da v4.1 congelada (IS + OOS), em ordem: dia, liq (pts/contrato)."""
    tr = pd.concat([estrategia.rodar(p) for p in ("IS", "OOS")])
    return pd.DataFrame({"dia": tr.dia.values, "liq": (tr.mov - operacao.CUSTO).values})


def backtest_recente():
    """v4.1 nos dados desde 2025-10-01 até agora (base + hoje até a última M15 fechada, se o MT5 estiver aberto)."""
    m1 = dados.le_win(dados.RAIZ / dados.PERIODOS["OOS"][0])[["open", "high", "low", "close", "real_volume"]]
    agora = pd.Timestamp(datetime.now())
    try:
        import MetaTrader5 as mt5
        sys.path.insert(0, str(AQUI.parent))
        import atualiza_bases_mt5 as A
        if mt5.initialize() and mt5.symbol_select("WIN$N", True):
            hoje = date.today()
            raw = A.m1_do_dia("WIN$N", hoje)
            raw = raw[(raw.index + pd.Timedelta("1min") <= agora) & (raw.index >= pd.Timestamp(hoje) + pd.Timedelta(hours=9))]
            if len(raw) and raw.index[0].normalize() > m1.index.max().normalize():
                f = A.fases_do_dia(hoje, raw, A.fim_continuo(pd.Timestamp(hoje), A.carrega_grade(A.GRADE)))
                if f and f["pregao_preco_inicio"]:
                    raw.iloc[0, raw.columns.get_loc("open")] = f["pregao_preco_inicio"]   # abertura sem o leilão
                m1 = pd.concat([m1, raw[m1.columns]])
    except ImportError:
        pass
    m1 = m1[m1.index >= dados.PERIODOS["OOS"][1]]
    b = m1.resample("15min").agg(dict(open="first", high="max", low="min", close="last", real_volume="sum")).dropna()
    b = b[b.index <= agora.floor("15min") - pd.Timedelta("15min")]
    b["dia"] = b.index.normalize()
    b["contrato"] = np.searchsorted(dados.vencimentos(), b.dia.values, side="right")
    b["atr"] = dados.atr(b); b["mme38"] = ind.mme(b.close, stop.MME_APERTO)
    dias = escada.pregoes(b); s = escada.sinais(dias)
    ok = np.ones(len(s), bool)
    for f in estrategia.FILTROS:
        ok &= np.asarray(f(b, s))
    tr = operacao.operar(s[ok].sort_values(["seg", "t0"]).reset_index(drop=True), dias, stop.inicial_v41, stop.estrutura)
    return pd.DataFrame({"dia": tr.dia.values, "liq": (tr.mov - operacao.CUSTO).values}), b.index.max()


def real(desde):
    """Operações do EA na conta (magic da escada): resultado por posição, em pts por contrato."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return None, "MetaTrader5 não instalado"
    if not mt5.initialize():
        return None, "MT5 fechado"
    conta = mt5.account_info()
    deals = mt5.history_deals_get(datetime.combine(desde, datetime.min.time()), datetime.now() + pd.Timedelta(days=1)) or ()
    linhas = {}
    for d in deals:
        if d.magic != MAGIC and d.position_id not in linhas: continue
        r = linhas.setdefault(d.position_id, dict(dia=None, rs=0.0, vol=0.0, fechou=False))
        r["rs"] += d.profit + d.commission + d.fee + d.swap
        if d.entry == 0:
            r["dia"] = pd.Timestamp(datetime.fromtimestamp(d.time, timezone.utc).replace(tzinfo=None)).normalize(); r["vol"] += d.volume
        elif d.entry in (1, 2, 3):
            r["fechou"] = True
    ops = [dict(dia=r["dia"], liq=r["rs"] / REAIS_POR_PONTO / r["vol"]) for r in linhas.values() if r["fechou"] and r["dia"] is not None and r["vol"]]
    rotulo = f"conta {conta.login} {conta.server}" if conta else "conta ?"
    return pd.DataFrame(ops, columns=["dia", "liq"]).sort_values("dia"), rotulo


# ------------------------------------------------------------------ comparação
def percentil_k(ref, k, soma):
    """Fração das sequências de k operações seguidas da referência com resultado <= soma."""
    if k == 0: return np.nan
    janelas = np.convolve(ref, np.ones(k), "valid")
    return (janelas <= soma + 1e-9).mean(), np.percentile(janelas, [5, 25, 50, 75, 95])


def binom_cdf(k, n, p):
    return sum(math.comb(n, i) * p**i * (1 - p)**(n - i) for i in range(k + 1))


def nivel(p):
    return "ALERTA" if p < 0.05 else ("atenção" if p < 0.25 else "normal")


def avalia(nome, ops, ref, ref_meses):
    print(f"\n== {nome}")
    if ops is None or not len(ops):
        print("   sem operações no período"); return
    x = ops.liq.to_numpy(); k = len(x)
    p, faixa = percentil_k(ref.liq.to_numpy(), k, x.sum())
    print(f"   operações: {k} | resultado {x.sum():+.0f} pts = R$ {x.sum()*REAIS_POR_PONTO:+.2f} por contrato")
    print(f"   referência p/ {k} operações seguidas: p5 {faixa[0]:+.0f} | p25 {faixa[1]:+.0f} | mediana {faixa[2]:+.0f} | p75 {faixa[3]:+.0f} | p95 {faixa[4]:+.0f}")
    print(f"   resultado no percentil {p:.0%} -> " + (nivel(p) if k >= MIN_OPS_RESULTADO else f"amostra pequena (veredito a partir de {MIN_OPS_RESULTADO} operações)"))
    acerto_ref = (ref.liq > 0).mean(); ganhos = int((x > 0).sum())
    if k >= MIN_OPS_ACERTO:
        pb = binom_cdf(ganhos, k, acerto_ref)
        print(f"   acerto {ganhos}/{k} = {ganhos/k:.0%} (referência {acerto_ref:.0%}), p = {pb:.3f} -> {'ALERTA' if pb < 0.05 else 'normal'}")
    else:
        print(f"   acerto {ganhos}/{k} = {ganhos/k:.0%} (referência {acerto_ref:.0%}); só é julgado a partir de {MIN_OPS_ACERTO} operações")
    mes = ops.assign(m=pd.to_datetime(ops.dia).dt.to_period("M")).groupby("m").liq.sum()
    p5m = ref_meses.quantile(0.05)
    ruins = [str(m) for m, v in mes.items() if v < p5m]
    seguidos = any((mes.index[i] - mes.index[i - 1]).n == 1 and mes.iloc[i] < p5m and mes.iloc[i - 1] < p5m for i in range(1, len(mes)))
    print(f"   meses (p5 da referência {p5m:+.0f} pts): " + ", ".join(f"{m} {v:+.0f}" for m, v in mes.items())
          + (f" | abaixo do p5: {', '.join(ruins)}" if ruins else "") + (" -> ALERTA FORTE (2 meses seguidos)" if seguidos else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", default=date.today().replace(day=1).isoformat())
    ap.add_argument("--sem-real", action="store_true")
    a = ap.parse_args()
    desde = date.fromisoformat(a.desde)
    ref = referencia()
    ref = ref[pd.to_datetime(ref.dia) < pd.Timestamp(desde)]          # não compara o período com ele mesmo
    ref_meses = ref.assign(m=pd.to_datetime(ref.dia).dt.to_period("M")).groupby("m").liq.sum()
    print(f"Referência: v4.1 congelada IS+OOS, {len(ref)} operações, acerto {(ref.liq > 0).mean():.1%}, "
          f"{ref.liq.mean():+.1f} pts/op, meses negativos {(ref_meses < 0).mean():.0%}")
    print(f"Período acompanhado: desde {desde:%d/%m/%Y}")
    bt, ate = backtest_recente()
    avalia(f"BACKTEST nos dados recentes (até {ate:%d/%m %H:%M})", bt[pd.to_datetime(bt.dia) >= pd.Timestamp(desde)], ref, ref_meses)
    if not a.sem_real:
        ops, rotulo = real(desde)
        avalia(f"REAL ({rotulo}, magic {MAGIC})", ops, ref, ref_meses)


if __name__ == "__main__":
    main()
