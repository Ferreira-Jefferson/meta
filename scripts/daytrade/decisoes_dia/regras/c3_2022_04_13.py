"""Ciclo 3 - dia 2022-04-13 (WIN M15, ROTACAO, ef 0,024). v1 = v2 = v3 = -R$103,00 (1 operacao).

O DIA: gap de ALTA de +2.400 pts (1,31 ATRd) sobre o fecho de ontem (116.420 -> abre 118.820), depois 9 horas de faixa 118.295-119.460
(range 0,9 ATRd, fecha 119.095, +275 da abertura). A v3 vendeu a `Falha da alta inicial` as 11:00 (118.635; stop 119.140 = 505 pts = 1,03 ATR15;
alvo 117.877), ficou 3 horas dentro da faixa e foi stopada as 14:00 pela maxima do dia (119.460). O alvo estava 757 pts abaixo; a minima
seguinte foi 118.355 (-280 pts, 0,55 R) e nao voltou a cair.

Regras puras (so passado do instante). Nada existente e editado. `python -m regras.c3_2022_04_13` imprime, para cada regra, R$ isolada no dia
(base.simula_dia) e o R$ do dia com a proposta DENTRO do robo v3. Efeito nos 70 dias: `python -m regras.c3_grupo_2022_04_13 <ids>` (ou a funcao `avalia`).
"""
import sys
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ)); sys.path.insert(0, str(RAIZ / "ciclo3"))
from regras import c3_grupo_2022_04_13 as g
from regras import c2_2025_04_07 as c25, r_2023_03_20 as r23

FALHA = "2023_03_20:Falha da alta inicial (venda)"
DIA = "2022-04-13"


def gap_atrd(ctx):
    return float(ctx.hoje.open.iloc[0] - ctx.diario.close.iloc[-1]) / ctx.atrd


def hm_ok(ctx): return g.hm(ctx) >= 10 * 60 + 30


# ============================================================================= FAZER / ajustes
def f1_falha_alta_alvo_meio(ctx):
    """AJUSTE de `Falha da alta inicial (venda)` (alvo): em rotacao (ef do dia ate agora < 0,10) o alvo cai de 1,5R para 0,5R (252 pts no dia).
    Condicao: dia sem direcao: a reversao devolve um pedaco, nao a faixa inteira (no dia a minima seguinte foi 0,55R abaixo da entrada).
    Natureza: ajuste de saida. Geral? Nao: nos 70 dias piora (ver tabela)."""
    s = r23.f_falha_alta_inicial(ctx)
    if s and g.ef_hoje(ctx) < 0.10:
        s = dict(s); p = float(s["preco"]); s["alvo"] = p - 0.5 * abs(float(s["stop"]) - p)
    return s


def f2_falha_alta_trava(ctx):
    """AJUSTE de gestao (adaptativo, rotacao): a venda da falha da alta passa a ter, depois de 0,5R a favor, stop em entrada - 20 pts
    (zero a zero com custo). O sinal e o original; a trava esta em `g.post_trava` (proposta G2b). Natureza: gestao adaptativa (estado = ef<0,10)."""
    return r23.f_falha_alta_inicial(ctx)


def f3_fade_vwap_em_rotacao(ctx):
    """FAZER ja existente em c2_2025_04_07 (F3, nao adotado no ciclo 3 por so ter disparado em 1 dia): depois das 12:00, com ef do dia <= 0,08,
    fecha a >= 0,5 faixa mediana do VWAP com a vela virando contra o afastamento -> volta ao VWAP. No dia: 2 vendas, alvo no VWAP.
    Natureza: reversao a valor."""
    return c25.f3_fade_vwap_em_rotacao(ctx)


def f4_fade_borda_rotacao(ctx):
    """FAZER novo (grupo): toque na borda da faixa do dia em rotacao com rejeicao -> entra contra a borda, alvo 1R. Ver g.f_fade_borda_rotacao.
    Natureza: reversao a valor (fade de borda)."""
    return g.f_fade_borda_rotacao(ctx)


# ============================================================================= NAO_FAZER (armadilhas; R$ < 0 isolada no dia)
def _na_direcao_da_vela(ctx):
    u = ctx.hoje.iloc[-1]; r = min(1.0 * ctx.atr15, g.TETO)
    if u.close < u.open: return g.ordem(ctx, "venda", r, 1.5 * r)
    if u.close > u.open: return g.ordem(ctx, "compra", r, 1.5 * r)


def n1_vender_terco_inferior_em_rotacao(ctx):
    """NAO FAZER: em rotacao (ef<0,10, apos 10:30), vender a vela de baixa com o fecho no terco INFERIOR da faixa do dia. Armadilha: a faixa
    sem direcao devolve da borda; vender o fundo da faixa paga o repique. Condicao: ef<0,10 + posicao na faixa <= 0,30."""
    if g._borda_rotacao(ctx, "venda") and ctx.hoje.iloc[-1].close < ctx.hoje.iloc[-1].open:
        r = min(1.3 * ctx.atr15, g.TETO); return g.ordem(ctx, "venda", r, 1.5 * r)


def n2_vender_em_gap_de_alta_grande(ctx):
    """NAO FAZER: em dia de gap de ALTA >= 1 ATRd, depois das 10:30 e em rotacao, vender (reversao). Armadilha: o gap grande e aceito (o preco
    fica na faixa acima do fecho de ontem); vender o fechamento do gap nao tem combustivel. Condicao: gap >= 1 ATRd + ef<0,10."""
    if hm_ok(ctx) and gap_atrd(ctx) >= 1.0 and g.ef_hoje(ctx) < 0.10 and ctx.hoje.iloc[-1].close < ctx.hoje.iloc[-1].open:
        r = min(1.0 * ctx.atr15, g.TETO); return g.ordem(ctx, "venda", r, 1.5 * r)


def n3_entrar_com_stop_menor_que_1_1_atr(ctx):
    """NAO FAZER: abrir ordem cujo stop fica a <= 1,1 ATR15 do preco (a venda do dia: 505 pts = 1,03 ATR15). Armadilha: o stop esta dentro do
    ruido de ~3 velas; num dia sem direcao ele e varrido antes do alvo. Condicao: risco <= 1,1 ATR15."""
    s = r23.f_falha_alta_inicial(ctx)
    if s and abs(float(s["stop"]) - float(s["preco"])) <= 1.1 * ctx.atr15: return s


def n4_operar_em_rotacao_profunda(ctx):
    """NAO FAZER: depois das 10:30, com ef do dia < 0,06 e amplitude < 0,45 ATRd, VENDER a vela de baixa (continuacao). Armadilha: nada
    se estende; a continuacao de uma vela e devolvida. Condicao: ef<0,06 + faixa < 0,45 ATRd."""
    if hm_ok(ctx) and g.ef_hoje(ctx) < 0.06 and g.amp_atrd(ctx) < 0.45 and ctx.hoje.iloc[-1].close < ctx.hoje.iloc[-1].open:
        r = min(1.0 * ctx.atr15, g.TETO); return g.ordem(ctx, "venda", r, 1.5 * r)


FAZER = [("F1 falha da alta, alvo 0,5R em rotacao", f1_falha_alta_alvo_meio, None),
         ("F2 falha da alta + trava em 0,5R (rotacao)", f2_falha_alta_trava, None),
         ("F3 fade do VWAP em rotacao", f3_fade_vwap_em_rotacao, None),
         ("F4 fade de borda da faixa em rotacao", f4_fade_borda_rotacao, None)]
NAO_FAZER = [("N1 vender terco inferior em rotacao", n1_vender_terco_inferior_em_rotacao, None),
             ("N2 vender em gap de alta >= 1 ATRd em rotacao", n2_vender_em_gap_de_alta_grande, None),
             ("N3 stop <= 1,1 ATR15", n3_entrar_com_stop_menor_que_1_1_atr, None),
             ("N4 operar em rotacao profunda", n4_operar_em_rotacao_profunda, None)]


# ============================================================================= como cada proposta entra no v3 (Cfg)
def _sub_fazer(nome, fn):
    def ap(cfg):
        assert any(n == nome for n, _, _ in cfg.fz), nome
        cfg.fz = [(n, fn, gg) if n == nome else (n, r, gg) for n, r, gg in cfg.fz]
    return ap


def _cancela_risco_curto(ctx, s, n):
    return abs(float(s["stop"]) - float(s.get("preco", ctx.hoje.close.iloc[-1]))) <= 1.1 * ctx.atr15


def _veto_gap_grande(ctx, lado):
    return lado == "venda" and hm_ok(ctx) and gap_atrd(ctx) >= 1.0 and g.ef_hoje(ctx) < 0.10


def _veto_rot_profunda(ctx, lado):
    return lado == "venda" and hm_ok(ctx) and g.ef_hoje(ctx) < 0.06 and g.amp_atrd(ctx) < 0.45


CAND = {
    "a_F1_alvo_meio_falha": _sub_fazer(FALHA, f1_falha_alta_alvo_meio),   # so o alvo da falha da alta (F1 geral = G1c)
    "a_F3_vwap_rotacao": g.ap_fz("c3a:F3 fade vwap rotacao", f3_fade_vwap_em_rotacao),
    "a_N2_gap_alta_grande": g.ap_nf(g.ambos("c3a:gap alta grande", _veto_gap_grande)),
    "a_N3_stop_curto": g.ap_post(g.post_cancela(_cancela_risco_curto)),
    "a_N4_rotacao_profunda": g.ap_nf(g.ambos("c3a:rotacao profunda", _veto_rot_profunda)),
}
# F2 = G2b_trava_0.5R_rot, F4 = G5_fade_borda_rot, N1 = G3n_venda_ef0.1_f0.3 (todas no grupo)
PROPOSTAS = {"F1": "G1c_alvo_0.5R_rot", "F2": "G2b_trava_0.5R_rot", "F3": "a_F3_vwap_rotacao", "F4": "G5_fade_borda_rot",
             "N1": "G3n_venda_ef0.1_f0.3", "N2": "a_N2_gap_alta_grande", "N3": "a_N3_stop_curto", "N4": "a_N4_rotacao_profunda",
             "G1d alvo 1R rot": "G1d_alvo_1R_rot", "G3 borda 2 lados": "G3_veto_borda_rot"}


def dia_com(ids):
    import cfg3
    tr, _ = cfg3.roda(DIA, g.cfg_de(ids, CAND))
    ok = [x for x in tr if x.t_ent is not None]
    return round(sum(x.brl for x in ok), 2), [(x.fonte[:30], x.lado, str(x.t_ent.time()), str(x.t_sai.time()), x.motivo, round(x.brl, 1)) for x in ok]


if __name__ == "__main__":
    import base
    for grupo, lista in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for nome, r, _ in lista:
            res = base.resumo(base.simula_dia(DIA, r, None, max_ops=3))
            print(f"{grupo:9s} {nome:48s} isolada R$ {res['brl']:8.2f} ops {res['ops']}", flush=True)
    print("v3 puro:", dia_com(()))
    for k, i in PROPOSTAS.items():
        print(f"dentro do v3 + {k:16s} ({i}):", dia_com((i,)), flush=True)
