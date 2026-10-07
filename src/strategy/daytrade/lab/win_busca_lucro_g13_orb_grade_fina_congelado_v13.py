# -*- coding: utf-8 -*-
"""CONGELADO -- copia byte-a-byte de `win_busca_lucro_g13_orb_grade_fina.py`
no momento em que a grade fina do IS terminou (2026-10-05), com os DEFAULTS
trocados para o vencedor composto da grade: `stop_family="tecnico",
range_minutos=5.0, stop_min_pontos=50.0, stop_max_pontos=140.0,
alvo_multiplo=3.0, confirma_pontos=0.0, buffer_entrada_pontos=20.0,
ttl_barras_entrada=10`.

## Por que este arquivo NAO foi usado para rodar um NOVO OOS-1

Esta e' a descoberta central da Geracao 13. A grade desta geracao cruzou 3
eixos (alvo_multiplo x definicao do stop x confirma_pontos) em 79 celulas
(75 da familia tecnico -- `stop_max_pontos` em {100,120,140,160,180} x
`alvo_multiplo` em {3,4,5} x `confirma_pontos` em {0,10,20,30,50} -- mais 4 da
familia stop FIXO na vizinhanca do vencedor). O vencedor composto (liquido>0 E
nao censurado por capital E win% != NEGATIVO E p_ruina MC <= 25%) foi
`stop_max=140, alvo=3x, confirma=0` -- e com `confirma_pontos=0` esta classe e'
COMPORTAMENTALMENTE IDENTICA a` `WinBuscaLucroG08OrbSobrevivencia` no seu
proprio vencedor (mesma deteccao de rompimento, mesma formula de geometria,
mesmo buffer/TTL). Os numeros do IS confirmam a identidade byte-a-byte:
liquido=+R$1.365,50, 121 trades, win=37,2%, p_ruina(MC)=24,8%, stop
mediano=145pts -- OS MESMOS QUATRO NUMEROS que `g08_orb_sobrevivencia`
registrou em `ORQUESTRACAO.md` (Geracao 8).

A G8 ja' RODOU o OOS-1 (jul-ago/2026) para esta EXATA estrategia e o
resultado esta' registrado: **MORTA** -- liquido=-R$158,50, 5 trades (as 5
PERDEDORAS), equity_min=R$91,50 (abaixo da margem crua R$100), 322 ordens
recusadas por capital, 39/44 pregoes sem trade (censura total). Rodar
`g13_oos1.py` sobre este kwargs produziria, de forma deterministica, o MESMO
resultado -- o motor/dado/parametros sao identicos, entao nao ha' nada novo a
observar. Gastar o "roda uma vez" do protocolo nesta repeticao seria
desperdicio, nao rigor: o numero ja' existe, medido, publicado.

**Por isso o OOS-1 desta geracao NAO foi re-executado.** O achado da G13 nao
e' "este candidato morre no OOS-1" (ja' sabiamos) -- e' que **uma grade de
79 celulas, 3 eixos, nao encontrou NENHUM candidato composto-aprovado
DIFERENTE do que a G8 ja' tinha achado com busca de 1 eixo so'.** Isso e'
evidencia POSITIVA de que o resultado da G8 e' robusto (nao e' artefato de
sub-amostragem do eixo `stop_max_pontos`), e evidencia NEGATIVA de que
`alvo_multiplo` e `confirma_pontos` nao abrem nenhuma rota de fuga do
penhasco -- ver `ORQUESTRACAO.md`, Geracao 13, para a tabela completa e os
3 cortes (CORTE 1/2/3) que mostram a vizinhanca inteira falhando.

Este arquivo existe por CONSISTENCIA com a convencao de toda geracao anterior
desta busca (congelar o vencedor ANTES de decidir o proximo passo) e para
documentar, em codigo, exatamente qual configuracao foi a vencedora composta
-- nao porque um OOS-1 novo tenha sido (ou precise ser) rodado nela.

## Resto da busca (nao vencedora, mas parte do achado)

- Familia ATR-M15 (`stop_family="atr"`): **NAO CONCLUIDA**. 3 celulas
  planejadas (`atr_multiplo` in {1,0; 1,5; 2,0}), mas o motor desta maquina
  mostrou um custo computacional anomalo e reproduzivel para esta familia
  sobre a janela IS inteira (122 pregoes) -- multiplas tentativas
  independentes nao terminaram em ate' 70-200s de CPU por celula, contra
  5,7s da familia tecnico no MESMO periodo. Nao e' fabricado nenhum numero
  para esta familia; ela fica como limitacao declarada desta geracao, nao
  como resultado negativo nem positivo. Ver ORQUESTRACAO.md para a nota
  completa.
- Familia stop FIXO (`stop_family="fixo"`): 4 celulas rodadas
  (`stop_fixo_pontos` in {100,120,140,160}), vizinhanca do vencedor
  (alvo=3x, confirma=0). Reproduziu os MESMOS numeros da familia tecnico
  celula a celula (100/120/140 identicos; 160 colapsa para censura total,
  identico ao `tec sm=160 conf=0`) -- confirma que, nesta janela, o teto do
  stop tecnico quase sempre BIND (a faixa de abertura do WIN@ e' maior que
  qualquer teto testado), entao as familias (a) e (c) sao redundantes entre
  si neste regime, nao eixos independentes.

Protocolo (ORQUESTRACAO.md / mandato do dono): este modulo so' existiria
para o OOS-1 (`g13_oos1.py`) e, se o OOS-1 passasse COM FOLGA, para o OOS-2
(`g13_oos2.py`) -- mas pela razao acima, nenhum dos dois foi executado nesta
geracao. O modulo `win_busca_lucro_g13_orb_grade_fina.py` (nao-congelado)
continua existindo para qualquer geracao futura que queira reusar/estender a
classe -- este CONGELADO nunca muda depois de escrito.
"""
from __future__ import annotations

from strategy.daytrade.lab.win_busca_lucro_g13_orb_grade_fina import (
    TTL_BARRAS_ENTRADA,
    WinBuscaLucroG13OrbGradeFina as _Base,
    atr_m15_causal,
)

__all__ = ["WinBuscaLucroG13OrbGradeFina", "atr_m15_causal"]


class WinBuscaLucroG13OrbGradeFina(_Base):
    """Mesma classe/logica da G13, defaults travados no vencedor composto
    do IS (ver docstring do modulo)."""

    def __init__(
        self,
        symbol: str | None = None,
        range_minutos: float = 5.0,
        stop_family: str = "tecnico",
        stop_min_pontos: float = 50.0,
        stop_max_pontos: float = 140.0,
        atr_multiplo: float = 1.5,
        atr_serie: dict | None = None,
        stop_fixo_pontos: float = 140.0,
        alvo_multiplo: float = 3.0,
        confirma_pontos: float = 0.0,
        buffer_entrada_pontos: float = 20.0,
        ttl_barras_entrada: int = TTL_BARRAS_ENTRADA,
        quantity: int = 1,
    ) -> None:
        super().__init__(
            symbol=symbol,
            range_minutos=range_minutos,
            stop_family=stop_family,
            stop_min_pontos=stop_min_pontos,
            stop_max_pontos=stop_max_pontos,
            atr_multiplo=atr_multiplo,
            atr_serie=atr_serie,
            stop_fixo_pontos=stop_fixo_pontos,
            alvo_multiplo=alvo_multiplo,
            confirma_pontos=confirma_pontos,
            buffer_entrada_pontos=buffer_entrada_pontos,
            ttl_barras_entrada=ttl_barras_entrada,
            quantity=quantity,
        )
