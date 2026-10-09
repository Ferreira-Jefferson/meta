"""Regras DETERMINISTICAS da v4 (pre-registradas; funcoes puras, sem rede). Ver ../perguntas_v4.md.

1. Gestao: `manter` por padrao; `stop_pivo`/`zerar` so se a TESE foi invalidada = o preco FECHOU alem do ultimo swing contra a posicao.
2. Portao de direcao comprovada (sem posicao): eficiencia direcional do dia na vela de decisao >= LIMIAR_ER (0,20, fixado antes de rodar) E a entrada a favor
   do lado do dia (fechamento - abertura).
3. Risco vs caixa: perda do stop (distancia x R$0,20 x contratos) > 6% do caixa -> 1 contrato; com 1 contrato ainda > 6% -> nao entra.
4. Reentrada: apos operacao perdedora no dia so reentra se o portao continua valendo e passaram >= 2 velas desde a saida; maximo 3 operacoes por dia.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
PAI = Path(__file__).resolve().parents[2]
if str(PAI) not in sys.path:
    sys.path.insert(0, str(PAI))
from decisoes import pivo_recente, _tick_baixo, _tick_alto, FATOR_STOP, STOP_PADRAO, PIVO_MIN_ATR, PIVO_MAX_ATR  # noqa: E402
from motor import TICK, VALOR_PT, arredonda  # noqa: E402

LIMIAR_ER = 0.20
RISCO_MAX_PCT = 6.0
MAX_OPS_DIA = 3
MIN_VELAS_REENTRADA = 2
CAIXA_INI_DIA = 2000.0


def er_dia(dia, k):
    """(eficiencia direcional |fech-abertura|/soma das amplitudes M15, deslocamento fech-abertura) ate a vela k fechada. Igual ao DERIVADOS do pacote."""
    m = dia.m15[: k + 1]
    soma = float((m[:, 1] - m[:, 2]).sum())
    desl = float(m[-1, 3] - m[0, 0])
    return (abs(desl) / soma if soma > 0 else 0.0), desl


def portao(er, desl, dirn, limiar=LIMIAR_ER):
    """(ok, motivo). dirn=+1 compra / -1 venda. A favor = mesmo sinal do deslocamento (fech - abertura)."""
    if er < limiar:
        return False, f"portao: eficiencia {er:.2f} < {limiar:.2f}"
    if desl == 0 or (1 if desl > 0 else -1) != dirn:
        return False, f"portao: entrada {'compra' if dirn > 0 else 'venda'} contra o lado do dia ({desl:+.0f} pts da abertura)"
    return True, ""


def perda_stop_brl(preco, stop, n):
    return abs(preco - stop) * VALOR_PT * n


def risco(preco, stop, n, caixa, pct=RISCO_MAX_PCT):
    """(n_efetivo, motivo, perdas). n_efetivo = 0 -> nao entra. perdas = (perda_n_pedido, perda_1) em R$."""
    lim = caixa * pct / 100.0
    p_n, p_1 = perda_stop_brl(preco, stop, n), perda_stop_brl(preco, stop, 1)
    if p_n <= lim:
        return n, "", (p_n, p_1)
    if n > 1 and p_1 <= lim:
        return 1, f"risco: perda {p_n:.0f} > {pct:.0f}% do caixa ({lim:.0f}); mao {n}->1", (p_n, p_1)
    return 0, f"risco: perda com 1 contrato {p_1:.0f} > {pct:.0f}% do caixa ({lim:.0f})", (p_n, p_1)


def reentrada(trades, k, max_ops=MAX_OPS_DIA, min_velas=MIN_VELAS_REENTRADA):
    """(ok, motivo). trades = operacoes JA fechadas hoje (dicts com brl, k_sai, motivo). O portao e checado a parte (vale para toda entrada)."""
    if len(trades) >= max_ops:
        return False, f"reentrada: ja {len(trades)} operacoes hoje (maximo {max_ops})"
    if trades and trades[-1]["brl"] < 0 and k - trades[-1]["k_sai"] < min_velas:
        return False, f"reentrada: ultima operacao perdeu e faz {k - trades[-1]['k_sai']} vela(s) (< {min_velas})"
    return True, ""


def stop_opcoes(ctx, dia, k, dirn):
    """Preco de entrada (limite no ultimo fechamento) e stop de cada opcao da pergunta `stop` (mesma conta de decisoes.decisao_entrada)."""
    g = ctx.g(dia, k)
    last, atr = float(ctx.C[g]), float(ctx.ATR[g])
    preco = float(_tick_baixo(last) if dirn > 0 else _tick_alto(last))
    out = {}
    for nome, f in FATOR_STOP.items():
        out[nome] = _fix(preco, arredonda(preco - dirn * f * atr), dirn)
    if dirn > 0:
        pv = pivo_recente(ctx, g, 1, maximo=preco - PIVO_MIN_ATR * atr, minimo=preco - PIVO_MAX_ATR * atr)
        out["pivo"] = None if pv is None else _fix(preco, arredonda(pv[1] - TICK), dirn)
    else:
        pv = pivo_recente(ctx, g, -1, minimo=preco + PIVO_MIN_ATR * atr, maximo=preco + PIVO_MAX_ATR * atr)
        out["pivo"] = None if pv is None else _fix(preco, arredonda(pv[1] + TICK), dirn)
    return preco, out


def _fix(preco, stop, dirn):
    return stop if (stop - preco) * dirn < 0 else preco - dirn * TICK


def tese_invalidada(ctx, dia, k, pos):
    """(invalidada, info). Invalidada = algum fechamento M15 desde a entrada fechou alem do swing contra a posicao que valia NA ENTRADA, ou o fechamento atual
    esta alem do ultimo swing confirmado de agora. Swing = fractal de 2 velas de cada lado ja confirmado (mesmo do pacote), so de hoje.
    Compra: swing = fundo (invalida abaixo); venda: topo (invalida acima)."""
    dirn = pos["dir"]
    g = ctx.g(dia, k)
    g0 = ctx.g(dia, 0)
    g_ent = ctx.g(dia, pos["k_ent"])
    now = pivo_recente(ctx, g, dirn, gmin=g0)
    ent = pivo_recente(ctx, g_ent, dirn, gmin=g0)
    closes = ctx.C[g_ent: g + 1]
    quebra_now = bool(now is not None and (ctx.C[g] < now[1] if dirn > 0 else ctx.C[g] > now[1]))
    quebra_ent = bool(ent is not None and (closes.min() < ent[1] if dirn > 0 else closes.max() > ent[1]))
    info = dict(swing_agora=None if now is None else now[1], swing_na_entrada=None if ent is None else ent[1], fecha_atual=float(ctx.C[g]),
                quebra_agora=quebra_now, quebra_desde_entrada=quebra_ent)
    return quebra_now or quebra_ent, info
