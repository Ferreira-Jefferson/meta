"""Ciclo 3 -> 4, GRUPO dos dias 2025-06-20 e 2025-07-11: achado comum aos dois (e a causa de a v3 ter perdido ambos).

ACHADO: a maioria das regras (FAZER e NAO_FAZER) de `regras/r_*.py` e dos ajustes c1/c2 tem uma clausula `ctx.ops_hoje -> None`
(foram escritas e testadas isoladas, como "regra da PRIMEIRA operacao do dia"). No robo composto `ctx.ops_hoje` e o que o ROBO ja
operou. Resultado: depois da 1a operacao do dia, os vetos com essa clausula SE DESLIGAM em silencio. Em 2025-06-20 a F2 operou
as 10:00 e, as 12:15, o veto `2024_05_16:N2 vende o fundo esticado` (queda de 2.090 pts = 5,9 ATR15 abaixo da abertura) calou; a F1
vendeu o fundo e foi stopada (-R$108,71). Em 2025-07-11 a compra das 09:15 foi stopada e, as 12:45, o mesmo veto (queda de 835 pts =
2,4 ATR15) calou; a F1 vendeu e foi stopada (-R$106,04). Nos dois dias o veto que existia e funcionaria estava desligado pelo estado do robo.

Candidatas (todas sobre o robo_v3; `APLICA[id](cfg)`):
  OPV   : todo NAO_FAZER passa a ser avaliado com ops_hoje = [] (vale o dia inteiro, nao so antes da 1a operacao).
  OPV_N2: so o veto `2024_05_16:N2 vende o fundo esticado` (o que atuou nos dois dias).
  OPF   : todo FAZER avaliado com ops_hoje = [] (as regras voltam a poder disparar depois da 1a operacao).
  OPVF  : as duas.
Regras puras: so usam o passado do instante da decisao.
"""
import dataclasses

N2_FUNDO = "2024_05_16:N2 vende o fundo esticado"


def _sem_ops(fn):
    def w(ctx):
        return fn(dataclasses.replace(ctx, ops_hoje=[]) if ctx.ops_hoje else ctx)
    w.__doc__ = fn.__doc__
    return w


def ap_opv(cfg):
    cfg.nf = [(n, _sem_ops(r), g) for n, r, g in cfg.nf]


def ap_opv_n2(cfg):
    assert any(n == N2_FUNDO for n, _, _ in cfg.nf)
    cfg.nf = [(n, _sem_ops(r), g) if n == N2_FUNDO else (n, r, g) for n, r, g in cfg.nf]


def ap_opf(cfg):
    cfg.fz = [(n, _sem_ops(r), g) for n, r, g in cfg.fz]


def ap_opvf(cfg):
    ap_opv(cfg); ap_opf(cfg)


APLICA = {"OPV": ap_opv, "OPV_N2": ap_opv_n2, "OPF": ap_opf, "OPVF": ap_opvf}
