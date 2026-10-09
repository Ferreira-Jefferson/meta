"""Ciclo 2 - dia 2025-04-07 (WIN M15, tipo ruim, ef 0,009). v1 e v2 fecharam -R$118,00 (1 operacao).

O DIA: gap de baixa de -2.030 pts (~1 ATRd) sobre o fecho de sexta, minima 124.225 as 10:30, e uma barra de CHOQUE as 11:00
(125.530 -> 129.025: 3.495 pts de faixa) devolvida em 30 min. Dai em diante vira faixa 125.1k-127.3k, volume caindo (1,5M -> 0,3M),
fecha 125.910. A v2 vendeu o `pullback EMA20 em baixa` as 12:15 (126.115; stop = teto de 590 pts) e foi stopada as 14:36 por
55 pts (maxima 126.760 x stop 126.705). O alvo de 1R (125.525) ja fora tocado na vela de entrada. No momento da entrada o ATR15
era 1.337 pts: o stop permitido (590) era 0,44 ATR15, dentro do ruido.

Regras puras: so usam o passado do instante da decisao. Nao edita r_*.py nem robo*.py.
`python -m regras.c2_2025_04_07 [conjunto]` imprime o resultado isolado no dia e (com `conjunto`) o efeito nos 50 dias.
"""
import numpy as np
import pandas as pd

TETO = 590.0  # risco maximo por contrato (6% de R$2.000), em pontos


# ----------------------------------------------------------------------------- utilidades
def _hm(ctx):
    return ctx.t.hour * 60 + ctx.t.minute


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def _vwap(h):
    tp = (h.high + h.low + h.close) / 3
    return float((tp * h.vol).sum() / h.vol.sum())


def _amp_atrd(ctx):
    """amplitude do dia ate agora (max-min) em ATR diario."""
    return float(ctx.hoje.high.max() - ctx.hoje.low.min()) / ctx.atrd


def _efic(ctx):
    """eficiencia do dia ate agora: |fecho - abertura| / soma das faixas M15."""
    h = ctx.hoje
    s = float((h.high - h.low).sum())
    return abs(float(h.close.iloc[-1] - h.open.iloc[0])) / s if s > 0 else 0.0


def _r15(ctx, n=14):
    """faixa mediana das ultimas n velas M15 (mais robusta a UMA barra de choque que o ATR)."""
    m = ctx.m15.iloc[-n:]
    return float((m.high - m.low).median())


def _idade_choque(ctx, k=4.0, jan=30):
    """Velas desde a ultima barra de CHOQUE (faixa >= k x mediana das 30 faixas anteriores) nas ultimas `jan` velas
    fechadas; 0 = a propria vela atual; None = nao houve."""
    m = ctx.m15
    rng = m.high - m.low
    rel = (rng / rng.rolling(30).median().shift(1)).iloc[-jan:]
    idx = [i for i in range(len(rel)) if rel.iloc[i] >= k]
    return None if not idx else len(rel) - 1 - idx[-1]


def _ord(ctx, lado, stop_k, alvo_k, base="atr", alvo_px=None):
    """Ordem limitada no fecho. Stop = stop_k x (ATR15 ou r15), teto TETO. Alvo = alvo_k x risco, ou `alvo_px`."""
    p = float(ctx.hoje.close.iloc[-1])
    ref = ctx.atr15 if base == "atr" else _r15(ctx)
    r = min(stop_k * ref, TETO)
    s = 1 if lado == "compra" else -1
    return dict(lado=lado, preco=p, stop=p - s * r, alvo=(alvo_px if alvo_px is not None else p + s * alvo_k * r), contratos=1)


def _pullback_sinal(ctx):
    """Gatilho IDENTICO ao de r_2022_11_16.f_pullback_ema (venda no recuo a EMA20 M15)."""
    if not (10.5 <= _hm(ctx) / 60 <= 15):
        return False
    e = _ema(ctx.m15.close, 20)
    h = ctx.hoje.iloc[-1]
    return bool(h.close < e.iloc[-1] and h.high >= e.iloc[-1] - 0.3 * ctx.atr15 and e.iloc[-1] < e.iloc[-4])


# ============================================================================= FAZER (5)
def f1_pullback_proximo_alvo_1r_se_exausto(ctx):
    """AJUSTE de `2022_11_16:venda pullback EMA20 em baixa` (gatilho + alvo). Duas mudancas: (a) o fecho tem de estar a <= 0,9 faixa
    mediana abaixo da EMA20 (recuo de verdade; mais longe e perseguir queda ja esticada); (b) se o dia ja andou >= 2 ATRd
    (amplitude consumida) o alvo cai de 2,5R para 1R. Stop igual (1,3 ATR15, teto 580). Condicao: dia de choque/gap grande em que
    a faixa ja foi gasta. Natureza: ajuste de gatilho e de saida."""
    if not _pullback_sinal(ctx):
        return None
    e = _ema(ctx.m15.close, 20).iloc[-1]; c = float(ctx.hoje.close.iloc[-1])
    if e - c > 0.9 * _r15(ctx):
        return None
    r = min(1.3 * ctx.atr15, 580.0)
    k = 1.0 if _amp_atrd(ctx) >= 2.0 else 2.5
    return dict(lado="venda", preco=c, stop=c + r, alvo=c - k * r, contratos=1)


def f2_compra_exaustao_vendedora(ctx):
    """FAZER novo (reversao em exaustao): ate 14:00, o dia ja caiu >= 1,3 ATRd do fecho de ontem ate a minima; a vela toca a minima do
    dia (a 0,3 faixa), fecha no terco superior, e de alta, tem faixa >= 1,5x a faixa mediana de 30 velas e fecha acima da abertura
    da vela anterior (engolfa). Compra, stop 1,3 ATR15 (teto 590), alvo 2R. Condicao: liquidacao forcada (queda de varios ATRd) com
    rejeicao forte da minima. Natureza: reversao em exaustao."""
    h = ctx.hoje
    if len(h) < 4 or _hm(ctx) > 14 * 60:
        return None
    u = h.iloc[-1]; rng = u.high - u.low
    if rng <= 0:
        return None
    queda = (float(ctx.diario.close.iloc[-1]) - float(h.low.min())) / ctx.atrd
    if queda >= 1.3 and u.low <= h.low.min() + 0.3 * _r15(ctx) and u.close >= u.low + 0.66 * rng and u.close > u.open             and rng >= 1.5 * _r15(ctx, 30) and u.close > h.iloc[-2].open:
        return _ord(ctx, "compra", 1.3, 2.0)


def gerir_chandelier_adaptativo(ctx, pos):
    """GESTAO ADAPTATIVA (sem alvo fixo): o stop inicial fica onde esta ate o preco andar 1R a favor; dai o stop passa a seguir a
    extrema favoravel desde a entrada menos 1,5 x a faixa mediana M15 (volatilidade observada agora). Em dia de choque a folga e
    larga (nao e varrido pelo repique), em dia calmo e curta. So anda a favor."""
    h = ctx.hoje; h = h[h.index >= pos["t_ent"].floor("15min")]
    r0 = abs(pos["preco"] - pos["stop"]) if pos.get("stop") else 0
    lado = pos["lado"]
    if lado == "compra":
        if h.high.max() - pos["preco"] < max(r0, 1):  # ainda nao andou 1R (r0 pode ja ter mudado: usa stop atual)
            return None
        return float(h.high.max()) - 1.5 * _r15(ctx)
    if pos["preco"] - h.low.min() < max(r0, 1):
        return None
    return float(h.low.min()) + 1.5 * _r15(ctx)


def f2_compra_exaustao_vendedora_adaptativa(ctx):
    """F2 sem alvo: mesma entrada de f2_compra_exaustao_vendedora, alvo None; a saida e `gerir_chandelier_adaptativo`."""
    s = f2_compra_exaustao_vendedora(ctx)
    if s:
        s = dict(s); s["alvo"] = None
    return s


def f3_fade_vwap_em_rotacao(ctx):
    """FAZER novo (reversao a valor): depois das 12:00 e antes das 16:00, com o dia em rotacao (eficiencia ate agora <= 0,08), o
    fecho a >= 0,5 faixa-mediana do VWAP com a vela virando contra o afastamento: entra de volta ao VWAP (alvo = VWAP, stop 1 faixa
    mediana, teto 590). Condicao: dia sem direcao, o preco volta ao valor. Natureza: reversao a nivel de valor. Geral (rotacao e o
    regime de ~80% dos dias)."""
    h = ctx.hoje
    if _hm(ctx) < 12 * 60 or _hm(ctx) > 16 * 60 or _efic(ctx) > 0.08:
        return None
    vw = _vwap(h); c = float(h.close.iloc[-1]); r = _r15(ctx)
    if c <= vw - 0.5 * r and h.close.iloc[-1] > h.open.iloc[-1]:
        return _ord(ctx, "compra", 1.0, 0, base="r15", alvo_px=vw)
    if c >= vw + 0.5 * r and h.close.iloc[-1] < h.open.iloc[-1]:
        return _ord(ctx, "venda", 1.0, 0, base="r15", alvo_px=vw)


def f4_fade_borda_da_faixa_pos_choque(ctx):
    """FAZER novo: >= 6 velas depois de uma barra de choque, o preco passa a andar numa faixa (extremos das velas pos-choque).
    Vende a rejeicao da borda superior / compra a da inferior (a vela toca a borda a 0,1 faixa e fecha 0,3 faixa para dentro,
    contra o toque). Stop 1 faixa mediana, alvo 1,5R, ate 16:00. Condicao: choque vira faixa; as bordas seguram. Natureza:
    fade de borda de faixa pos-evento."""
    i = _idade_choque(ctx)
    if i is None or i < 6 or _hm(ctx) > 16 * 60:
        return None
    h = ctx.hoje
    post = h.iloc[-i:-1]
    if len(post) < 5:
        return None
    hi, lo, u, r = post.high.max(), post.low.min(), h.iloc[-1], _r15(ctx)
    if u.high >= hi - 0.1 * r and u.close < u.open and u.close < hi - 0.3 * r:
        return _ord(ctx, "venda", 1.0, 1.5, base="r15")
    if u.low <= lo + 0.1 * r and u.close > u.open and u.close > lo + 0.3 * r:
        return _ord(ctx, "compra", 1.0, 1.5, base="r15")


def f5_fade_choque_devolvido(ctx):
    """FAZER novo: >= 3 velas depois de uma barra de choque de corpo grande (faixa >= 4x a mediana, corpo >= 60%), quando uma vela
    FECHA do lado de dentro da metade do corpo do choque (a primeira vez), opera contra o choque: stop 1,3 ATR15 (teto 590), alvo
    1,5R. Ate 15:00. Condicao: movimento de noticia devolvido a metade tende a devolver o resto. Natureza: fade de choque."""
    m = ctx.m15
    if len(m) < 45 or _hm(ctx) > 15 * 60:
        return None
    rng = m.high - m.low
    rel = rng / rng.rolling(30).median().shift(1)
    u = ctx.hoje.iloc[-1]
    for i in range(-8, -3):
        b = m.iloc[i]
        if rel.iloc[i] >= 4 and abs(b.close - b.open) > 0.6 * (b.high - b.low):
            meio = b.open + 0.5 * (b.close - b.open); up = b.close > b.open
            if up and u.close < meio and m.iloc[-2].close >= meio:
                return _ord(ctx, "venda", 1.3, 1.5)
            if (not up) and u.close > meio and m.iloc[-2].close <= meio:
                return _ord(ctx, "compra", 1.3, 1.5)


# ============================================================================= NAO_FAZER (6 funcoes; N1 tem espelho)
def n1_vender_com_atr_acima_do_teto(ctx):
    """NAO FAZER: operar quando o ATR15 e >= 1,5x o teto de risco (590 pts => ATR15 >= 885): o stop que o caixa permite fica
    abaixo de 0,67 ATR15, dentro do ruido de uma vela. Armadilha: o stop de 590 e varrido por oscilacao comum; no dia, a venda
    de 12:15 (ATR15 1.337) foi stopada por 55 pts e o preco voltou. Condicao de mercado: volatilidade incompativel com o caixa."""
    if _hm(ctx) >= 10 * 60 and ctx.atr15 >= 1.5 * TETO and ctx.hoje.close.iloc[-1] < ctx.hoje.close.iloc[-2]:
        return _ord(ctx, "venda", 1.3, 2.5)


def n1b_comprar_com_atr_acima_do_teto(ctx):
    """Espelho de n1 (mesmo veto do lado da compra)."""
    if _hm(ctx) >= 10 * 60 and ctx.atr15 >= 1.5 * TETO and ctx.hoje.close.iloc[-1] > ctx.hoje.close.iloc[-2]:
        return _ord(ctx, "compra", 1.3, 2.5)


def n2_vender_pos_choque_ate_5_velas(ctx):
    """NAO FAZER: vender (fecho abaixo da EMA20 e da vela anterior) nas 5 velas seguintes a uma barra de choque (faixa >= 4x a
    mediana). Armadilha: depois da noticia o preco oscila dos dois lados com faixa de varias vezes o normal, o stop pega o
    repique. Condicao: volatilidade anomala logo depois de um choque."""
    i = _idade_choque(ctx)
    if i is not None and i <= 5 and _hm(ctx) < 16 * 60 and ctx.hoje.close.iloc[-1] < ctx.hoje.close.iloc[-2] \
            and ctx.hoje.close.iloc[-1] < _ema(ctx.m15.close, 20).iloc[-1]:
        return _ord(ctx, "venda", 1.3, 2.5)


def n3_vender_acima_da_abertura_em_gap_de_baixa(ctx):
    """NAO FAZER: em dia de gap de baixa, vender abaixo da EMA20 enquanto o preco esta ACIMA da abertura do dia (apos 10:30).
    Armadilha: o gap esta sendo preenchido; a 'tendencia de baixa' e a do dia anterior e o preco ja a desmentiu. Condicao: gap de
    baixa + preco acima da abertura."""
    h = ctx.hoje
    if _hm(ctx) >= 10 * 60 + 30 and h.open.iloc[0] < ctx.diario.close.iloc[-1] and h.close.iloc[-1] > h.open.iloc[0] \
            and h.close.iloc[-1] < _ema(ctx.m15.close, 20).iloc[-1]:
        return _ord(ctx, "venda", 1.3, 2.5)


def n4_vender_perto_do_vwap_em_rotacao(ctx):
    """NAO FAZER: depois das 11:30, com a eficiencia do dia < 0,1 e o fecho a <= 0,3 faixa-mediana do VWAP, vender a vela de baixa.
    Armadilha: no VWAP de um dia sem direcao nao ha esticamento a favor; a venda de continuacao vira ruido. Condicao: rotacao
    + preco no valor."""
    h = ctx.hoje
    if _hm(ctx) >= 11 * 60 + 30 and abs(h.close.iloc[-1] - _vwap(h)) <= 0.3 * _r15(ctx) and _efic(ctx) < 0.1 \
            and h.close.iloc[-1] < h.close.iloc[-2]:
        return _ord(ctx, "venda", 1.3, 2.5)


def n5_vender_apos_amplitude_esgotada_em_rotacao(ctx):
    """NAO FAZER: depois das 11:30, com o dia ja tendo andado >= 2 ATRd e a eficiencia ate agora < 0,05 (foi e voltou), vender
    uma vela de baixa. Armadilha: a faixa do dia foi consumida pelo choque e devolvida; falta combustivel para continuacao.
    Condicao: amplitude esgotada + dia sem direcao."""
    if _hm(ctx) >= 11 * 60 + 30 and _efic(ctx) < 0.05 and _amp_atrd(ctx) >= 2.0 and ctx.hoje.close.iloc[-1] < ctx.hoje.close.iloc[-2]:
        return _ord(ctx, "venda", 1.3, 2.5)


def n6_vender_minima_do_dia_velha(ctx):
    """NAO FAZER: vender (abaixo da EMA20, vela de baixa) quando a minima do dia tem >= 6 velas (1h30) e nao foi renovada.
    Armadilha: a baixa ja foi testada e segurou; a venda e a de um movimento que parou. Condicao: minima do dia velha."""
    h = ctx.hoje
    if len(h) < 8 or _hm(ctx) > 16 * 60:
        return None
    idade = len(h) - 1 - int(np.argmin(h.low.values))
    if idade >= 6 and h.close.iloc[-1] < h.close.iloc[-2] and h.close.iloc[-1] < _ema(ctx.m15.close, 20).iloc[-1]:
        return _ord(ctx, "venda", 1.3, 2.5)


FAZER = [("F1 pullback proximo, alvo 1R se amplitude esgotada", f1_pullback_proximo_alvo_1r_se_exausto, None),
         ("F2 compra exaustao vendedora (prioritaria, chandelier)", f2_compra_exaustao_vendedora_adaptativa, gerir_chandelier_adaptativo),
         ("F3 fade do VWAP em rotacao", f3_fade_vwap_em_rotacao, None),
         ("F4 fade da borda da faixa pos-choque", f4_fade_borda_da_faixa_pos_choque, None),
         ("F5 fade do choque devolvido", f5_fade_choque_devolvido, None)]
NAO_FAZER = [("N1 operar com ATR15 >= 1,5x teto (venda)", n1_vender_com_atr_acima_do_teto, None),
             ("N2 vender ate 5 velas pos-choque", n2_vender_pos_choque_ate_5_velas, None),
             ("N3 vender acima da abertura em gap de baixa", n3_vender_acima_da_abertura_em_gap_de_baixa, None),
             ("N4 vender perto do VWAP em rotacao", n4_vender_perto_do_vwap_em_rotacao, None),
             ("N5 vender com amplitude esgotada em rotacao", n5_vender_apos_amplitude_esgotada_em_rotacao, None),
             ("N6 vender minima do dia velha", n6_vender_minima_do_dia_velha, None)]

# como cada proposta entra no robo v2: substitui um FAZER (pelo nome na lista da v2), acrescenta FAZER no fim, acrescenta veto
PULL = "2022_11_16:venda pullback EMA20 em baixa"
AJUSTES = {
    "F1": dict(sub_fazer={PULL: f1_pullback_proximo_alvo_1r_se_exausto}),
    "F2": dict(add_fazer=[("c2:F2 compra exaustao", f2_compra_exaustao_vendedora, None)]),
    "F2P": dict(prio=[("c2:F2P exaustao prioritaria 2R", f2_compra_exaustao_vendedora, None)]),
    "F2A": dict(prio=[("c2:F2A exaustao prioritaria, chandelier", f2_compra_exaustao_vendedora_adaptativa, gerir_chandelier_adaptativo)]),
    "F3": dict(add_fazer=[("c2:F3 fade vwap rotacao", f3_fade_vwap_em_rotacao, None)]),
    "F4": dict(add_fazer=[("c2:F4 fade borda pos-choque", f4_fade_borda_da_faixa_pos_choque, None)]),
    "F5": dict(add_fazer=[("c2:F5 fade choque", f5_fade_choque_devolvido, None)]),
    "N1": dict(add_veto=[("c2:N1 atr>=1,5 teto venda", n1_vender_com_atr_acima_do_teto, None),
                         ("c2:N1b atr>=1,5 teto compra", n1b_comprar_com_atr_acima_do_teto, None)]),
    "N2": dict(add_veto=[("c2:N2 pos-choque", n2_vender_pos_choque_ate_5_velas, None)]),
    "N3": dict(add_veto=[("c2:N3 gap baixa acima abertura", n3_vender_acima_da_abertura_em_gap_de_baixa, None)]),
    "N4": dict(add_veto=[("c2:N4 vwap rotacao", n4_vender_perto_do_vwap_em_rotacao, None)]),
    "N5": dict(add_veto=[("c2:N5 amplitude esgotada", n5_vender_apos_amplitude_esgotada_em_rotacao, None)]),
    "N6": dict(add_veto=[("c2:N6 minima velha", n6_vender_minima_do_dia_velha, None)]),
}


def monta(fz, nf, chaves):
    """Devolve (fz, nf, prio). `prio` = FAZER prioritarias: entram ao sinal, SEM veto e SEM conflito de lados (ver roda_c2)."""
    fz, nf, prio = list(fz), list(nf), []
    for k in chaves:
        a = AJUSTES[k]
        for orig, fn in a.get("sub_fazer", {}).items():
            assert any(n == orig for n, _, _ in fz), orig
            fz = [(n, fn, None) if n == orig else (n, r, g) for n, r, g in fz]
        fz = fz + a.get("add_fazer", [])
        nf = nf + a.get("add_veto", [])
        prio = prio + a.get("prio", [])
    return fz, nf, prio


def roda_c2(dia, fz, nf, prio):
    """Igual a robo.roda_robo (estrutura v1/v2) com uma etapa antes: se alguma FAZER prioritaria sinaliza (e a limitada nao e
    agressiva), ela entra direto, ignorando vetos e conflito de lados. Sem `prio` e identico a robo.roda_robo."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import robo
    if not prio:
        return robo.roda_robo(dia, fz, nf)
    contra = []

    def decide(ctx):
        for n, r, g in prio:
            s = robo._chama(r, ctx)
            if s and "erro" not in s and not robo._agressiva(s, ctx):
                return s, dict(fazer=[(n, s["lado"])], vetos={}, entrou=n, nota="prioritaria"), g
        sins = []
        for n, r, g in fz:
            s = robo._chama(r, ctx)
            if s and "erro" not in s: sins.append((n, s, g))
        if not sins:
            return None, None, None
        vetos = {"compra": [], "venda": []}
        for n, r, g in nf:
            s = robo._chama(r, ctx)
            if s and "erro" not in s and s.get("lado") in vetos: vetos[s["lado"]].append(n)
        info = dict(fazer=[(n, s["lado"]) for n, s, g in sins], vetos={k: v for k, v in vetos.items() if v}, entrou=None, nota="")
        if len({s["lado"] for _, s, _ in sins}) > 1:
            info["nota"] = "FAZER nos dois lados: nao entra"; return None, info, None
        for n, s, g in sins:
            if robo._agressiva(s, ctx):
                continue
            if vetos[s["lado"]]:
                return None, info, None
            info["entrou"] = n
            return s, info, g
        return None, info, None
    trades, log = robo._roda(dia, decide)
    return trades, log, contra


# ----------------------------------------------------------------------------- avaliacao
def _dias_usados():
    import json
    from pathlib import Path
    j = json.load(open(Path(__file__).resolve().parents[1] / "dias_usados.json"))
    out = list(j["ciclo0"]["dias"]) + [x["dia"] for x in j["ciclo1"]["dias"]] + [x["dia"] for x in j["ciclo2"]["dias"]]
    assert len(out) == 50
    return out


def _um(args):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import robo_v2
    from regras import c2_2025_04_07 as c2
    chaves, dia = args
    fz, nf = robo_v2.monta_v2()
    fz, nf, prio = c2.monta(fz, nf, chaves)
    tr, log, contra = c2.roda_c2(dia, fz, nf, prio)
    ok = [x for x in tr if x.t_ent]
    return chaves, dia, round(sum(x.brl for x in ok), 2), len(ok), [(x.fonte[:50], x.lado, str(x.t_ent.time()), x.motivo, round(x.brl, 1)) for x in ok]


def avalia(configs, dias=None, workers=10):
    from concurrent.futures import ProcessPoolExecutor, as_completed
    dias = dias or _dias_usados()
    res = {tuple(c): {} for c in configs}
    with ProcessPoolExecutor(workers) as ex:
        fut = [ex.submit(_um, (tuple(c), d)) for c in configs for d in dias]
        for f in as_completed(fut):
            ch, d, brl, ops, tr = f.result()
            res[ch][d] = (brl, ops, tr)
    return res


def isolada(dia, regra, gerir=None):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import base
    return base.resumo(base.simula_dia(dia, regra, gerir, max_ops=3))


DIA = "2025-04-07"

if __name__ == "__main__":
    import sys, json
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    for grupo, lista in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for nome, r, g in lista:
            res = isolada(DIA, r, g)
            print(f"{grupo:9s} {nome:48s} isolada R$ {res['brl']:8.2f} ops {res['ops']}", flush=True)
            for x in res["lista"]:
                print("     ", x["lado"], x["sinal"], x["ent"], x["preco"], "stop", x["stop"], "->", x["sai"], x["preco_sai"], x["motivo"], x["brl"])
    if len(sys.argv) > 1 and sys.argv[1] == "conjunto":
        cfgs = [()] + [(k,) for k in AJUSTES] + [tuple(a.split("+")) for a in sys.argv[2:]]
        res = avalia(cfgs)
        b = res[()]
        out = {}
        print("\nconfig | R$ no dia | R$ 50 dias | dias que pioraram | melhoraram", flush=True)
        for c, r in res.items():
            tot = sum(v[0] for v in r.values())
            pi = [d for d in r if r[d][0] < b[d][0] - 0.005]
            me = [d for d in r if r[d][0] > b[d][0] + 0.005]
            out["+".join(c) or "BASE"] = dict(dia=r[DIA][0], total=round(tot, 2), piorou=pi, melhorou=me,
                                              delta={d: round(r[d][0] - b[d][0], 2) for d in r if abs(r[d][0] - b[d][0]) > 0.005})
            print(f"{'+'.join(c) or 'BASE':14s} dia {r[DIA][0]:8.2f}  total {tot:9.2f}  piorou {len(pi)}  melhorou {len(me)}  {[(d, round(r[d][0]-b[d][0],1)) for d in pi+me]}", flush=True)
        json.dump(out, open(Path(__file__).resolve().parents[1] / "c2_2025_04_07_conjunto.json", "w"), indent=1)
