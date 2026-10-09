"""Ciclo 3, dia 2024-10-25 (WIN, ruim, rotacao, ef 0,071; robo v3 = v2 = v1 = -R$40,32, 2 operacoes).

O DIA: abre 132.300 (gap de +100 sobre o fecho de ontem, 132.200, que fechou na maxima), faixa 131.510-132.360 (850 pts = 0,51 ATRd),
fecha 131.575. O robo vendeu a F2 matinal as 10:00 (alvo em 22 min, +R$47,58) e depois o `venda pullback EMA20 em baixa` as 13:30
(131.735, stop 132.164): a vela das 13:15 tinha feito a minima do dia (131.530) e fechado a 98% da faixa; a vela seguinte subiu 370 pts
e bateu o stop (-R$87,89). Das 12:45 as 13:15 ha 'FAZER nos dois lados: nao entra' (venda x `faixa_tarde` compra), que travou
a venda de continuacao que ganharia (a queda 12:30-13:15, depois nova minima as 14:30).

Contem (uso: `python -m regras.c3_2024_10_25 conj`): propostas BF* (FAZER), BN* (NAO_FAZER), mais as do grupo (G*), em
`c3_grupo_2024_09_05` (que traz o motor de avaliacao nos 70 dias). Nada existente e editado.
"""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from regras import c3_grupo_2024_09_05 as G
from regras.c3_grupo_2024_09_05 import _hm, _ord, _efic, _vwap, TETO

DIA = "2024-10-25"
PULLBACKS = ("2022_11_16:venda pullback EMA20 em baixa", "2025_06_04:F3 recuo na media em tendencia de baixa")


def _ema(s, n): return s.ewm(span=n, adjust=False).mean()


# =====================================================================================================  FAZER
def bf1_vende_topo_da_faixa_em_rotacao(ctx):
    """FAZER (fade de extremo da faixa, so com rotacao). A partir da 8a vela e ate 14:00: faixa do dia < 1,0 ATRd e >= 1,5 ATR15, eficiencia do
    dia ate agora <= 0,15 e o fecho nos 25% superiores da faixa -> vende no fecho, stop 0,3 ATR15 acima da maxima do dia (teto 590), alvo na
    MINIMA do dia (o outro extremo). Logica: em rotacao o topo da faixa devolve. Em 10-25 pega o topo das 11:15 (132.205) -> alvo 131.655."""
    h = ctx.hoje
    if len(h) < 8 or _hm(ctx) > 14 * 60: return None
    hi, lo, c = float(h.high.max()), float(h.low.min()), float(h.close.iloc[-1]); rng = hi - lo
    if rng < ctx.atrd and rng >= 1.5 * ctx.atr15 and _efic(ctx) <= 0.15 and hi - c <= 0.25 * rng:
        return _ord(ctx, "venda", hi + 0.3 * ctx.atr15 - c, alvo=lo)


def bf1m_compra_fundo_da_faixa_em_rotacao(ctx):
    """FAZER (espelho de BF1, definido sem olhar resultado): compra o fundo da faixa em rotacao, alvo na MAXIMA do dia."""
    h = ctx.hoje
    if len(h) < 8 or _hm(ctx) > 14 * 60: return None
    hi, lo, c = float(h.high.max()), float(h.low.min()), float(h.close.iloc[-1]); rng = hi - lo
    if rng < ctx.atrd and rng >= 1.5 * ctx.atr15 and _efic(ctx) <= 0.15 and c - lo <= 0.25 * rng:
        return _ord(ctx, "compra", c - (lo - 0.3 * ctx.atr15), alvo=hi)


def bf2_compra_rejeicao_de_minima_alvo_vwap(ctx):
    """FAZER (reversao a media). Vela que fez a minima do dia e fechou no terco superior, com o fecho >= 0,75 ATR15 ABAIXO do VWAP: compra,
    stop 0,3 ATR15 abaixo da minima (teto 590), alvo no VWAP. Em 10-25 13:30 (fecho 131.735, VWAP ~131.95): +. Natureza: reversao a media."""
    h = ctx.hoje
    if len(h) < 6 or not (10 * 60 + 30 <= _hm(ctx) <= 15 * 60): return None
    if not G.rej_minima(ctx, nb=1): return None
    u = h.iloc[-1]; c = float(u.close); v = _vwap(h)
    if v - c >= 0.75 * ctx.atr15:
        return _ord(ctx, "compra", c - (float(u.low) - 0.3 * ctx.atr15), alvo=v)


def bf3_venda_rompe_minima_da_faixa_do_almoco(ctx):
    """FAZER (continuacao, saida da lateral). Entre 12:30 e 15:00, fecho abaixo da minima das ultimas 8 velas (excluindo a atual) com
    volume >= 0,8 do medio e fecho abaixo do VWAP: vende no fecho, stop 1,2 ATR15 (teto 590), alvo 2R. Natureza: rompimento de lateral a
    favor do lado que ja negocia abaixo do VWAP (em 10-25 12:45, fecho 131.665 sob a minima 131.700 das velas anteriores)."""
    h = ctx.hoje
    if len(h) < 10 or not (12 * 60 + 30 <= _hm(ctx) <= 15 * 60): return None
    u = h.iloc[-1]; c = float(u.close); prev = h.iloc[-9:-1]
    if c < float(prev.low.min()) and u.vol >= 0.8 * h.vol.mean() and c < _vwap(h):
        return _ord(ctx, "venda", 1.2 * ctx.atr15, 2.0)


# =====================================================================================================  NAO_FAZER (filtros de regime sobre as FAZER)
def _wrap_nomes(pred_veta, nomes=None, natureza_in=None):
    def ap(cfg):
        import cfg3
        def mk(n, r):
            def w(ctx):
                s = r(ctx)
                if s and "erro" not in s and pred_veta(ctx): return None
                return s
            return w
        novo = []
        for n, r, g in cfg.fz:
            alvo = (nomes is not None and n in nomes) or (natureza_in is not None and cfg3.natureza(n) in natureza_in)
            novo.append((n, mk(n, r), g) if alvo else (n, r, g))
        cfg.fz = novo
    return ap


def _veta_continuacao_sem_tendencia(ctx):
    """Depois do meio-dia, o dia ate agora tem eficiencia < 0,12: nao ha perna a continuar."""
    return _hm(ctx) >= 12 * 60 and _efic(ctx) < 0.12


def _veta_pos_vitoria_em_rotacao(ctx):
    """Ja existe operacao do dia, a ultima foi vitoria, e a eficiencia do dia ate agora < 0,10."""
    o = ctx.ops_hoje
    return bool(o) and o[-1].brl > 0 and _efic(ctx) < 0.10


def _veta_pullback_ema_plana(ctx):
    """EMA20 M15 quase plana: inclinacao das ultimas 3 velas > -0,3 ATR15 (a 'tendencia de baixa' que o pullback exige nao existe)."""
    e = _ema(ctx.m15.close, 20)
    return float(e.iloc[-1] - e.iloc[-4]) > -0.3 * ctx.atr15


PROPS = {
    "BF1": ("FAZER", "vende o topo da faixa em rotacao (alvo = minima do dia)", G._add_fz("c3b:BF1", bf1_vende_topo_da_faixa_em_rotacao)),
    "BF1m": ("FAZER", "espelho: compra o fundo da faixa em rotacao", G._add_fz("c3b:BF1m", bf1m_compra_fundo_da_faixa_em_rotacao)),
    "BF2": ("FAZER", "compra rejeicao de minima abaixo do VWAP, alvo VWAP", G._add_fz("c3b:BF2", bf2_compra_rejeicao_de_minima_alvo_vwap)),
    "BF3": ("FAZER", "vende rompimento da minima da faixa do almoco sob o VWAP", G._add_fz("c3b:BF3", bf3_venda_rompe_minima_da_faixa_do_almoco)),
    "BN2": ("NAO_FAZER", "FAZER de continuacao nao vale apos 12:00 com eficiencia do dia < 0,12", _wrap_nomes(_veta_continuacao_sem_tendencia, natureza_in=("continuacao",))),
    "BN2b": ("NAO_FAZER", "idem, tambem para rompimento", _wrap_nomes(_veta_continuacao_sem_tendencia, natureza_in=("continuacao", "rompimento"))),
    "BN3": ("NAO_FAZER", "apos vitoria matinal em rotacao (ef < 0,10) nao opera mais", _wrap_nomes(_veta_pos_vitoria_em_rotacao, natureza_in=("continuacao", "rompimento", "reversao", "outra"))),
    "BN4": ("NAO_FAZER", "pullback na EMA20 so com EMA inclinada (>= 0,3 ATR15 em 3 velas)", _wrap_nomes(_veta_pullback_ema_plana, nomes=PULLBACKS)),
}
G.REG.update(PROPS)
MODULOS = ("regras.c3_grupo_2024_09_05", "regras.c3_2024_09_05", "regras.c3_2024_10_25")
LISTA = ["BF1", "BF1m", "BF2", "BF3", "G2m", "BN2", "BN2b", "BN3", "BN4", "G1", "G5", "G3a", "G3d", "G4"]

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "conj":
        G.imprime(f"DIA {DIA}", [(k,) for k in LISTA], MODULOS, ("2024-09-05", "2024-10-25"))
