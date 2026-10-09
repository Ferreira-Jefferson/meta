"""Regras do pregao 2024-05-16 (WIN): rotacao com varredura. Topo 9:30, fundo 11:00, lateral ate o fim."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import base


def _h(ctx):
    return ctx.t.hour * 60 + ctx.t.minute


# ---------------- FAZER ----------------
def f1_rompe_minima_1a_hora(ctx):
    """Seguir rompimento: apos 10:00, vela fecha abaixo da minima das 4 primeiras velas -> vende; stop na
    maxima da faixa (limite 550 pts), alvo 1,5x o risco. Condicao: faixa de abertura estreita (< 0,5 ATR
    diario) que rompe. Natureza: rompimento da faixa da abertura. Geral? provavelmente geral."""
    h = ctx.hoje
    if len(h) < 5 or ctx.ops_hoje or _h(ctx) > 12 * 60:
        return None
    f = h.iloc[:4]
    lo, hi = f.low.min(), f.high.max()
    if hi - lo > 0.6 * ctx.atrd:
        return None
    c = h.close.iloc[-1]
    if c < lo:
        r = min(hi - c, 550)
        return dict(lado="venda", stop=c + r, alvo=c - 0.15 * ctx.atrd, contratos=1)


def f2_falha_maxima_matinal(ctx):
    """Reversao em falha: a maxima do dia saiu nas 3 primeiras velas e, antes das 11:00, uma vela fecha
    abaixo da abertura do dia -> vende (perdeu o ponto de partida). Stop na maxima do dia (limite 550),
    alvo 1R. Condicao: alta cedo sem continuidade. Geral? parcialmente (combinacao vista no dia)."""
    h = ctx.hoje
    if len(h) < 4 or ctx.ops_hoje or _h(ctx) > 11 * 60:
        return None
    op = h.open.iloc[0]
    c = h.close.iloc[-1]
    if c < op and h.high.idxmax() <= h.index[2]:
        hi = h.high.max()
        r = min(hi - c, 550)
        return dict(lado="venda", stop=c + r, alvo=c - 0.15 * ctx.atrd, contratos=1)


def f3_compra_exaustao_vwap(ctx):
    """Reversao a media: apos 10:30, preco bem abaixo da VWAP do dia (>= 1,8 ATR15), vela com pavio
    inferior grande fechando acima do meio, dia de baixa eficiencia direcional -> compra, alvo na VWAP.
    Condicao: rotacao. Geral? provavelmente geral em dias de rotacao; limiares ajustados."""
    h = ctx.hoje
    if len(h) < 6 or ctx.ops_hoje or _h(ctx) > 14 * 60 or _h(ctx) < 10 * 60 + 30:
        return None
    tp = (h.high + h.low + h.close) / 3
    vw = float((tp * h.vol).sum() / h.vol.sum())
    u = h.iloc[-1]
    c = u.close
    ef = abs(c - h.open.iloc[0]) / max(h.high.max() - h.low.min(), 1)
    if ef > 0.5:
        return None
    rng = max(u.high - u.low, 1)
    if vw - c >= 1.8 * ctx.atr15 and (u.close - u.low) > 0.5 * rng and (min(u.open, u.close) - u.low) >= 0.3 * rng:
        r = min(c - h.low.min() + 120, 550)
        return dict(lado="compra", stop=c - r, alvo=vw, contratos=1)


def f4_fade_borda_lateral(ctx):
    """Lateral da tarde: apos 12:00, faixa das ultimas 8 velas < 0,3 ATR diario e volume abaixo de 0,75 da
    media das 8 primeiras velas; compra a minima da faixa ou vende a maxima (20% extremos). Stop 0,8 da
    faixa alem da borda (max 450), alvo 70% da faixa. Condicao: compressao pos-almoco. Geral? provavelmente
    geral em rotacao, nao serve em dia de tendencia."""
    h = ctx.hoje
    if len(h) < 14 or ctx.ops_hoje or not (12 * 60 <= _h(ctx) <= 15 * 60 + 30):
        return None
    j = h.iloc[-8:]
    hi, lo = j.high.max(), j.low.min()
    fx = hi - lo
    if fx > 0.3 * ctx.atrd or fx < 150:
        return None
    if j.vol.mean() > h.vol.iloc[:8].mean() * 0.75:
        return None
    c = h.close.iloc[-1]
    if c <= lo + 0.2 * fx:
        return dict(lado="compra", stop=c - min(fx * 0.8, 450), alvo=lo + 0.7 * fx, contratos=1)
    if c >= hi - 0.2 * fx:
        return dict(lado="venda", stop=c + min(fx * 0.8, 450), alvo=hi - 0.7 * fx, contratos=1)


def f5_rompe_faixa_tarde_compra(ctx):
    """Fade da extensao tardia: entre 15:00 e 16:00, fecha acima da maxima das 12 velas anteriores (faixa
    < 0,4 ATR diario) e acima da abertura -> VENDE (rompimento de compressao sem forca), stop 300 pts,
    alvo no meio da faixa. Condicao: dia de rotacao, rompimento tardio que nao segue. Geral? ajustada ao
    dia (apos 15h os sinais pioram; o rompimento a favor perdeu R$59 aqui). Resultado: +R$66."""
    h = ctx.hoje
    if len(h) < 20 or ctx.ops_hoje or not (15 * 60 <= _h(ctx) <= 16 * 60):
        return None
    j = h.iloc[-13:-1]
    hi, lo = j.high.max(), j.low.min()
    c = h.close.iloc[-1]
    if hi - lo > 0.4 * ctx.atrd:
        return None
    if c > hi and c > h.open.iloc[0]:
        return dict(lado="venda", stop=c + 300, alvo=(hi + lo) / 2, contratos=1)


FAZER = [("F1 vende rompimento da minima da 1a hora", f1_rompe_minima_1a_hora, None),
         ("F2 vende falha da maxima matinal", f2_falha_maxima_matinal, None),
         ("F3 compra exaustao abaixo da VWAP", f3_compra_exaustao_vwap, None),
         ("F4 fade das bordas da lateral da tarde", f4_fade_borda_lateral, None),
         ("F5 vende rompimento falso tardio da compressao", f5_rompe_faixa_tarde_compra, None)]


# ---------------- NAO FAZER ----------------
def n1_compra_minima_nova(ctx):
    """Comprar cada minima nova do dia depois das 10:30 com o preco abaixo da abertura (faca caindo).
    Armadilha: queda com volume crescente (10:30-10:45 sao as velas de maior volume do dia): minima nova
    com volume alto continua. Veto: nao comprar minima nova do dia com volume relativo > 1,3x.
    Geral? provavelmente geral."""
    h = ctx.hoje
    if len(h) < 6 or ctx.ops_hoje or _h(ctx) > 12 * 60 or _h(ctx) < 10 * 60 + 30:
        return None
    u = h.iloc[-1]
    if u.low <= h.low.min() and u.close < h.open.iloc[0]:
        c = u.close
        return dict(lado="compra", stop=c - 300, alvo=c + 600, contratos=1)


def n2_vende_fundo_esticado(ctx):
    """Vender a queda ja esticada: apos 11:00, preco ja 1,2 ATR15 abaixo da abertura -> vende. Armadilha:
    depois da varredura o preco devolve (fundo do dia as 11:00). Veto: nao vender quando a queda ja
    percorreu > 1 ATR15 e a minima nao renova ha 2+ velas. Geral? provavelmente geral."""
    h = ctx.hoje
    if len(h) < 8 or ctx.ops_hoje or _h(ctx) > 13 * 60 or _h(ctx) < 11 * 60:
        return None
    c = h.close.iloc[-1]
    if h.open.iloc[0] - c >= 1.2 * ctx.atr15:
        return dict(lado="venda", stop=c + 400, alvo=c - 600, contratos=1)


def n3_compra_rompe_maxima_abertura(ctx):
    """Comprar o rompimento da maxima das 2 primeiras velas ate 10:15. Armadilha: gap nulo e rompimento
    que vira topo do dia e devolve ~1.300 pts. Veto: nao comprar rompimento matinal com gap < 0,1 ATR
    diario sem expansao de volume. Geral? provavelmente geral."""
    h = ctx.hoje
    if len(h) < 3 or ctx.ops_hoje or _h(ctx) > 10 * 60 + 15:
        return None
    hi = h.high.iloc[:2].max()
    c = h.close.iloc[-1]
    if c > hi:
        return dict(lado="compra", stop=c - 400, alvo=c + 800, contratos=1)


def n4_vende_rompe_lateral_tarde(ctx):
    """Vender o rompimento da minima da lateral da tarde (13:00-15:00). Armadilha: lateral de baixo volume
    com rompimento falso, preco volta ao meio. Veto: nao seguir rompimento de lateral comprimida sem
    aumento de volume (> 1,2x). Geral? provavelmente geral."""
    h = ctx.hoje
    if len(h) < 14 or ctx.ops_hoje or not (13 * 60 <= _h(ctx) <= 15 * 60):
        return None
    j = h.iloc[-9:-1]
    c = h.close.iloc[-1]
    if c < j.close.min():
        return dict(lado="venda", stop=c + 300, alvo=c - 600, contratos=1)


def n5_compra_alta_tardia(ctx):
    """Perseguir a alta final: entre 16:00 e 17:30, vela fecha acima da anterior e o preco esta acima da
    abertura -> compra. Armadilha: fim de pregao com volume em queda (< 0,5 da media), alta e devolvida.
    Veto: nao abrir posicao apos 16:00. Geral? provavelmente geral."""
    h = ctx.hoje
    if len(h) < 20 or ctx.ops_hoje or not (16 * 60 <= _h(ctx) <= 17 * 60 + 30):
        return None
    c = h.close.iloc[-1]
    if c > h.open.iloc[0] and c > h.close.iloc[-2]:
        return dict(lado="compra", stop=c - 250, alvo=c + 500, contratos=1)


NAO_FAZER = [("N1 compra cada minima nova (faca caindo)", n1_compra_minima_nova, None),
             ("N2 vende o fundo esticado", n2_vende_fundo_esticado, None),
             ("N3 compra rompimento da maxima da abertura", n3_compra_rompe_maxima_abertura, None),
             ("N4 vende rompimento da lateral da tarde", n4_vende_rompe_lateral_tarde, None),
             ("N5 compra alta tardia depois das 16h", n5_compra_alta_tardia, None)]

DIA = "2024-05-16"
if __name__ == "__main__":
    for tag, lst in (("FAZER", FAZER), ("NAO FAZER", NAO_FAZER)):
        print(tag)
        for nome, rg, ge in lst:
            r = base.resumo(base.simula_dia(DIA, rg, ge))
            print(f"  {nome:50s} R$ {r['brl']:9.2f}  ops {r['ops']}  pts {r['pts']}", flush=True)
            for x in r["lista"]:
                print("      ", x)
