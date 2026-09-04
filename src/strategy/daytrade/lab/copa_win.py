"""`copa_win` — rompimento de faixa intradiaria no mini-indice (WIN),
desenhado para a Copa BTG Trader.

## Por que ROMPIMENTO aqui, e nao a grade maker que o repo ja conhece

Pela economia MEDIDA do instrumento, nao por gosto. Um round-trip custa
R$0,50/contrato de tarifa (`FUTURES_FEE_ROUND_TRIP_BRL`) mais a slippage de
1 tick por perna a mercado. No WIN o tick vale 5 pontos (R$1,00/contrato),
entao:

| | custo de 1 round-trip | em ticks do WIN |
|---|---|---|
| tarifa | 2,5 pontos | 0,50 tick |
| entrada a mercado (taker) | 5 pontos | 1,00 tick |
| saida no alvo (ordem parada, maker) | 0 | 0 |
| **total** | **7,5 pontos** | **1,5 tick** |

Um alvo de 1 tick (5 pontos) NASCE negativo. E' o oposto do WDO, onde a
mesma tarifa e' um decimo de tick e o giro alto se paga -- foi essa
economia que motivou uma grade maker de muitos trades pequenos para WDO@
(`CopaWdo`), mas a tentativa zerou a conta sob capital real de day trade e
foi removida em 2026-08-27; WDO@ hoje nao tem estrategia propria nesta
familia.
Dai o desenho: no WIN o robo precisa de POUCOS trades GRANDES, cada um
pagando 1,5 tick de pedagio para tentar capturar dezenas de ticks. Foi essa
assimetria que fechou a decisao do dono de nao ter uma estrategia so' para os
dois ativos.

Calibra o alvo pela VOLATILIDADE recente do proprio pregao, nao por um numero
fixo de pontos: o range diario mediano do WIN e' 2.968 pontos, mas o intervalo
p25–p75 vai de 2.296 a 4.054 (182 pregoes medidos) — um alvo fixo seria
grande demais em metade dos dias e pequeno demais na outra.

## Tudo reinicia no pregao

Nenhum indicador de NIVEL de preco atravessa a virada: a faixa, a
volatilidade, o stop e o alvo saem exclusivamente das barras de HOJE. Nao e'
zelo — a serie continua (`WIN@`) tem emenda de rolagem, e o salto de preco
dela (+742, +786, +630, +510 pontos nos 4 dias de rolagem medidos) se esconde
DENTRO do ruido overnight normal (mediano 499, p95 1.746), ou seja, e'
indetectavel por outlier. A unica defesa estrutural e' nunca deixar um nivel
de preco cruzar a sessao.

## O teto de contratos e' ENTRADA, nunca constante

`teto_contratos` e' obrigatorio no construtor e TODO tamanho e' fracao dele
(`_qtd`). Os numeros de 2025 (WIN 15) podem mudar antes de 14/09/2026; um
literal aqui viraria um robo que so' sabe operar as regras do ano passado.

## Realocacao dinamica por CAPITAL (2026-08-27, ADITIVA e OPT-IN)

`teto_contratos` continua sendo o teto OFICIAL da competicao -- ele NUNCA
muda de significado. O que passou a existir e' um segundo teto, o que o
CAIXA REAL do dono sustenta agora (`contracts_from_capital`, `strategy.
daytrade.base`), e a entrada usa o MENOR dos dois. Por default
(`margin_per_contract_brl=None`) este segundo teto nao existe e o
comportamento e' byte-a-byte o de antes: so' quem passa `margin_per_
contract_brl` explicito ativa a realocacao (mesma convencao aditiva de
`config_for`/`contracts_from_capital`).

Por que nao reaproveitar `teto_contratos` para isto: ele e' o teto da
COMPETICAO (pode ser MAIOR do que o capital atual sustenta -- o robo
comeca com R$200 e o teto oficial e' 15 contratos), enquanto o teto por
capital so' pode ENCOLHER a entrada, nunca cresce-la acima do que a
competicao permite. Um caixa que crescesse o suficiente para sustentar
mais contratos do que `teto_contratos` nao deve fazer o robo violar o
regulamento -- e' por isso que a formula e' `min(teto_contratos,
contracts_from_capital(...))`, nunca so' o segundo termo.

`on_capital_update` segue o MESMO padrao ja usado por `Gremah`
(`_cash_atual_brl`, atualizado pelo motor logo antes de cada `on_bar`,
comeca em 0.0): antes da primeira barra real, ou quando o replay de
`warm_start_calibration` roda sem `cash_brl` (default `None`, comportamento
antigo), o hook nunca e' chamado e o robo nao "sabe" quanto caixa tem -- e
o piso de 1 contrato ja existente (`max(1, round(...))`) cobre esse caso
sem precisar de um segundo estado. Desde 2026-09-03 (LICOES_DE_PRODUCAO.md
item 3.14), `warm_start_calibration` TAMBEM chama `on_capital_update` a
cada barra do replay quando o CHAMADOR passa `cash_brl` --
`live/intraday_runtime.py::_start_session` passa o caixa real
(`initial_capital + realized_pnl`) num restart no meio do pregao, entao o
teto dinamico volta a valer desde a PRIMEIRA entrada recalibrada.

## Teto por RISCO por trade (2026-08-29, ADITIVA -- item 3.9 de LICOES_DE_PRODUCAO.md)

O teto por CAPITAL acima limita ALAVANCAGEM/margem, nao RISCO -- os dois so'
coincidem por acidente no tamanho em que foram medidos. Medido com R$3.000
reais nos 182 pregoes salvos de WIN@: um dia bom (12 contratos) cresceu o
caixa 43%, o teto por margem escalou a proxima entrada pra 15 contratos, e o
MESMO `stop_vol` de sempre -- agora sobre mais contratos -- perdeu
R$3.457,50 num trade so': R$3.000,00 -> R$68,50 (-97,7%), sem nunca ficar
negativa, quase zerando com margem/reserva funcionando exatamente como
desenhadas (nenhuma ordem foi recusada por capital nesses 5 trades).

`risco_pct_por_trade` (`strategy.daytrade.base.contracts_from_risk`) e' o
SEGUNDO teto, independente do primeiro -- a entrada usa o MENOR entre
`teto_contratos`, o teto por CAPITAL (se `margin_per_contract_brl` setado) e
o teto por RISCO (se `risco_pct_por_trade` setado). Nenhum substitui o outro:
alavancagem alta com risco baixo so' abre o que o risco permite; risco alto
com margem curta so' abre o que a margem permite. Recalculado a CADA entrada
com o `stop_vol x volatilidade_do_dia` DESSA entrada especifica (nunca
ancorado num caixa de um momento passado -- ver a nota abaixo sobre por que
isso importa).

Uma alternativa foi testada e REFUTADA antes desta (2026-08-29,
`scripts/daytrade/copawin_ratchet_skim_teste_2026_08_29.py`): "separar" uma
fatia do caixa a cada marco de crescimento (ex.: +60%) e parar de conta-la
como caixa operacional. Nao funciona -- a fatia e' so' contabil (nunca sai da
MESMA posicao/MESMA conta) e fica CONGELADA em reais; quando o caixa recupera
de uma perda, ela vira uma fracao cada vez MENOR do caixa atual, e o tamanho
da entrada reinfla sem nenhum novo gatilho. Em parametros mais sensiveis
testados isso deixou a conta em EQUITY NEGATIVA -- pior que nao fazer nada.

`None` (default) desliga -- comportamento IDENTICO ao de antes desta secao.

## Saida defensiva de RECUO (2026-09-03, ADITIVA e OPT-IN)

Mesma ideia pedida pelo dono e ja implementada em `WdoGridReloadMaker`
(`strategy.daytrade.lab.wdo_grid_reload_maker`, ver a docstring do parametro
`defesa_ativa` la' para o precedente completo): "se a posicao chegou perto do
stop e depois voltou perto do alvo, fecha antecipado" -- generalizado em dois
parametros, `defesa_gatilho_stop_pct` (fracao da distancia do STOP que precisa
ser sofrida, em excursao ADVERSA nao realizada, para a defesa ARMAR) e
`defesa_alvo_proximidade_pct` (depois de armada, fracao da distancia RESTANTE
ate o alvo abaixo da qual a posicao fecha antecipada). Ver a docstring do
parametro `defesa_ativa` em `__init__` abaixo para a formula exata.

Testado PRIMEIRO na WDO F1 e achado DEGENERADO la': com o alvo de producao de
1 tick, nao existe estado intermediario entre "0% do alvo" e "100% do alvo"
(bateu) -- a defesa nunca via a condicao de fechar antes do motor ja ter
fechado a posicao pelo caminho normal (ver `wdof1_defesa_recuo_sweep_2026_09_
03.py`). O `CopaWin` e' o candidato natural para medir a ideia de verdade: o
alvo de producao tem `alvo_vol=19,0` (19 volatilidades de referencia, dezenas
de pontos de espaco real) contra o stop de `stop_vol=12,0` -- "quase la'" e'
um estado que existe de fato nesta config, ao contrario da WDO F1. Ver
`scripts/daytrade/copawin_defesa_recuo_sweep_2026_09_03.py` para a varredura
que mede se/quanto isto ajuda.

`defesa_ativa=False` (default) preserva o comportamento BYTE A BYTE de antes
desta secao -- os dois `*_pct` so' importam com `defesa_ativa=True`.

## Corte por PERSISTENCIA no lado ADVERSO (2026-09-03, ADITIVO e OPT-IN)

Achado RETROSPECTIVO de `scripts/daytrade/copawin_duracao_operacoes_2026_09_
03.py` (secao bonus): entre os trades resolvidos por STOP ou TARGET, ja em
10% da DURACAO EVENTUAL do trade (medida so' DEPOIS que ele fecha) estar do
lado adverso ja indicava 84,4% de chance de terminar em STOP; entre 70%-90%
da duracao isso vira ~100%. O problema: "% da duracao EVENTUAL" so' se
conhece DEPOIS que o trade fecha -- nao da' pra usar essa forma ao vivo,
porque a duracao total e' desconhecida enquanto o trade esta' aberto (seria
olhar o futuro).

Esta secao e' a versao CAUSAL do mesmo achado -- so' usa o que ja e' conhecido
no momento, nunca o futuro. Em vez de "fracao da duracao EVENTUAL", mede
"fracao das barras JA VIVIDAS desde a entrada": quantas barras M1 ja se
passaram (`IntradayOpenPosition.bars_held`, campo que o motor JA preenche --
nao recalculado aqui) e, dessas, quantas ja estiveram do lado adverso (isto
SIM precisa de contador proprio -- ver `self._barras_adversas` abaixo --
porque `bars_held` conta barras, nao diz quantas foram do lado ruim).

Regra (`corte_persistencia_ativo=True`): se `pos.bars_held >= corte_
persistencia_min_barras` (aquecimento minimo por trade -- evita disparar com
2-3 barras de ruido logo apos a entrada) E `barras_adversas / pos.bars_held >=
corte_persistencia_frac_adverso`, fecha a posicao AGORA (`Exit(reason=
"corte_persistencia")`) -- aceita um prejuizo MENOR agora em vez de arriscar o
STOP cheio depois, que e' exatamente o que o achado retrospectivo mediu.

Lado adverso de uma barra: `bar.close < entry_price` (comprado) ou `bar.close
> entry_price` (vendido) -- usa o FECHAMENTO, nao o pior preco da barra
(`bar.low`/`bar.high`, que e' o que `defesa_ativa` usa para excursao). Escolha
deliberada: aqui a pergunta e' "onde o mercado ASSENTOU", nao "qual foi o pior
momento" -- excursao intrabarra e' o dominio da defesa de recuo (distancia),
nao deste mecanismo (persistencia no tempo). Fechamento exatamente igual a
`entry_price` conta como NAO adverso (mais conservador -- nao empurra o
contador por um empate).

Contagem (`self._barras_adversas`, chave `(side, entry_ts)`, mesma convencao
de `self._defesa_armada`): a CADA `on_bar` com a posicao aberta, primeiro
CHECA a condicao acima usando o contador ACUMULADO ATE a barra anterior (por
isso a checagem so' roda quando `pos.bars_held > 0` -- na primeira barra em
que a posicao aparece, `bars_held=0` e nao ha' barra anterior nenhuma para o
contador descrever), so' DEPOIS atualiza o contador com o lado da barra
CORRENTE (para a PROXIMA chamada). Isto mantem o contador e `pos.bars_held`
descrevendo exatamente a MESMA janela de barras passadas em toda checagem --
nunca conta a barra corrente contra si mesma no numerador (mesma disciplina
anti-look-ahead de `self._faixa` no `on_bar` principal). Resetado em `on_
session_start`, mesmo lugar que ja reseta `self._defesa_armada`.

Prioridade entre os dois mecanismos de saida quando os dois estao ativos:
`corte_persistencia` e' checado PRIMEIRO (ver `on_bar`) porque e' mais
simples/direto -- "desistir" nao depende de olhar a distancia ate o alvo, so'
de quanto tempo a posicao ja resistiu do lado errado. Se nenhum dos dois
dispara, cai no `_trailing` normal, igual antes desta secao.

`corte_persistencia_ativo=False` (default) preserva o comportamento BYTE A
BYTE de antes desta secao. `corte_persistencia_frac_adverso=1.0` e' o valor
NEUTRO quando ligado sem querer varrer a grade inteira -- 100% das barras
passadas do lado adverso e' o caso mais raro/extremo, entao serve como "quase
nunca dispara sozinho" em vez de um valor arbitrario.
"""
from __future__ import annotations

from collections import deque

import pandas as pd

from strategy.daytrade.base import (
    MARGIN_BUFFER_FUTUROS,
    AdjustStop,
    Bar,
    Enter,
    EnterLimit,
    Exit,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
    contracts_from_capital_com_reserva,
    contracts_from_risk,
    no_tick,
)


class CopaWin(IntradayStrategy):
    """Rompimento de faixa rolante intradiaria, com alvo e stop escalados
    pela volatilidade do proprio pregao e stop que so' aperta.

    Uma posicao por vez (o motor recusa `Enter` com posicao aberta), com
    tamanho igual a uma FRACAO do teto de contratos da competicao."""

    name = "copa_win"
    version = "0.1"
    symbol = "WIN@"
    is_futuro = True
    # A saida por alvo e' ordem PARADA no nivel (maker, sem slippage); a
    # entrada e' a mercado de proposito -- nao existe ordem-limite que compre
    # um rompimento PARA CIMA (uma compra parada acima do preco viraria
    # execucao imediata; uma abaixo espera o preco VOLTAR, que e' o sinal
    # oposto). O robo paga 1 tick para entrar e nao paga nada para sair no
    # alvo: e' a assimetria honesta deste desenho, nao um favor do motor.
    target_fills_as_maker = True
    feed_kind = "m1"
    #: Pernas MAKER por round-trip -- 1 com entrada a mercado (so' o alvo e'
    #: ordem parada), 2 com `entrada_maker=True`. Multiplicador do portao G7
    #: (pedagio de 1 tick em todo fill maker): um backtest em barra M1 nao
    #: enxerga POSICAO NA FILA, entao assume que a ordem parada preencheu
    #: sempre que o preco tocou o nivel. Se o edge morre com 1 tick de
    #: pedagio, ele era ficcao de fila. Vira atributo de INSTANCIA no
    #: `__init__`, porque depende de `entrada_maker`.
    pernas_maker = 1

    def __init__(
        self,
        teto_contratos: int,
        symbol: str = "WIN@",
        tick_size: float = 5.0,
        point_value_brl: float = 0.20,
        fracao_entrada: float = 0.5,
        janela_rompimento: int = 20,
        alvo_vol: float = 2.0,
        stop_vol: float = 1.0,
        vol_min_ticks: float = 2.0,
        trail_vol: float | None = 1.0,
        aquecimento_barras: int = 15,
        max_entradas_dia: int = 10,
        entrada_maker: bool = False,
        entrada_ttl_barras: int = 5,
        perda_max_dia_pontos: float | None = None,
        margin_per_contract_brl: float | None = None,
        margin_buffer: float = MARGIN_BUFFER_FUTUROS,
        risco_pct_por_trade: float | None = None,
        defesa_ativa: bool = False,
        defesa_gatilho_stop_pct: float = 0.0,
        defesa_alvo_proximidade_pct: float = 0.0,
        corte_persistencia_ativo: bool = False,
        corte_persistencia_min_barras: int = 0,
        corte_persistencia_frac_adverso: float = 1.0,
    ):
        """`teto_contratos`: teto de contratos SIMULTANEOS da competicao.
        Obrigatorio e sem default -- e' o unico limitador de tamanho num
        ambiente de margem infinita, e herdar um numero em silencio aqui seria
        o mesmo erro que `Gremah` evita ao recusar simbolo sem calibracao.

        `fracao_entrada`: tamanho da posicao como fracao do teto. `0.5` com
        teto 12 = 6 contratos; com teto 15 = 8. O robo NUNCA le 12 nem 15.

        `janela_rompimento`: barras M1 da faixa rolante. Tambem e' a janela da
        volatilidade de referencia -- uma so', porque as duas medem a mesma
        coisa ("o que este pregao andou nos ultimos N minutos").

        `alvo_vol`/`stop_vol`: alvo e stop em multiplos dessa volatilidade.

        `vol_min_ticks`: nao opera enquanto a volatilidade de referencia for
        menor que isto (em ticks). Um "rompimento" de faixa achatada e'
        quantizacao do tick, nao sinal -- mesmo motivo do `min_range_price` da
        `OpeningRangeBreakout`, so' que medido em volatilidade em vez de range
        absoluto.

        `trail_vol`: aperta o stop para `trail_vol` volatilidades atras do
        preco corrente, uma vez que o trade esteja a favor. `None` desliga.
        O motor so' aceita stop MAIS protetor (`AdjustStop`), entao isto nunca
        afrouxa nada.

        `aquecimento_barras`: barras da abertura sem operar. A abertura do WIN
        concentra o leilao e o repique dele; entrar em cima disso e' apostar
        no ruido de formacao de preco.

        `max_entradas_dia`: teto de entradas por pregao -- limita quantas
        vezes o pedagio de 1,5 tick e' pago num dia sem sinal bom.

        `entrada_maker`: entra por RETESTE em vez de perseguir o rompimento.
        Rompeu para cima, deixa uma compra PARADA no nivel rompido (o teto da
        faixa) e espera o preco voltar nele. Existe por medicao (2026-08-25):
        com entrada a mercado o custo por round-trip no WIN e' ~10,4 pontos
        por contrato contra ~10,6 pontos de edge BRUTO -- praticamente todo o
        ganho vai embora no spread da entrada, e a ordem parada nao paga esse
        tick. O preco disso e' real e nao e' estimavel a priori: o rompimento
        que nunca retesta simplesmente nao e' operado, e o que retesta pode
        ser justamente o rompimento fraco. E' hipotese a MEDIR, por isso e'
        parametro e nao o desenho.

        `entrada_ttl_barras`: barras que a ordem de reteste espera antes de o
        motor cancela-la. O robo so' re-arma depois do prazo, sincronizado com
        o motor -- re-armar a cada barra substituiria a propria ordem e o
        prazo nunca se cumpriria.

        `perda_max_dia_pontos`: perda-limite do pregao, em pontos por
        contrato do teto (`pontos x point_value x teto`). `None` (default)
        desliga: a funcao objetivo e' lucro total, e um freio diario e' uma
        hipotese a MEDIR na varredura, nao uma premissa.

        `margin_per_contract_brl`: ATIVA a realocacao dinamica por capital
        (ver a secao do modulo). `None` (default) -- comportamento IDENTICO
        ao de antes desta rodada: `quantidade_por_entrada` so' olha
        `teto_contratos x fracao_entrada`, nunca o caixa. Setado, o teto
        efetivo de contratos passa a ser `min(teto_contratos,
        contracts_from_capital(caixa_atual, margin_per_contract_brl,
        margin_buffer))` -- o caixa real NUNCA deixa a entrada ultrapassar o
        teto oficial da competicao, so' pode encolhe-la abaixo dele.

        `margin_buffer`: multiplicador de seguranca sobre a margem por
        contrato, mesmo parametro/mesmo default de `contracts_from_capital`
        (`MARGIN_BUFFER_FUTUROS=2.0`) -- so' importa quando
        `margin_per_contract_brl` esta setado.

        `risco_pct_por_trade`: ATIVA o teto por RISCO (ver a secao do modulo,
        `strategy.daytrade.base.contracts_from_risk`). `None` (default) --
        desligado, comportamento IDENTICO ao de antes desta secao. Setado, o
        teto efetivo de contratos vira `min(teto_efetivo_atual,
        contracts_from_risk(caixa_atual, risco_pct_por_trade,
        stop_vol x volatilidade_do_dia x point_value_brl))` -- so' pode
        ENCOLHER a entrada, nunca cresce-la acima do que os outros tetos
        permitem.

        `defesa_ativa`/`defesa_gatilho_stop_pct`/`defesa_alvo_proximidade_pct`
        (2026-09-03, pedido do dono -- saida defensiva de RECUO, ver a secao
        do modulo "Saida defensiva de RECUO"): "chegou perto do stop e depois
        voltou perto do alvo, fecha a posicao". ADITIVO e OPT-IN --
        `defesa_ativa=False` (default) preserva o comportamento BYTE A BYTE
        de antes; os dois `*_pct` so' importam com `defesa_ativa=True`.

        Mecanica, avaliada a CADA `on_bar` com posicao aberta (nunca antes de
        o fill ser confirmado -- este robo so' chama `_entrada`/`EnterLimit`
        quando `positions` esta vazio, entao qualquer posicao vista aqui ja
        esta' preenchida):

        1. ARMAR (uma vez por trade, nunca desarma depois): a posicao sofreu
           excursao ADVERSA (nao realizada) de pelo menos
           `defesa_gatilho_stop_pct x dist_stop_pontos`, onde
           `dist_stop_pontos = |entry_price - current_stop|` (derivado do
           stop REAL da posicao -- pode ja ter sido apertado por `_trailing`
           -- nunca de `stop_vol x vol` recalculado, que e' so' o valor NO
           MOMENTO da entrada). A excursao usa o preco mais ADVERSO DENTRO da
           barra M1 (`bar.low` comprado, `bar.high` vendido), nao so' o
           `close` -- o pico de dor pode ter acontecido e revertido dentro da
           mesma barra.
        2. FECHAR (so' depois de armada): a distancia RESTANTE ate o alvo, em
           FRACAO da distancia total entrada->alvo, cai a
           `defesa_alvo_proximidade_pct` ou abaixo -- formula exata:
           `dist_restante_pontos / dist_total_pontos <= defesa_alvo_
           proximidade_pct`, onde `dist_restante_pontos` usa o preco mais
           FAVORAVEL da barra (`bar.high` comprado, `bar.low` vendido,
           espelhando o preco mais adverso do passo 1) e nunca fica negativo
           (clampado em 0). Fecha via `Exit(reason="defesa_recuo")`,
           IGNORANDO o `_trailing` normal que rodaria para a MESMA posicao
           nesta chamada (a defesa tem prioridade).

        Diferente da WDO F1 (alvo de 1 tick, sem estado intermediario): aqui
        o alvo tem dezenas de pontos de espaco real (`alvo_vol=19,0` na
        config de producao), entao "quase la'" e' um estado que de fato
        existe -- se a defesa dispara ou nao, e quanto ajuda, e' o que
        `scripts/daytrade/copawin_defesa_recuo_sweep_2026_09_03.py` mede.

        Estado de armada mora em `self._defesa_armada` (dict, chave
        `(side, entry_ts)`), NUNCA em `IntradayOpenPosition.metadata` --
        `metadata` e' um snapshot READ-ONLY reconstruido do zero a cada
        chamada (`machine.py::_position_view`, `metadata=dict(pos.metadata)`
        e' uma COPIA) -- resetado em `on_session_start`, mesmo lugar que ja
        reseta `self._faixa`/`self._barras_hoje`/etc (sem memoria entre
        pregoes). `(side, entry_ts)` basta porque este robo so' abre UMA
        posicao por vez (o motor recusa `Enter`/`EnterLimit` com posicao
        aberta).

        `corte_persistencia_ativo`/`corte_persistencia_min_barras`/
        `corte_persistencia_frac_adverso` (2026-09-03, pedido do dono -- corte
        por PERSISTENCIA no lado adverso, ver a secao do modulo "Corte por
        PERSISTENCIA no lado ADVERSO"): versao CAUSAL (so' usa o que ja e'
        conhecido no momento) do achado retrospectivo de `copawin_duracao_
        operacoes_2026_09_03.py` -- "estar do lado adverso por uma fracao alta
        da vida do trade ja indica STOP com alta probabilidade". Mede
        PERSISTENCIA no tempo (quantas barras JA VIVIDAS estiveram do lado
        errado), NAO distancia de preco -- mecanismo DIFERENTE de `defesa_
        ativa` acima (que mede o quao perto do stop/alvo o preco chegou); os
        dois coexistem como parametros independentes desta mesma classe.

        Mecanica exata, ver a secao do modulo para a formula/justificativa
        completa: a CADA `on_bar` com posicao aberta, se `pos.bars_held >=
        corte_persistencia_min_barras` E a fracao de barras JA PASSADAS que
        estiveram do lado adverso (`self._barras_adversas[chave] / pos.
        bars_held`, so' avaliada quando `pos.bars_held > 0`) for `>=
        corte_persistencia_frac_adverso`, fecha via `Exit(reason=
        "corte_persistencia")` -- checado ANTES de `defesa_ativa` (ver
        `on_bar`), prioridade por ser o mecanismo mais simples ("desistir" nao
        depende de olhar o alvo).

        `corte_persistencia_ativo=False` (default) preserva o comportamento
        BYTE A BYTE de antes desta secao -- `corte_persistencia_min_barras`/
        `corte_persistencia_frac_adverso` so' importam com `corte_persistencia_
        ativo=True`. `corte_persistencia_frac_adverso=1.0` e' o valor NEUTRO
        (100% das barras passadas do lado adverso e' o extremo raro, entao
        "quase nunca dispara sozinho" mesmo se `corte_persistencia_ativo`
        fosse ligado sem varrer a grade)."""
        if teto_contratos < 1:
            raise ValueError(
                f"copa_win: `teto_contratos` tem de ser >= 1, veio {teto_contratos!r}. "
                "O teto e' entrada de configuracao (as regras da Copa podem mudar "
                "antes de 14/09/2026), nunca constante no codigo."
            )
        self.symbol = symbol
        self.teto_contratos = int(teto_contratos)
        self.tick_size = float(tick_size)
        self.point_value_brl = float(point_value_brl)
        self.fracao_entrada = float(fracao_entrada)
        self.janela_rompimento = int(janela_rompimento)
        self.alvo_vol = float(alvo_vol)
        self.stop_vol = float(stop_vol)
        self.vol_min_ticks = float(vol_min_ticks)
        self.trail_vol = None if trail_vol is None else float(trail_vol)
        self.aquecimento_barras = int(aquecimento_barras)
        self.max_entradas_dia = int(max_entradas_dia)
        self.entrada_maker = bool(entrada_maker)
        self.entrada_ttl_barras = int(entrada_ttl_barras)
        self.perda_max_dia_pontos = perda_max_dia_pontos
        self.margin_per_contract_brl = (
            None if margin_per_contract_brl is None else float(margin_per_contract_brl)
        )
        self.margin_buffer = float(margin_buffer)
        if risco_pct_por_trade is not None and risco_pct_por_trade <= 0:
            raise ValueError(
                f"copa_win: `risco_pct_por_trade` tem que ser positivo ou `None`, "
                f"veio {risco_pct_por_trade!r}."
            )
        self.risco_pct_por_trade = (
            None if risco_pct_por_trade is None else float(risco_pct_por_trade)
        )
        self.defesa_ativa = bool(defesa_ativa)
        self.defesa_gatilho_stop_pct = float(defesa_gatilho_stop_pct)
        self.defesa_alvo_proximidade_pct = float(defesa_alvo_proximidade_pct)
        self.corte_persistencia_ativo = bool(corte_persistencia_ativo)
        self.corte_persistencia_min_barras = int(corte_persistencia_min_barras)
        self.corte_persistencia_frac_adverso = float(corte_persistencia_frac_adverso)
        # Atualizado por `_entrada` logo antes de pedir `quantidade_por_
        # entrada` -- distancia do STOP desta entrada especifica, em pontos.
        # So' importa quando `risco_pct_por_trade` esta setado.
        self._ultimo_stop_dist_pontos: float | None = None
        # Estado de "ja armou a defesa de recuo" por POSICAO -- chave
        # `(side, entry_ts)`, mora no self por causa do snapshot read-only de
        # `IntradayOpenPosition` (ver a docstring do parametro `defesa_ativa`
        # acima). Resetado em `on_session_start`. So' cresce (nunca desarma
        # dentro do mesmo trade) -- zerado inteiro a cada pregao.
        self._defesa_armada: dict[tuple[str, pd.Timestamp], bool] = {}
        # Contador de "quantas das barras JA PASSADAS desde a entrada
        # estiveram do lado adverso" -- chave `(side, entry_ts)`, mesma
        # convencao de `self._defesa_armada` (ver a docstring do parametro
        # `corte_persistencia_ativo` acima). So' cresce dentro do mesmo trade
        # (nunca desconta), resetado inteiro em `on_session_start`.
        self._barras_adversas: dict[tuple[str, pd.Timestamp], int] = {}
        # A entrada parada e' a SEGUNDA perna maker (a primeira e' o alvo) --
        # ver o comentario do atributo de classe.
        self.pernas_maker = 2 if self.entrada_maker else 1

        # Atualizado por `on_capital_update`, chamado pelo motor logo antes
        # de cada `on_bar` -- 0.0 so' antes da primeira barra real. Desde
        # 2026-09-03 (LICOES_DE_PRODUCAO.md item 3.14) o warm start (replay
        # de `warm_start_calibration`) TAMBEM chama `on_capital_update`, uma
        # vez por barra do replay, quando o chamador passa `cash_brl` --
        # sem esse argumento (default `None`) o replay ainda nao chama o
        # hook, mesmo padrao antigo de `Gremah._cash_atual_brl`. So' importa
        # quando `margin_per_contract_brl` esta setado.
        self._cash_atual_brl = 0.0

        self._faixa: deque[Bar] = deque(maxlen=self.janela_rompimento)
        self._barras_hoje = 0
        self._entradas_hoje = 0
        self._encerrado_hoje = False
        # Barras desde que a ordem de reteste foi armada; `None` = nenhuma em
        # pe'. Espelha `IntradaySessionMachine.resting_limit_bars_waited` de
        # fora.
        self._espera: int | None = None

    # ---------- tamanho: sempre fracao do teto ----------------------------

    @property
    def quantidade_por_entrada(self) -> int:
        """`max(1, round(teto_efetivo x fracao))` -- piso de 1 contrato
        porque uma entrada de zero contratos nao e' "menor", e' nenhuma.

        `teto_efetivo` e' `teto_contratos` (comportamento de sempre) quando
        `margin_per_contract_brl` e' `None`. Setado, vira `min(teto_
        contratos, contracts_from_capital_com_reserva(caixa_atual,
        margin_per_contract_brl, margin_buffer))` -- o caixa real do robo
        so' pode ENCOLHER a entrada abaixo do teto oficial da competicao,
        nunca cresce-la acima dele (ver a secao do modulo).

        `contracts_from_capital_com_reserva` (nao a versao pura) desde
        2026-08-28, MESMA reserva de seguranca que `backtest.intraday.
        machine.IntradaySessionMachine._cap_capital_atual` aplica no teto
        agregado do motor -- ver `strategy.daytrade.base.RESERVA_CAIXA_
        SEGURANCA`. Consistencia entre "o que a estrategia pede" e "o que o
        motor deixa abrir" e' o ponto inteiro: pedir mais do que o motor vai
        aceitar so' produziria recusas (`OrderRejected(reason=
        "capital_insuficiente")`) em vez de uma entrada menor e aceita.

        `contracts_from_risk` (2026-08-29, item 3.9) aplica DEPOIS, se
        `risco_pct_por_trade` estiver setado -- so' pode ENCOLHER `teto_
        efetivo` mais ainda, nunca cresce-lo. Alavancagem (o teto acima) e
        risco (este) medem coisas diferentes e nenhum substitui o outro; ver
        a secao do modulo para o numero real que motivou isto (R$3.000 ->
        R$68,50 num trade so', sem este segundo teto)."""
        teto_efetivo = self.teto_contratos
        if self.margin_per_contract_brl is not None:
            teto_por_caixa = contracts_from_capital_com_reserva(
                self._cash_atual_brl, self.margin_per_contract_brl, self.margin_buffer,
            )
            teto_efetivo = min(teto_efetivo, teto_por_caixa)
        if self.risco_pct_por_trade is not None and self._ultimo_stop_dist_pontos is not None:
            stop_reais_por_contrato = self._ultimo_stop_dist_pontos * self.point_value_brl
            if stop_reais_por_contrato > 0:
                teto_por_risco = contracts_from_risk(
                    self._cash_atual_brl, self.risco_pct_por_trade, stop_reais_por_contrato,
                )
                teto_efetivo = min(teto_efetivo, teto_por_risco)
        return max(1, round(teto_efetivo * self.fracao_entrada))

    def on_capital_update(self, cash_brl: float) -> None:
        """Guarda o caixa acumulado (`config.initial_capital + machine.
        realized_pnl`, ver `IntradayStrategy.on_capital_update`) para
        `quantidade_por_entrada` usar na proxima entrada -- so' tem efeito
        quando `margin_per_contract_brl` e/ou `risco_pct_por_trade` estao
        setados."""
        self._cash_atual_brl = cash_brl

    @property
    def perda_max_dia_brl(self) -> float | None:
        if self.perda_max_dia_pontos is None:
            return None
        return abs(self.perda_max_dia_pontos) * self.point_value_brl * self.teto_contratos

    # ---------- ciclo do pregao -------------------------------------------

    def on_session_start(self, session_date) -> None:
        """Zera TUDO. E' aqui que a regra "nenhum nivel de preco atravessa a
        virada" vira codigo: a faixa do pregao anterior nao sobrevive, entao a
        emenda de rolagem da serie continua nunca entra num nivel."""
        self._faixa = deque(maxlen=self.janela_rompimento)
        self._barras_hoje = 0
        self._entradas_hoje = 0
        self._encerrado_hoje = False
        self._defesa_armada = {}
        self._barras_adversas = {}
        self._espera = None

    # ---------- decisao ----------------------------------------------------

    def _volatilidade(self) -> float:
        """Amplitude MEDIA das barras da faixa. Media (nao mediana) de
        proposito: aqui a barra grande isolada e' informacao, nao ruido a
        descartar -- e' ela que diz que o alvo precisa ser maior agora."""
        if not self._faixa:
            return 0.0
        return sum(b.high - b.low for b in self._faixa) / len(self._faixa)

    def _corte_persistencia_deve_fechar(self, pos: IntradayOpenPosition, bar: Bar) -> bool:
        """`True` se o corte por persistencia (`corte_persistencia_ativo`)
        manda fechar `pos` AGORA -- ver a docstring do parametro
        `corte_persistencia_ativo` em `__init__` para a mecanica completa. So'
        chamada quando `self.corte_persistencia_ativo` ja e' `True`.

        Ordem importa: CHECA primeiro com o contador acumulado ATE a barra
        anterior (`pos.bars_held > 0` -- na barra em que a posicao aparece
        pela primeira vez, `bars_held=0`, e nao ha' barra anterior para o
        contador descrever, entao nunca dispara ali), so' DEPOIS atualiza o
        contador com o lado da barra CORRENTE -- a barra corrente nunca conta
        contra si mesma no numerador (mesma disciplina anti-look-ahead de
        `self._faixa` no `on_bar` principal)."""
        chave = (pos.side, pos.entry_ts)
        adversas = self._barras_adversas.get(chave, 0)
        dispara = (
            pos.bars_held > 0
            and pos.bars_held >= self.corte_persistencia_min_barras
            and (adversas / pos.bars_held) >= self.corte_persistencia_frac_adverso - 1e-9
        )
        adverso_agora = (
            (bar.close < pos.entry_price) if pos.side == "long"
            else (bar.close > pos.entry_price)
        )
        if adverso_agora:
            self._barras_adversas[chave] = adversas + 1
        return dispara

    def _defesa_deve_fechar(self, pos: IntradayOpenPosition, bar: Bar) -> bool:
        """`True` se a defesa de recuo (`defesa_ativa`) manda fechar `pos`
        AGORA -- ver a docstring do parametro `defesa_ativa` em `__init__`
        para a mecanica completa e a formula exata. So' chamada quando
        `self.defesa_ativa` ja e' `True`."""
        if pos.current_stop is None:
            return False  # sem stop, nada a derivar
        eps = 1e-9
        chave = (pos.side, pos.entry_ts)
        dist_stop_pontos = abs(pos.entry_price - pos.current_stop)
        if dist_stop_pontos <= 0:
            return False

        if not self._defesa_armada.get(chave, False):
            preco_adverso = bar.low if pos.side == "long" else bar.high
            excursao_pontos = (
                (pos.entry_price - preco_adverso) if pos.side == "long"
                else (preco_adverso - pos.entry_price)
            )
            excursao_pontos = max(0.0, excursao_pontos)
            gatilho_pontos = self.defesa_gatilho_stop_pct * dist_stop_pontos
            if excursao_pontos + eps >= gatilho_pontos:
                self._defesa_armada[chave] = True
            else:
                return False  # ainda nao armou -- nao ha' o que checar de alvo

        if pos.current_target is None:
            return False  # armada, mas sem alvo declarado -- nao ha' proximidade a medir
        dist_total_pontos = abs(pos.current_target - pos.entry_price)
        if dist_total_pontos <= 0:
            return False
        preco_favoravel = bar.high if pos.side == "long" else bar.low
        dist_restante_pontos = (
            (pos.current_target - preco_favoravel) if pos.side == "long"
            else (preco_favoravel - pos.current_target)
        )
        dist_restante_pontos = max(0.0, dist_restante_pontos)
        fracao_restante = dist_restante_pontos / dist_total_pontos
        return fracao_restante <= self.defesa_alvo_proximidade_pct + eps

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._barras_hoje += 1
        acoes: list[IntradayAction] = []
        faixa_pronta = len(self._faixa) == self.janela_rompimento
        vol = self._volatilidade()

        try:
            if self._encerrado_hoje:
                return acoes

            limite = self.perda_max_dia_brl
            if limite is not None and session_pnl_brl <= -limite:
                # Encerra o dia. Nao emite `Exit`: quem esta comprado tem stop
                # proprio, e um `Exit` a mercado aqui pagaria slippage para
                # fechar uma posicao que pode estar a caminho do alvo. O freio
                # e' sobre ABRIR de novo.
                self._encerrado_hoje = True
                return acoes

            if positions:
                self._espera = None
                if self.corte_persistencia_ativo:
                    # Checado ANTES de `defesa_ativa` -- prioridade decidida
                    # na docstring do parametro `corte_persistencia_ativo`
                    # em `__init__` ("desistir" e' mais simples/direto, nao
                    # depende de olhar a distancia ate o alvo).
                    for pos in positions:
                        if self._corte_persistencia_deve_fechar(pos, bar):
                            return [Exit(reason="corte_persistencia")]
                if self.defesa_ativa:
                    # Prioridade sobre o trailing normal desta chamada -- ver
                    # a docstring do parametro `defesa_ativa` em `__init__`.
                    for pos in positions:
                        if self._defesa_deve_fechar(pos, bar):
                            return [Exit(reason="defesa_recuo")]
                acoes.extend(self._trailing(positions, bar, vol))
                return acoes

            if self._espera is not None:
                # Ordem de reteste ainda viva no motor -- substitui-la agora
                # zeraria o prazo dela a cada barra.
                self._espera += 1
                if self._espera < self.entrada_ttl_barras:
                    return acoes
                self._espera = None

            if not faixa_pronta or self._barras_hoje <= self.aquecimento_barras:
                return acoes
            if self._entradas_hoje >= self.max_entradas_dia:
                return acoes
            if vol < self.vol_min_ticks * self.tick_size:
                return acoes

            teto_faixa = max(b.high for b in self._faixa)
            piso_faixa = min(b.low for b in self._faixa)
            if bar.close > teto_faixa:
                acoes.append(self._entrada("long", bar.close, teto_faixa, vol))
            elif bar.close < piso_faixa:
                acoes.append(self._entrada("short", bar.close, piso_faixa, vol))
            return acoes
        finally:
            # SEMPRE no fim, e depois de a decisao ja ter sido tomada: a barra
            # corrente nao pode fazer parte da faixa contra a qual ela propria
            # e' comparada (seria comparar o preco com ele mesmo, e nenhum
            # rompimento existiria).
            self._faixa.append(bar)

    def _entrada(self, lado: str, preco: float, nivel_rompido: float,
                 vol: float) -> Enter | EnterLimit:
        """`preco` e' o fechamento que rompeu; `nivel_rompido` e' a borda da
        faixa. A mercado, o robo entra no fechamento; por reteste, espera
        parado na borda -- e stop/alvo saem sempre do preco em que ele
        REALMENTE entraria, nunca de um preco de referencia diferente."""
        self._entradas_hoje += 1
        base = nivel_rompido if self.entrada_maker else preco
        alvo_dist = self.alvo_vol * vol
        stop_dist = self.stop_vol * vol
        # Guardado ANTES de `quantidade_por_entrada` ser lida abaixo (dentro
        # de `Enter(...)`/`EnterLimit(...)`) -- e' o teto por RISCO desta
        # entrada especifica, ver `IntradayStrategy`/modulo.
        self._ultimo_stop_dist_pontos = stop_dist
        if lado == "long":
            stop = no_tick(base - stop_dist, self.tick_size)
            alvo = no_tick(base + alvo_dist, self.tick_size)
        else:
            stop = no_tick(base + stop_dist, self.tick_size)
            alvo = no_tick(base - alvo_dist, self.tick_size)
        side = "long" if lado == "long" else "short"
        metadata = {"vol_ref": vol, "entrada_n": self._entradas_hoje,
                    "nivel_rompido": nivel_rompido}
        if not self.entrada_maker:
            return Enter(side=side, quantity=self.quantidade_por_entrada,
                         initial_stop=stop, initial_target=alvo,
                         metadata=metadata, reason=f"rompimento_{lado}")
        self._espera = 0
        return EnterLimit(
            side=side,
            limit_price=no_tick(base, self.tick_size),
            quantity=self.quantidade_por_entrada,
            initial_stop=stop,
            initial_target=alvo,
            ttl_bars=self.entrada_ttl_barras,
            metadata=metadata,
            reason=f"reteste_{lado}",
        )

    def _trailing(self, positions: list[IntradayOpenPosition], bar: Bar,
                  vol: float) -> list[IntradayAction]:
        """Stop arrastado a `trail_vol` volatilidades do preco corrente.

        Nao devolve nada se o novo nivel nao for mais protetor que o atual --
        o motor recusaria de qualquer forma (`AdjustStop` so' aperta), e
        emitir a acao mesmo assim encheria o diario de ruido."""
        if self.trail_vol is None or vol <= 0:
            return []
        acoes: list[IntradayAction] = []
        for pos in positions:
            if pos.side == "long":
                novo = no_tick(bar.close - self.trail_vol * vol, self.tick_size)
                if pos.current_stop is None or novo > pos.current_stop:
                    acoes.append(AdjustStop(new_stop=novo))
            else:
                novo = no_tick(bar.close + self.trail_vol * vol, self.tick_size)
                if pos.current_stop is None or novo < pos.current_stop:
                    acoes.append(AdjustStop(new_stop=novo))
            break  # uma posicao por vez neste desenho; o motor aplica a todas
        return acoes
