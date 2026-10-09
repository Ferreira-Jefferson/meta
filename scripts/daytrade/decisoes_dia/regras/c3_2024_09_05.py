"""Ciclo 3, dia 2024-09-05 (WIN, ruim, rotacao, ef 0,044; robo v3 = v2 = v1 = -R$112,00, uma unica operacao).

O DIA: abre 137.850 (sem gap: fecho de ontem 137.980), depois de uma ALTA de 2.100 pts ontem que fechou a 82% da faixa. Faixa do dia toda
entre 137.270 e 138.340 (1.070 pts = 0,68 ATRd), fecha 138.265. O robo vendeu a F2 `falha da maxima matinal` as 10:00 no fecho da vela
que FEZ a minima do dia (137.270, pavio inferior de 90% da faixa), stop no teto de 550 pts (a maxima do dia estava 805 pts acima), alvo a
238 pts (payoff 0,43: precisaria acertar 70%). O preco devolveu e bateu o stop as 14:00 (-R$112).

Contem (uso: `python -m regras.c3_2024_09_05 conj`):
  FAZER (propostas AF*) / NAO_FAZER (AN*) / gestao (AG*)   -> registradas em c3_grupo_2024_09_05.REG
  as propostas comuns aos dois dias estao em `c3_grupo_2024_09_05` (G1..G5, G3a-d = conflito de lados, G4 = A2 condicional)
Nada em r_*.py, robo*.py ou ciclo3/ e editado.
"""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from regras import c3_grupo_2024_09_05 as G
from regras.c3_grupo_2024_09_05 import _hm, _ord, TETO

DIA = "2024-09-05"


# =====================================================================================================  FAZER
def af1_compra_recuo_apos_dia_altista(ctx):
    """FAZER (continuacao do dia anterior, entrada CEDO). Ontem subiu >= 0,8 ATRd e fechou nos 25% superiores da faixa; entre 09:30 e 10:30
    o preco recua >= 0,8 ATR15 abaixo da abertura de hoje -> compra no fecho, stop 0,3 ATR15 abaixo da minima do dia (teto 590), alvo 1,5R.
    Logica: a perna de ontem fechou forte e o recuo da manha e a oportunidade a favor dela; nao exige saber se hoje sera direcional.
    Ajustada ao dia? parcialmente: a ideia e geral, os limiares (0,8; 25%) foram vistos neste dia."""
    d = ctx.diario
    if len(d) < 2 or not (9 * 60 + 30 <= _hm(ctx) <= 10 * 60 + 30): return None
    y = d.iloc[-1]; rng = float(y.high - y.low)
    if rng <= 0: return None
    if (y.close - y.open) / ctx.atrd >= 0.8 and (y.close - y.low) / rng >= 0.75:
        h = ctx.hoje; c = float(h.close.iloc[-1])
        if c <= float(h.open.iloc[0]) - 0.8 * ctx.atr15:
            st = float(h.low.min()) - 0.3 * ctx.atr15
            return _ord(ctx, "compra", c - st, 1.5)


def af3_retomada_da_abertura_a_favor_de_ontem(ctx):
    """FAZER (continuacao, 'V'). Ontem andou >= 0,5 ATRd no lado s. Hoje o preco ficou >= 1 ATR15 do lado CONTRARIO da abertura e agora
    fechou de volta do lado a favor de s (cruzou a abertura): entra a favor de s no fecho, stop 0,3 ATR15 alem do extremo contrario do dia
    (teto 590), sem alvo fixo alem de 2R. Entre 10:00 e 13:00. Geral na ideia (retoma a abertura = o teste do dia falhou)."""
    d = ctx.diario; h = ctx.hoje
    if len(d) < 2 or len(h) < 4 or not (10 * 60 <= _hm(ctx) <= 13 * 60): return None
    y = d.iloc[-1]; mov = float(y.close - y.open)
    if abs(mov) < 0.5 * ctx.atrd: return None
    s = 1 if mov > 0 else -1
    op = float(h.open.iloc[0]); c = float(h.close.iloc[-1]); c_ant = float(h.close.iloc[-2])
    ext = float(h.low.min()) if s == 1 else float(h.high.max())
    if s * (op - ext) >= 1.0 * ctx.atr15 and s * (c - op) > 0 and s * (c_ant - op) <= 0:
        st = ext - s * 0.3 * ctx.atr15
        return _ord(ctx, "compra" if s == 1 else "venda", abs(c - st), 2.0)


# =====================================================================================================  gestao
def _gerir_tempo(ctx, pos):
    """Gestao por estado: depois de 8 velas (2h) em posicao, aperta o stop para 0,75 ATR15 do fecho (so a favor). Quem nao andou a favor
    em 2h perde o benefico da duvida: o stop largo deixa de proteger e passa a so custar."""
    if (ctx.t - pos["t_ent"]) < pd.Timedelta(hours=2): return None
    c = float(ctx.hoje.close.iloc[-1])
    return c - 0.75 * ctx.atr15 if pos["lado"] == "compra" else c + 0.75 * ctx.atr15


def ap_ag1(cfg):
    cfg.fz = [(n, r, g if g is not None else _gerir_tempo) for n, r, g in cfg.fz]


# =====================================================================================================  NAO_FAZER
def _payoff_min(k):
    def ap(cfg):
        def mk(r):
            def w(ctx):
                s = r(ctx)
                if s and "erro" not in s and s.get("alvo") is not None:
                    p = float(s.get("preco", ctx.hoje.close.iloc[-1]))
                    if abs(float(s["alvo"]) - p) < k * abs(float(s["stop"]) - p): return None
                return s
            return w
        cfg.fz = [(n, mk(r), g) for n, r, g in cfg.fz]
    return ap


def an3_nf_vender_cedo_apos_dia_altista(ctx):
    """NAO_FAZER. Ontem subiu >= 0,8 ATRd e fechou nos 25% superiores da faixa; antes das 11:00 de hoje, vender e ir contra a perna que
    acabou de fechar forte (o dia 09-05 abriu sem gap, 130 pts abaixo do fecho). Condicao de mercado = estado do dia anterior."""
    d = ctx.diario
    if len(d) < 2 or _hm(ctx) >= 11 * 60: return None
    y = d.iloc[-1]; rng = float(y.high - y.low)
    if rng > 0 and (y.close - y.open) / ctx.atrd >= 0.8 and (y.close - y.low) / rng >= 0.75:
        return _ord(ctx, "venda", 120, 2)


PROPS = {
    "AF1": ("FAZER", "compra o recuo da manha apos dia anterior altista forte (continuacao, cedo)", G._add_fz("c3a:AF1", af1_compra_recuo_apos_dia_altista)),
    "AF3": ("FAZER", "retomada da abertura a favor do dia anterior (V)", G._add_fz("c3a:AF3", af3_retomada_da_abertura_a_favor_de_ontem)),
    "AG1": ("gestao", "stop aperta para 0,75 ATR15 do fecho depois de 2h sem sair (toda FAZER sem gerir)", ap_ag1),
    "AN1": ("NAO_FAZER", "payoff minimo: descarta FAZER com alvo < 0,5 x stop", _payoff_min(0.5)),
    "AN1b": ("NAO_FAZER", "payoff minimo: descarta FAZER com alvo < 0,7 x stop", _payoff_min(0.7)),
    "AN3": ("NAO_FAZER", "nao vender antes das 11:00 apos dia anterior altista forte", G._add_nf("c3a:AN3", an3_nf_vender_cedo_apos_dia_altista)),
}
G.REG.update(PROPS)
MODULOS = ("regras.c3_grupo_2024_09_05", "regras.c3_2024_09_05", "regras.c3_2024_10_25")

# lista final na ordem da tabela (proprias + comuns do grupo)
LISTA = ["AF1", "AF3", "G2", "AG1", "AN1", "AN1b", "AN3", "G1", "G5", "G3a", "G3d", "G4"]

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "conj":
        G.imprime(f"DIA {DIA}", [(k,) for k in LISTA], MODULOS, ("2024-09-05", "2024-10-25"))
