"""Base de decisões do WIN: dados por pregão, contexto só com velas FECHADAS e simulador de execução.

Uma regra é uma função pura `regra(ctx) -> dict | None`, chamada no fechamento de cada vela M15 do pregão.
Ela devolve uma intenção de entrada:
    {"lado": "compra" | "venda", "stop": preço, "alvo": preço | None,
     "preco": preço da ordem limitada (padrão: fechamento da vela), "contratos": 1 | 2}
Opcionalmente a regra tem `gerir(ctx, pos) -> novo_stop | None`, chamada a cada vela fechada
com a posição aberta. O stop só anda a favor.

Execução (desenho fechado do projeto: nunca a mercado na entrada nem no alvo):
- entrada: ordem LIMITADA no `preco`, válida por 3 velas M15 (45 min). Na compra, enche quando a
  mínima M1 fica 10 pts abaixo do preço; na venda é o espelho.
- stop: a mercado no nível. Se o minuto abre além do stop, sai na abertura.
- alvo: LIMITADO. Enche quando passa 10 pts além. Se stop e alvo caem no mesmo minuto, vale o stop.
- fim do pregão: zera no fechamento da última barra contínua.
- custo: 10 pts por contrato por operação. R$ = pts x 0,20 x contratos.
- uma posição por regra por vez. A regra pode voltar a entrar depois de sair.

Sem look-ahead POR CONSTRUÇÃO: `ctx` é montado cortando os dados no instante da decisão.
"""
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[3]
ARQ = RAIZ / "data/win_sem_leiloes/m1_WIN$N_2022_2025.parquet"
FURA, CUSTO, RS_PT, VALIDADE = 10.0, 10.0, 0.20, pd.Timedelta(minutes=45)

_M1 = None


def m1_tudo():
    global _M1
    if _M1 is None:
        _M1 = pd.read_parquet(ARQ)
    return _M1


@dataclass
class Ctx:
    t: pd.Timestamp                 # instante da decisão (fim da vela M15 fechada)
    m1: pd.DataFrame                # M1 até t (do histórico carregado, ~40 pregões)
    m15: pd.DataFrame               # M15 fechadas até t (histórico incluído), colunas open/high/low/close/vol/dia
    diario: pd.DataFrame            # pregões ANTERIORES ao dia (open/high/low/close/vol)
    hoje: pd.DataFrame              # M15 fechadas de hoje até t
    atr15: float                    # ATR(14) M15 até t
    atrd: float                     # ATR(14) diário até ontem
    posicao: dict | None = None     # posição aberta da regra, se houver
    ops_hoje: list = field(default_factory=list)


def _m15(m1):
    b = m1.resample("15min", label="left", closed="left").agg(
        dict(open="first", high="max", low="min", close="last", real_volume="sum")).dropna()
    b = b.rename(columns={"real_volume": "vol"})
    b["dia"] = b.index.normalize()
    return b


def _diario(m1):
    d = m1.resample("1D").agg(dict(open="first", high="max", low="min", close="last", real_volume="sum")).dropna()
    return d.rename(columns={"real_volume": "vol"})


def _atr(df, n=14):
    pc = df.close.shift(1)
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=5).mean()


def carrega(dia, pregoes_antes=40):
    """M1 do dia + `pregoes_antes` pregões anteriores."""
    m1 = m1_tudo()
    dias = m1.index.normalize().unique()
    d = pd.Timestamp(dia)
    i = dias.get_loc(d)
    ini = dias[max(0, i - pregoes_antes)]
    return m1[(m1.index >= ini) & (m1.index < d + pd.Timedelta(days=1))]


def contextos(dia, pregoes_antes=40):
    """Gera (t, ctx_base) para cada vela M15 fechada de hoje. ctx só vê dados até t."""
    m1 = carrega(dia, pregoes_antes)
    d = pd.Timestamp(dia)
    m15 = _m15(m1)
    dia_hist = _diario(m1[m1.index < d])
    atrd = float(_atr(dia_hist).iloc[-1])
    hoje_idx = m15.index[m15.dia == d]
    for ts in hoje_idx:
        t = ts + pd.Timedelta(minutes=15)  # fim da vela
        m1_t = m1[m1.index < t]
        m15_t = m15[m15.index <= ts]
        atr15 = float(_atr(m15_t).iloc[-1])
        yield t, Ctx(t=t, m1=m1_t, m15=m15_t, diario=dia_hist, hoje=m15_t[m15_t.dia == d],
                     atr15=atr15, atrd=atrd)


@dataclass
class Trade:
    lado: str
    contratos: int
    t_sinal: pd.Timestamp
    preco: float
    stop: float
    alvo: float | None
    t_ent: pd.Timestamp | None = None
    t_sai: pd.Timestamp | None = None
    preco_sai: float | None = None
    motivo: str = ""
    stop_ini: float = 0.0

    @property
    def pts(self):
        if self.t_ent is None:
            return 0.0
        s = 1 if self.lado == "compra" else -1
        return (self.preco_sai - self.preco) * s - CUSTO

    @property
    def brl(self):
        return self.pts * RS_PT * self.contratos


def simula_dia(dia, regra, gerir=None, max_ops=None):
    """Roda uma regra num pregão. Devolve a lista de Trades (inclusive ordens que não encheram)."""
    m1 = carrega(dia, 0)
    d = pd.Timestamp(dia)
    m1d = m1[m1.index.normalize() == d]
    fim = m1d.index[m1d["ultima_continua"]].max() if m1d["ultima_continua"].any() else m1d.index.max()
    trades, aberta = [], None
    for t, ctx in contextos(dia):
        # 1) avança a posição/ordem pelos minutos da vela que acabou de fechar já foi feito no laço anterior
        if aberta is not None and aberta.t_ent is not None and gerir is not None:
            ctx.posicao = dict(lado=aberta.lado, preco=aberta.preco, stop=aberta.stop, alvo=aberta.alvo,
                               t_ent=aberta.t_ent, contratos=aberta.contratos)
            ns = gerir(ctx, ctx.posicao)
            if ns is not None:
                if aberta.lado == "compra" and ns > aberta.stop: aberta.stop = float(ns)
                if aberta.lado == "venda" and ns < aberta.stop: aberta.stop = float(ns)
        if aberta is None and t <= fim and (max_ops is None or len([x for x in trades if x.t_ent is not None]) < max_ops):
            ctx.ops_hoje = [x for x in trades if x.t_ent is not None]
            s = regra(ctx)
            if s:
                p = float(s.get("preco", ctx.hoje.close.iloc[-1]))
                ult = float(ctx.hoje.close.iloc[-1])
                if (s["lado"] == "compra" and p > ult) or (s["lado"] == "venda" and p < ult):
                    # limite "agressiva" (compra acima / venda abaixo do último preço) enche na hora = entrada a mercado
                    continue
                aberta =Trade(lado=s["lado"], contratos=int(s.get("contratos", 1)), t_sinal=t, preco=p,
                               stop=float(s["stop"]), alvo=(float(s["alvo"]) if s.get("alvo") is not None else None))
                aberta.stop_ini = aberta.stop
                trades.append(aberta)
        # 2) percorre os minutos da PRÓXIMA vela (de t até t+15)
        if aberta is not None:
            janela = m1d[(m1d.index >= t) & (m1d.index < t + pd.Timedelta(minutes=15))]
            for ts, r in janela.iterrows():
                if aberta.t_ent is None:
                    if ts >= aberta.t_sinal + VALIDADE:
                        aberta.motivo = "nao_encheu"; aberta = None; break
                    enche = (r.low <= aberta.preco - FURA) if aberta.lado == "compra" else (r.high >= aberta.preco + FURA)
                    if enche:
                        aberta.t_ent = ts
                    continue
                c = aberta.lado == "compra"
                bateu_stop = (r.low <= aberta.stop) if c else (r.high >= aberta.stop)
                bateu_alvo = aberta.alvo is not None and ((r.high >= aberta.alvo + FURA) if c else (r.low <= aberta.alvo - FURA))
                if bateu_stop:
                    px = min(r.open, aberta.stop) if c else max(r.open, aberta.stop)
                    aberta.t_sai, aberta.preco_sai, aberta.motivo = ts, px, "stop"; aberta = None; break
                if bateu_alvo:
                    aberta.t_sai, aberta.preco_sai, aberta.motivo = ts, aberta.alvo, "alvo"; aberta = None; break
                if ts >= fim:
                    aberta.t_sai, aberta.preco_sai, aberta.motivo = ts, r.close, "fim"; aberta = None; break
    if aberta is not None:
        if aberta.t_ent is None:
            aberta.motivo = "nao_encheu"
        else:
            aberta.t_sai, aberta.preco_sai, aberta.motivo = fim, float(m1d.loc[fim].close), "fim"
    return trades


def resumo(trades):
    feitos = [x for x in trades if x.t_ent is not None]
    return dict(ops=len(feitos), brl=round(sum(x.brl for x in feitos), 2),
                pts=round(sum(x.pts for x in feitos), 1),
                acertos=sum(x.pts > 0 for x in feitos),
                lista=[dict(lado=x.lado, sinal=str(x.t_sinal.time()), ent=str(x.t_ent.time()), preco=x.preco,
                            stop=x.stop_ini, alvo=x.alvo, sai=str(x.t_sai.time()), preco_sai=x.preco_sai,
                            motivo=x.motivo, pts=round(x.pts, 1), brl=round(x.brl, 2)) for x in feitos])
