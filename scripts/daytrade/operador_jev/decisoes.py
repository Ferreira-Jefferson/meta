"""Conversao das respostas do Jev (endpoint de decisoes) em ordens do motor. Funcoes puras: sem rede, sem I/O.

Sem posicao: choice `acao` {comprar, vender, fora}; entra so se a escolha for comprar/vender E P(escolha) >= limiar.
  stop  {0.5atr, 1atr, 1.5atr, pivo}  alvo {sem_alvo, 1atr, 2atr, 3atr}  mao {1, 2}
  entrada = limite no ultimo fechamento (arredondado para o lado passivo), validade 3 velas.
  "sem_alvo" = deixar correr: stop movel na minima (compra) / maxima (venda) das ultimas 8 velas M15, so a favor.
Com posicao: choice `g_acao` {manter, stop_pivo, zerar}; o stop movel de "deixar correr" roda mesmo sem resposta.
So velas FECHADAS (indice <= k) entram em qualquer calculo: sem look-ahead.
"""
from __future__ import annotations
import numpy as np
from motor import arredonda, TICK, MAX_CONTRATOS

VALIDADE_VELAS = 3
TRAIL_VELAS = 8
FATOR_STOP = {"0.5atr": 0.5, "1atr": 1.0, "1.5atr": 1.5}
FATOR_ALVO = {"1atr": 1.0, "2atr": 2.0, "3atr": 3.0}
STOP_PADRAO = 1.5          # ATR: usado quando o pivo nao existe/e inviavel
PIVO_MIN_ATR, PIVO_MAX_ATR = 0.3, 4.0
JANELA_PIVO = 60


class Ctx:
    """Arrays globais do M15 (ordenados no tempo) para pivos, ATR e trailing."""

    def __init__(self, mk):
        m = mk.m15
        self.T = m.index.values
        self.H = m.high.to_numpy(float)
        self.L = m.low.to_numpy(float)
        self.C = m.close.to_numpy(float)
        self.ATR = m.atr_m15.to_numpy(float)

    def g(self, dia, k):
        return int(np.searchsorted(self.T, dia.m15_t[k]))


def _tick_baixo(x):
    return np.floor(x / TICK + 1e-9) * TICK


def _tick_alto(x):
    return np.ceil(x / TICK - 1e-9) * TICK


def pivo_recente(ctx: Ctx, g: int, dirn: int, apos=None, ref=None, minimo=None, maximo=None, gmin=None):
    """Ultimo pivo (fractal de 2 velas de cada lado) JA CONFIRMADO em g (indice <= g-2).
    dirn=+1: fundo (compra); -1: topo (venda). Devolve (indice, valor) do mais recente que satisfaz
    minimo < valor < maximo (limites no proprio eixo de preco), ou None."""
    arr = ctx.L if dirn > 0 else ctx.H
    for i in range(g - 2, max(2, g - JANELA_PIVO) - 1, -1):
        if gmin is not None and i < gmin:
            break
        v = arr[i]
        viz = (arr[i - 1], arr[i - 2], arr[i + 1], arr[i + 2])
        ok = all(v < x for x in viz) if dirn > 0 else all(v > x for x in viz)
        if not ok:
            continue
        if minimo is not None and not v > minimo:
            continue
        if maximo is not None and not v < maximo:
            continue
        return i, float(v)
    return None


def nivel_trailing(ctx: Ctx, g: int, dirn: int):
    """Minima (compra) / maxima (venda) das ultimas TRAIL_VELAS velas fechadas (incluindo a que acabou de fechar)."""
    a = max(0, g - TRAIL_VELAS + 1)
    return float(ctx.L[a:g + 1].min()) if dirn > 0 else float(ctx.H[a:g + 1].max())


def escolha(resp, qid, padrao=None):
    r = (resp or {}).get(qid)
    if isinstance(r, dict):
        return r.get("c", padrao), r.get("p", {})
    return padrao, {}


def decisao_entrada(rm, ctx: Ctx, dia, k: int, limiar: float, modo: str = "argmax"):
    """(dec, info). dec no formato do motor; info = o que o Jev escolheu (para log/diagnostico)."""
    esc, pr = escolha(rm, "acao")
    if modo == "lado" and pr:            # ignora 'fora': compara so comprar x vender (descritivo, p/ limiares baixos)
        esc = "comprar" if pr.get("comprar", 0.0) >= pr.get("vender", 0.0) else "vender"
    p = float(pr.get(esc, 0.0)) if esc else 0.0
    info = dict(esc=esc, p=p, p_comprar=float(pr.get("comprar", 0.0)), p_vender=float(pr.get("vender", 0.0)),
                p_fora=float(pr.get("fora", 0.0)))
    if esc not in ("comprar", "vender") or p < limiar:
        return dict(acao="ficar_fora", confianca=round(100 * p), respostas=[],
                    raciocinio=f"Jev: acao={esc} (p={p:.2f}) -> {'abaixo do limiar ' + str(limiar) if esc in ('comprar', 'vender') else 'fora'}"), info
    dirn = 1 if esc == "comprar" else -1
    g = ctx.g(dia, k)
    last, atr = float(ctx.C[g]), float(ctx.ATR[g])
    preco = float(_tick_baixo(last) if dirn > 0 else _tick_alto(last))
    s_esc, _ = escolha(rm, "stop", "1.5atr")
    a_esc, _ = escolha(rm, "alvo", "sem_alvo")
    m_esc, _ = escolha(rm, "mao", "1")
    modo_stop = s_esc
    stop = None
    if s_esc == "pivo":
        if dirn > 0:
            pv = pivo_recente(ctx, g, 1, maximo=preco - PIVO_MIN_ATR * atr, minimo=preco - PIVO_MAX_ATR * atr)
            stop = None if pv is None else pv[1] - TICK
        else:
            pv = pivo_recente(ctx, g, -1, minimo=preco + PIVO_MIN_ATR * atr, maximo=preco + PIVO_MAX_ATR * atr)
            stop = None if pv is None else pv[1] + TICK
        if stop is None:
            modo_stop = "pivo->1.5atr"
    if stop is None:
        f = FATOR_STOP.get(s_esc, STOP_PADRAO)
        stop = preco - dirn * f * atr
    stop = arredonda(stop)
    if (stop - preco) * dirn >= 0:           # protecao: stop sempre do lado certo e >= 1 tick
        stop = preco - dirn * TICK
    alvo = None
    if a_esc in FATOR_ALVO:
        alvo = arredonda(preco + dirn * FATOR_ALVO[a_esc] * atr)
        if (alvo - preco) * dirn <= 0:
            alvo = preco + dirn * TICK
    n = max(1, min(MAX_CONTRATOS, int(m_esc) if str(m_esc).isdigit() else 1))
    info.update(modo_stop=modo_stop, alvo_modo=a_esc, mao=n, preco=preco, stop=stop, alvo=alvo, atr=atr)
    dec = dict(acao="comprar_limite" if dirn > 0 else "vender_limite", preco=preco, stop=stop, alvo=alvo, contratos=n,
               validade_velas=VALIDADE_VELAS, trail=alvo is None, confianca=round(100 * p), respostas=[],
               raciocinio=f"Jev: {esc} p={p:.2f} | stop {modo_stop} ({stop:.0f}) | alvo {a_esc} | mao {n}")
    return dec, info


def decisao_gestao(rg, ctx: Ctx, dia, k: int, pos: dict):
    """(dec, info) com posicao aberta. Aplica o stop movel de 'deixar correr' e/ou o pivo escolhido (so a favor)."""
    g = ctx.g(dia, k)
    last = float(ctx.C[g])
    dirn = pos["dir"]
    esc, pr = escolha(rg, "g_acao", "manter")
    info = dict(esc=esc, p=float(pr.get(esc, 0.0)) if esc else 0.0)
    if esc == "zerar":
        return dict(acao="zerar", confianca=round(100 * info["p"]), respostas=[], raciocinio="Jev: zerar"), info
    cand = []
    if pos.get("trail"):
        cand.append(("trail", nivel_trailing(ctx, g, dirn)))
    if esc == "stop_pivo":
        # pivo formado desde a entrada, estritamente entre o stop atual e o ultimo fechamento
        pv = pivo_recente(ctx, g, dirn, gmin=ctx.g(dia, pos["k_ent"]),
                          minimo=pos["stop"] if dirn > 0 else last, maximo=last if dirn > 0 else pos["stop"])
        if pv is not None:
            cand.append(("pivo", pv[1] - dirn * TICK))
    validos = []
    for nome, v in cand:
        v = arredonda(v)
        if (dirn > 0 and pos["stop"] < v < last) or (dirn < 0 and last < v < pos["stop"]):
            validos.append((nome, v))
    if not validos:
        return dict(acao="manter", confianca=round(100 * info["p"]), respostas=[], raciocinio=f"Jev: {esc}"), info
    nome, v = (max if dirn > 0 else min)(validos, key=lambda x: x[1])
    info["stop_mov"] = nome
    return dict(acao="mover_stop", novo_stop=v, confianca=round(100 * info["p"]), respostas=[],
                raciocinio=f"Jev: {esc}; stop -> {v:.0f} ({nome})"), info


def decide_vela(ctx: Ctx, dia, k: int, s, rm, rg, limiar: float, modo: str = "argmax"):
    """Decisao completa na vela k. s = Sessao (le pos/pend). rm/rg = respostas compactas (ou None)."""
    if s.pos:
        dec, info = decisao_gestao(rg, ctx, dia, k, s.pos)
        info["fase"] = "gestao"
        return dec, info
    if s.pend:
        return dict(acao="manter", confianca=0, respostas=[], raciocinio="ordem pendente: aguarda"), dict(fase="pendente")
    if not rm:
        return dict(acao="ficar_fora", confianca=0, respostas=[], raciocinio="(sem resposta do Jev)"), dict(fase="falha")
    dec, info = decisao_entrada(rm, ctx, dia, k, limiar, modo)
    info["fase"] = "entrada"
    return dec, info


def ks_decisao(dia, hora_ini="09:15", hora_fim="17:30"):
    """Velas em que o motor pede decisao (mesma regra de motor.run_dia)."""
    from motor import _hm
    out = []
    n = len(dia.m15_t)
    for k in range(n):
        t_fech = _hm(dia.m15_t[k] + np.timedelta64(15, "m"))
        if not (hora_ini <= t_fech <= hora_fim):
            continue
        if int(dia.m1_fim[k]) > dia.flat_i + 1 or k == n - 1:
            continue
        out.append(k)
    return out


def resimula_dia(mk, ctx: Ctx, dia, sess: dict, limiar: float, hora_ini="09:15", hora_fim="17:30", modo: str = "argmax"):
    """Re-roda um dia COM AS RESPOSTAS JA LOGADAS (sem rede) a outro limiar. Aproximacao: as respostas de mercado nao dependem
    da posicao (o estado nao a inclui), entao a entrada e exata; a gestao so existe nas velas em que a posicao ORIGINAL estava
    aberta - em velas com posicao so na nova trajetoria vale 'manter' (+ stop movel de deixar correr)."""
    from motor import run_dia
    M = {p["k"]: p["jev"].get("m") for p in sess["pontos"]}
    G = {p["k"]: p["jev"].get("g") for p in sess["pontos"]}

    def decidir(pf, k, s):
        dec, info = decide_vela(ctx, dia, k, s, M.get(k), G.get(k), limiar, modo)
        return dec, dict(info=info)
    s, _ = run_dia(mk, dia, decidir, hora_ini, hora_fim)
    return s
