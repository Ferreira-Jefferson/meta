"""Dimensionamento de posicao pela formula de Kelly -- traduzir CONVICCAO em
TAMANHO por uma conta, nao por um percentual escolhido de cabeca.

Kelly cru: f* = p - (1-p)/b, com `p` = probabilidade de acerto e `b` = razao
ganho medio / perda media (payoff). Ele assume os dois parametros EXATOS.
Numa tese discricionaria (Camilo/Williams), os dois sao ESTIMATIVA humana --
nao uma frequencia medida em milhares de trades, como o breakeven empirico
de `LICOES_DE_PRODUCAO.md` (la o n e' de milhares e o IC e' estreito; aqui o
n e' UMA tese, e o "IC" e' so' o quanto o dono confia no proprio
julgamento). Kelly CHEIO sobre uma estimativa incerta e' a mesma familia de
erro que a secao do deslize do TP nativo em `CLAUDE.md` documenta: um otimo
que mora exatamente no ponto onde o modelo e' mais otimista que a realidade
nao e' um otimo -- e' o motivo de `fracao_kelly` ter default fixo em 0.5
(meio-Kelly), NUNCA 1.0. Meio-Kelly e' o ajuste padrao da industria para
erro de estimacao dos parametros, nao um numero escolhido a dedo.

## A regra que realmente salvou Larry Williams em 1987 nao foi o Kelly

Williams venceu o Robbins World Cup de 1987 (US$10 mil -> US$1.137.600,
+11.376%) arriscando ate ~30% do capital por operacao -- Kelly CHEIO, sem
fracionar, o oposto do que este modulo recomenda acima. No crash de outubro
(Black Monday, Dow -22,6% num pregao so'), a conta foi de US$2,1 milhoes a
US$750 mil -- >60% de drawdown -- e SOBREVIVEU. O que impediu a ruina nao
foi o tamanho Kelly: foi uma segunda regra, independente, que ele aplicava
por CIMA do Kelly: dimensionava pela PIOR perda ja registrada pelo proprio
sistema (nao a perda MEDIA, que e' o que a maioria usa) e exigia que o
capital aguentasse 150% daquele pior caso antes de autorizar mais uma
unidade. E' `teto_por_pior_caso` abaixo.

Este projeto NAO recomenda replicar o tamanho de risco de Williams (30% por
operacao contraria toda a cultura de risco daqui -- ver o incidente de
2026-08-28 que zerou a conta, `LICOES_DE_PRODUCAO.md`). O que vale a pena
herdar e' a FORMA da regra: duas amarras independentes (Kelly fracionario
E' o teto do pior caso), nao uma so' -- porque foi a segunda que segurou a
conta quando a primeira, sozinha, teria estourado.
"""
from __future__ import annotations


def kelly_fraction(prob_acerto: float, payoff_ratio: float) -> float:
    """Fracao de Kelly CRUA. Retorna `0.0` quando a edge estimada e' <= 0
    (f* negativo) -- Kelly negativo pede posicao vendida ou nenhuma
    posicao, e este modulo so' dimensiona ENTRADA COMPRADA: a tese
    discricionaria (Camilo/Williams) e' sempre no sentido da observacao, nao
    um par long/short."""
    if not 0.0 < prob_acerto < 1.0:
        raise ValueError(f"kelly_fraction: `prob_acerto` tem de estar em (0, 1), recebeu {prob_acerto!r}.")
    if payoff_ratio <= 0:
        raise ValueError(f"kelly_fraction: `payoff_ratio` tem de ser > 0, recebeu {payoff_ratio!r}.")
    f = prob_acerto - (1.0 - prob_acerto) / payoff_ratio
    return max(f, 0.0)


def tamanho_meio_kelly(
    prob_acerto: float,
    payoff_ratio: float,
    *,
    fracao_kelly: float = 0.5,
    teto_pct: float = 0.40,
) -> float:
    """Kelly FRACIONARIO, capado em `teto_pct` do capital.

    `teto_pct` default (0.40) e' o limite superior que o proprio Camilo
    pratica por conviccao (20-40%, ver `CLAUDE.md`) -- nao e' recomendacao
    deste modulo, e' o unico numero desse tipo que existe com auditoria
    academica por tras (volatilidade ~5x o mercado). Mudar o teto e' decisao
    do dono a cada chamada, nunca um default silencioso enterrado no codigo.

    Retorna `0.0` quando `kelly_fraction` ja devolveu 0 -- sem edge positiva
    estimada, o tamanho certo e' NAO abrir a tese, e este modulo nao inventa
    um piso minimo para disfarcar isso.
    """
    if not 0.0 < fracao_kelly <= 1.0:
        raise ValueError(f"tamanho_meio_kelly: `fracao_kelly` tem de estar em (0, 1], recebeu {fracao_kelly!r}.")
    if not 0.0 < teto_pct <= 1.0:
        raise ValueError(f"tamanho_meio_kelly: `teto_pct` tem de estar em (0, 1], recebeu {teto_pct!r}.")
    f = kelly_fraction(prob_acerto, payoff_ratio) * fracao_kelly
    return min(f, teto_pct)


def max_unidades_pelo_pior_caso(
    capital_disponivel_brl: float,
    pior_perda_historica_brl_por_unidade: float,
    *,
    multiplicador: float = 1.5,
) -> int:
    """Quantas UNIDADES (contratos, lotes, ou o tamanho-padrao da tese) o
    capital atual aguenta abrir, pela regra de sobrevivencia de Larry
    Williams: o capital tem de cobrir `multiplicador` vezes a PIOR perda ja
    registrada pelo sistema NUMA unidade antes de autorizar mais uma -- nao
    a perda MEDIA. Williams usava 1,5 (150%); foi essa reserva, e nao o
    tamanho agressivo do Kelly que ele tambem usava, que impediu a ruina no
    crash de 1987 (ver a nota do modulo).

    Retorna `0` quando o capital nao cobre nem uma unidade nessa margem --
    e' o resultado CORRETO nesse caso (nao abrir posicao nenhuma), nao um
    piso minimo artificial."""
    if capital_disponivel_brl <= 0:
        raise ValueError(f"max_unidades_pelo_pior_caso: `capital_disponivel_brl` tem de ser > 0, recebeu {capital_disponivel_brl!r}.")
    if pior_perda_historica_brl_por_unidade <= 0:
        raise ValueError(f"max_unidades_pelo_pior_caso: `pior_perda_historica_brl_por_unidade` tem de ser > 0, recebeu {pior_perda_historica_brl_por_unidade!r}.")
    if multiplicador <= 1.0:
        raise ValueError(
            f"max_unidades_pelo_pior_caso: `multiplicador` tem de ser > 1.0 (Williams usava "
            f"1.5), recebeu {multiplicador!r} -- <= 1.0 nao e' reserva, e' so' cobrir o "
            f"proprio pior caso uma unica vez, sem margem."
        )
    exigencia_por_unidade = multiplicador * pior_perda_historica_brl_por_unidade
    return int(capital_disponivel_brl // exigencia_por_unidade)
