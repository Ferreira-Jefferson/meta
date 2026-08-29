"""Registry de robôs de DAY TRADE.

Registry PRÓPRIO, não `strategy.registry` (ver docstring de
`strategy/daytrade/base.py`): `IntradayStrategy` não herda de `Strategy` de
propósito, então `discover_strategies()` nem varre o pacote `daytrade`, e um
robô de um símbolo só não pode competir no mesmo pódio que um robô diário de
carteira (capital/risco/instrumento incomparáveis). Por isso este catálogo é
uma lista EXPLÍCITA, não uma descoberta automática — cada entrada é uma
decisão deliberada de "este robô está pronto para aparecer no painel", não
"toda classe que existir em algum arquivo".

O SÍMBOLO é propriedade do ROBÔ, não do slot (`core.config.Slot` não declara
símbolo nenhum desde 2026-08-21): dois robôs registrados aqui podem operar
símbolos diferentes, e o slot só empresta o caixa/conta/processo — quem
decide o que negociar é a instância escolhida. Isto substitui três cópias do
mesmo mapa `{"gremah": Gremah}` que existiam soltas em `scripts/run_live.py`,
`dashboard/live_service.py` e `dashboard/live_control.py`: um catálogo
declarado em três lugares é um catálogo que diverge quando um robô novo
entra em só dois deles.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass

from strategy.daytrade.base import IntradayStrategy
from strategy.daytrade.lab.copa_win import CopaWin
from strategy.daytrade.lab.gremah import Gremah
from strategy.daytrade.lab.gremah_tick import GremahTick
from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker

# A ORDEM DESTE DICIONÁRIO É O PÓDIO DE DAY TRADE — o primeiro é o TOP-1.
#
# Diferente do ranking de swing (recalculado a cada 6h a partir do diário de
# backtests, ver `journal.reader.top_strategies_by_final_capital`), aqui a
# ordem é DECLARADA. Não é preguiça: robôs de day trade não são comparáveis
# por "capital final" de uma run — nem sempre rodam a mesma granularidade de
# dado ou o mesmo instrumento, então não existe uma run em que apareçam lado
# a lado. Um ranking automático teria de comparar números medidos em bases
# diferentes, que é a comparação desonesta que este projeto evita.
#
# 2026-08-28, decisão do dono: `copa_win` entra no pódio como TOP-2,
# empurrando `gremah_tick` para TOP-3 e `gremah` para TOP-4. Por quê:
# recalibração de `alvo_vol`/`stop_vol` (varredura de 400 células,
# `run_copa_score.CALIBRACAO_IS["WIN@"]`) confirmada em OOS explícito —
# diferente da calibração antiga (que caía de R$62,24 para R$3,84/pregão
# fora da amostra), o par (19,12) MELHOROU no OOS: R$54,86 → R$61,80/pregão,
# Calmar OOS 3,04, IS+OOS combinado R$56,82/pregão (ver a memória
# `copa-win-recalibracao-alvo-stop-2026-08-28`). Os kwargs de instanciação
# default (`_KWARGS_PADRAO` abaixo) replicam essa calibração; `teto_contratos`
# usa o teto OFICIAL da Copa 2025 (15) só como CEILING regulatório — o
# dimensionamento real por pregão vem de `margin_per_contract_brl` (margem
# WIN do projeto, ver a tabela de capital mínimo no `CLAUDE.md`), que ativa a
# realocação por caixa (`CopaWin.quantidade_por_entrada`) e reproduz o
# tamanho (1 contrato) com que a calibração foi de fato medida/confirmada.
#
# 2026-08-27, decisão do dono: `wdo_grid_reload_maker` sobe a TOP-1. Por quê:
#   - é o único robô de day trade do projeto com confirmação OOS que
#     SUSTENTA: R$148,89/pregão combinado, 89% de retenção IS→OOS, 30/30
#     blocos de 4 pregões positivos (o critério da própria Copa BTG,
#     `backtest/intraday/copa_score.py`) — quando esta ordem foi decidida,
#     nenhum outro candidato medido (CopaWin, ORB, M5 pré-registrada) tinha
#     passado nesse crivo (a recalibração/confirmação OOS do `copa_win`
#     acima é de 2026-08-28, um dia depois desta decisão);
#   - é o único cujo edge NÃO depende de prever direção — depende de
#     execução (a ordem ser preenchida no toque), o que sobrevive mesmo à
#     conclusão de que prever direção no WIN/WDO não funciona (linha da
#     Copa BTG, encerrada por refutação em 2026-08-26).
# O que a ordem NÃO afirma, e precisa ser dito junto: o número inteiro
# depende de uma taxa de preenchimento passivo (ordem parada tocada no
# nível) que NUNCA foi medida com dado de livro real — só o teste ao vivo
# com 1 contrato resolve isso, e até lá o robô é TOP-1 por qualidade de
# medição sobre o dado disponível, não por validação em dinheiro real. Ver
# `WdoGridReloadMaker.plain_summary`.
#
# 2026-08-28, decisão do dono: o default de `stop_ticks` da classe mudou de
# 16 para 4 (varredura completa profit_ticks/stop_ticks 1..20, ver a
# memória `wdof1-grid-1a20-encerrada-2026-08-28`) — T1 S4 domina T1 S16 em
# todas as métricas no IS. A confirmação OOS citada acima (R$148,89/pregão,
# 89% de retenção) descreve especificamente T1 S16, NÃO o default de então:
# T1 S4 nunca foi medido fora da amostra.
#
# 2026-08-29, REVERTIDO de volta para 16 (default da classe voltou a ser
# `stop_ticks=16`): a ressalva acima se confirmou, e de forma mais grave do
# que "não foi medido fora da amostra" — rodando o histórico salvo INTEIRO
# (177 pregões) com CAIXA REAL (não nocional), T1 S4 nunca sobrevive ao
# próprio histórico com capital realista: trava (cai abaixo do piso de
# capital pra abrir 1 contrato — item 1.14/3.9 de `LICOES_DE_PRODUCAO.md` —
# e NUNCA recupera dali em diante) em todo nível de capital testado até
# R$20.000, e só sobrevive com R$30.000 — mesmo assim fechando em
# +R$4.586,87 (quase só devolvendo o capital, líquido de R$-25.413,13 sobre
# R$30.000). T1 S16 sobrevive com só R$5.000 e fecha estável em +R$2.671,80
# a partir daí (idêntico de R$5.000 a R$30.000). Win rate no mesmo teste:
# 65,7% (S4) contra 90,3% (S16) — S4 é estruturalmente pior (a razão
# risco:retorno 1:4 exige >80% de acerto pra empatar; 65,7% fica abaixo
# disso), não uma diferença de amostra. Ver `scripts/daytrade/wdof1_stress_
# capital_real_historico_completo.py` e a memória `wdof1-stop-ticks-4-
# producao-2026-08-28` (atualizada com a reversão). O robô segue TOP-1, e a
# confirmação OOS original (R$148,89/pregão, 89% de retenção) volta a
# descrever o default em produção.
#
# 2026-08-22, decisão do dono (ordem original, agora TOP-3/TOP-4): entre
# `gremah_tick` e `gremah`, tick a tick não tem a ambiguidade "stop e alvo
# na mesma barra" que o M1 resolve por chute pessimista — um negócio tem um
# preço só; ao vivo, apaga a divergência de até 60s que `live/
# intraday_runtime.py` declara; e uma ordem-limite só é dada como tocada
# quando alguém NEGOCIOU no nível, em vez de bastar a faixa do minuto
# contê-lo. O que essa ordem não afirma: a `gremah_tick` tem medição
# própria em UM ativo (PMAM3) contra os dez da `gremah` — é por isso que
# `GremahTick.calibrated_setups()` oferece um só.
_ROBOTS: dict[str, type[IntradayStrategy]] = {
    WdoGridReloadMaker.name: WdoGridReloadMaker,
    CopaWin.name: CopaWin,
    GremahTick.name: GremahTick,
    Gremah.name: Gremah,
}

#: kwargs extras pra robôs cujo construtor exige parâmetro sem default
#: (`copa_win`: `teto_contratos` é obrigatório de propósito, ver a
#: docstring de `CopaWin.__init__` — herdar um número em silêncio ali seria
#: o mesmo erro que `Gremah` evita ao recusar símbolo sem calibração) OU que
#: precisam de dimensionamento dinâmico por caixa ligado explicitamente
#: (`wdo_grid_reload_maker`, ver abaixo). `cls()` sem isto explodiria (copa_win)
#: ou rodaria estático em 1 contrato pra sempre (wdo_grid_reload_maker) em
#: `list_daytrade_robots`/`get_daytrade_robot`/`symbols_for_robot`.
_KWARGS_PADRAO: dict[str, dict] = {
    # 2026-08-29, pedido do dono depois de descobrir que o CopaWin já escala
    # contratos com o caixa e a WDO F1 não ("wdo também tem que ser dinâmico,
    # conforme o capital cresce é natural aumentar os contratos"):
    # `WdoGridReloadMaker` SEMPRE pediu exatamente 1 contrato em produção
    # (`default_quantity=1` do perfil de futuro, `margin_per_contract_brl`
    # da estratégia nunca setado) — o modo dinâmico existe no construtor
    # desde 2026-08-27 mas era OPT-IN, nunca ligado aqui. `margin_per_
    # contract_brl=150.0` (margem real do WDO@) ativa a realocação por
    # caixa; `hard_cap_contratos=5` replica o teto REGULATÓRIO do perfil
    # (`profiles.py`, `max_open_contracts` do WDO@) — sem isto a estratégia
    # pediria mais contratos do que o motor aceita e toda entrada acima do
    # teto do motor seria recusada em silêncio (bug de setup já visto em
    # `wdof1_teto_por_risco_2026_08_29.py`, nunca reproduzir em produção).
    # `risco_pct_por_trade`/`point_value_brl=10.0` (item 3.9): mesmo
    # mecanismo do `copa_win` abaixo, mas NÃO o mesmo NÚMERO — copiar 5% sem
    # medir fez o capital R$5.000 (antes o piso limpo, ver item 3.11) quase
    # zerar (líquido −R$4.753,12, equity mínima R$246,88) porque o stop
    # desta estratégia é FIXO em R$ (16 ticks × R$0,50 × R$10/ponto = R$80/
    # contrato, CONSTANTE, diferente do stop por volatilidade do CopaWin) —
    # 5% de R$5.000 já libera 2-3 contratos enquanto o caixa ainda está
    # perto do piso, amplificando a sequência de perdas normal antes de
    # existir folga de verdade. Varredura de {1%, 2%, 3%, 5%} em
    # `scripts/daytrade/wdof1_calibracao_risco_pct_2026_08_29.py` achou 1%
    # como o único valor que NUNCA regride nenhum nível de capital já
    # medido (R$3.000/R$5.000 saem IDÊNTICOS ao dimensionamento estático de
    # antes) e ainda ganha de verdade em capital alto: R$50.000 fecha em
    # +R$13.095,09 (dinâmico) contra +R$2.671,80 (o que o 1-contrato-fixo
    # SEMPRE dava, em qualquer capital, antes desta mudança). 1% é a escolha
    # mais conservadora testada — 2%/3% renderam mais em alguns níveis
    # intermediários sem regredir nenhum dos testados, mas com margem de
    # segurança menor; ver a memória `wdo-dinamico-producao-2026-08-29` se
    # quiser reconsiderar depois de mais medição.
    WdoGridReloadMaker.name: dict(
        margin_per_contract_brl=150.0,
        hard_cap_contratos=5,
        risco_pct_por_trade=0.01,
        point_value_brl=10.0,
    ),
    CopaWin.name: dict(
        # `alvo_vol`/`stop_vol` e os demais campos abaixo são
        # `run_copa_score.CALIBRACAO_IS["WIN@"]` (recalibrado e confirmado em
        # OOS em 2026-08-28) — trocar aqui sem trocar lá (ou vice-versa) é o
        # catálogo divergindo da calibração que a memória documenta.
        janela_rompimento=10, alvo_vol=19.0, stop_vol=12.0, trail_vol=None,
        vol_min_ticks=8.0, fracao_entrada=1.0, aquecimento_barras=45,
        max_entradas_dia=10, entrada_maker=True, entrada_ttl_barras=15,
        # Teto OFICIAL da Copa 2025 (`run_copa_score.TETO_OFICIAL["WIN@"]`) —
        # regulamento, nunca medida; só entra como CEILING porque
        # `margin_per_contract_brl` abaixo já limita a entrada pelo caixa
        # real antes de chegar perto dele.
        teto_contratos=15,
        # Ativa a realocação por capital (ver a docstring da seção "Realocação
        # dinâmica por CAPITAL" em `copa_win.py`): sem isto o robô sempre
        # pediria `teto_contratos x fracao_entrada` contratos, ignorando o
        # caixa — os outros 3 robôs do pódio já escalam pelo caixa real
        # internamente, e o painel expõe robôs prontos pra dinheiro real, não
        # só pra competição. R$100 é a margem do WIN@ em
        # `backtest.intraday.profiles` (`_PROFILES["WIN@"].margin_per_contract_brl`,
        # fonte real -- não confundir com o WDO@, que é R$150; a tabela de
        # capital mínimo do `CLAUDE.md` tinha os dois trocados até 2026-08-28).
        # `MARGIN_BUFFER_FUTUROS` já é o default do robô. Com o caixa mínimo
        # real do WIN (R$200 = 2 lotes de margem), isto reproduz exatamente 1
        # contrato — o tamanho com que a calibração acima foi medida e
        # confirmada em OOS.
        margin_per_contract_brl=100.0,
        # 2026-08-29, item 3.9 de LICOES_DE_PRODUCAO.md: o teto por CAPITAL
        # acima limita ALAVANCAGEM, não RISCO — medido com R$3.000 reais nos
        # 182 pregões salvos de WIN@, um dia bom escalou a entrada de 12 pra
        # 15 contratos, e o MESMO stop de sempre (agora sobre mais contratos)
        # perdeu R$3.457,50 num trade só: R$3.000,00 → R$68,50 (-97,7%), sem
        # nunca ficar negativa, quase zerando com margem/reserva funcionando
        # exatamente como desenhadas. `risco_pct_por_trade` é o SEGUNDO teto,
        # independente — a entrada usa o MENOR entre os dois (ver a docstring
        # de `CopaWin.__init__`). 5% É PROVISÓRIO: testado 2%-10% no mesmo
        # histórico (todos terminaram positivos, nenhum chegou perto de
        # zerar — ver `scripts/daytrade/copawin_dimensionamento_por_risco_
        # 2026_08_29.py`), mas nenhum valor específico passou por uma
        # varredura própria nem por confirmação OOS ainda.
        risco_pct_por_trade=0.05,
    ),
}


@dataclass(frozen=True)
class DaytradeRobotInfo:
    """Metadata de exibição de um robô de day trade — para o select do
    painel, sem precisar do terminal MT5 nem de conta criada."""

    key: str
    label: str
    symbol: str
    version: str
    description: str
    #: Posição no pódio declarado (1 = TOP-1). Sai da ordem de `_ROBOTS`, e
    #: existe como CAMPO para o painel poder rotular a escolha — antes a ordem
    #: só existia implícita na lista, e uma ordem que ninguém enxerga não é
    #: uma recomendação, é um acaso de iteração.
    rank: int = 1
    #: `"m1"` ou `"tick"` — a granularidade em que este robô foi medido (ver
    #: `IntradayStrategy.feed_kind`). No painel é o que distingue dois robôs
    #: do mesmo desenho.
    feed_kind: str = "m1"
    #: Ver `IntradayStrategy.is_futuro`. Sai daqui (não de instanciar a
    #: classe de novo) para `dashboard/app.py` poder decidir a fórmula de
    #: capital mínimo (lote de ação x margem por contrato) sem importar a
    #: classe do robô.
    is_futuro: bool = False


def _description(cls: type) -> str:
    doc = inspect.getdoc(cls) or ""
    if not doc:
        return f"Robô {cls.__name__} (sem docstring)."
    primeira = doc.strip().splitlines()[0].strip(" .")
    return primeira + "."


def list_daytrade_robots() -> list[DaytradeRobotInfo]:
    """Um `DaytradeRobotInfo` por robô registrado, na ordem do PÓDIO (TOP-1
    primeiro) — ver o comentário sobre `_ROBOTS` no topo do módulo.

    Instancia com os defaults de cada classe (mais `_KWARGS_PADRAO`, para quem
    exige parâmetro sem default) só para ler `.symbol` — leitura pura, sem
    I/O (mesmo espírito de `strategy.registry.list_strategies`)."""
    infos = []
    for posicao, (key, cls) in enumerate(_ROBOTS.items(), start=1):
        robo = cls(**_KWARGS_PADRAO.get(key, {}))
        infos.append(DaytradeRobotInfo(
            key=key, label=key, symbol=robo.symbol,
            version=getattr(robo, "version", "0.1"),
            description=_description(cls),
            rank=posicao,
            feed_kind=getattr(cls, "feed_kind", "m1"),
            is_futuro=getattr(cls, "is_futuro", False),
        ))
    return infos


def get_daytrade_robot(key: str, symbol: str | None = None) -> IntradayStrategy:
    """Resolve um robô de day trade por chave, com os PARÂMETROS DEFAULT da
    classe — quem precisa de parâmetros diferentes instancia direto.

    `symbol` escolhe o ativo. `None` usa o default da classe. Passar um ativo
    que o robô não aceita é erro DELE, não daqui: `Gremah.__init__` levanta
    `ValueError` para símbolo sem calibração própria, em vez de herdar a
    calibração de outro papel — é esse comportamento que impede o painel de
    ligar um robô num ativo nunca medido.

    Este parâmetro entrou em 2026-08-22, quando o painel passou a abrir N
    robôs de day trade (um por ativo): até então "o robô" e "o ativo" eram a
    mesma escolha, porque o registry só sabia instanciar com o default.

    `KeyError` (nunca um default silencioso) se a chave não existir: um id
    desconhecido chegando de form/CLI é catálogo desatualizado ou form
    adulterado, e escolher um robô por chute operaria dinheiro real com o
    robô errado."""
    if key not in _ROBOTS:
        raise KeyError(
            f"robô de day trade desconhecido: {key!r} — disponíveis: "
            f"{', '.join(sorted(_ROBOTS))}"
        )
    cls = _ROBOTS[key]
    kwargs = dict(_KWARGS_PADRAO.get(key, {}))
    if symbol is not None:
        kwargs["symbol"] = symbol
    return cls(**kwargs)


def symbols_for_robot(key: str) -> tuple[str, ...]:
    """Ativos que este robô aceita operar, na ordem em que ele os declara.

    Sai de `calibrated_setups()` na CLASSE quando ela oferece esse método (é o
    caso da `gremah`: cada ativo tem alvo/stop medidos separadamente, e a
    ordem é lucro OOS decrescente). Um robô de ativo único simplesmente não
    define o método, e aqui ele vira a tupla de um elemento com o símbolo
    default — o painel não precisa saber qual dos dois casos é.

    Ordenar por capital mínimo é do CHAMADOR, não daqui: depende do preço de
    hoje, e `strategy/` não busca preço (regra 1 do AGENTS.md).
    """
    if key not in _ROBOTS:
        raise KeyError(
            f"robô de day trade desconhecido: {key!r} — disponíveis: "
            f"{', '.join(sorted(_ROBOTS))}"
        )
    cls = _ROBOTS[key]
    setups = getattr(cls, "calibrated_setups", None)
    if callable(setups):
        return tuple(s.symbol for s in setups())
    return (cls(**_KWARGS_PADRAO.get(key, {})).symbol,)
