"""WDO F1 + TENDENCIA como fonte de CONFIRMACAO (pedido do dono,
2026-08-28) -- rodado SO' no pregao de hoje, o dia em que a conta perdeu
dinheiro de verdade.

## A pergunta

Hoje, 2026-08-28, o `wdo_grid_reload_maker` operou ao vivo pela primeira
vez e a conta terminou em -R$298,60. Forense confirmado no MT5 (deals
`475209177`..`475216399`, magic 862399285, simbolo WDOU26):

    11:58:53  COMPRA 1 @ 5204,0     abre LONG
    11:58:53  VENDA  1 @ 5203,5     fecha LONG          -R$  5,00
    11:58:59  VENDA  1 @ 5203,5     abre SHORT
    11:59:04  VENDA  1 @ 5204,0     abre SHORT DE NOVO  (o bug do dia)
    12:59:46  COMPRA 2 @ 5218,5     stop nos dois       -R$295,00

O robo ficou VENDIDO e o mercado SUBIU 15 pontos (30 ticks) na hora
seguinte. A pergunta do dono: uma leitura de TENDENCIA teria mudado essa
decisao?

Com a ressalva que este arquivo repete em toda saida, porque ela e' o
contexto sem o qual o numero engana: **os -R$295 nao vieram do sinal**.
Vieram de DUAS entradas independentes numa conta que so' tinha margem
para uma (ver `LICOES_DE_PRODUCAO.md` e a docstring de
`WdoGridReloadMaker`). Um unico contrato teria perdido R$147,50. Filtro
de tendencia nenhum conserta entrada duplicada -- isso ja foi corrigido
no motor, por teto dinamico de capital. O que se mede aqui e' outra
coisa, menor e legitima: **aquela venda, sozinha, teria sido autorizada?**

## A tendencia como PERCENTUAL, nao como veto

Pedido explicito do dono: "a tendencia nao e' certeza de nao operar, deve
ser mais uma fonte de confirmacao que pode ser encarada como percentual
de indicacao de entrar ou nao".

Medida escolhida: **razao de eficiencia com sinal** (Kaufman) sobre os
fechamentos de MINUTO da propria sessao --

    ER_janela = (fecha_agora - fecha_inicio) / soma(|variacoes minuto a minuto|)

Ela vive em [-1, +1] por construcao, sem constante arbitraria de escala:
+1 e' subida em linha reta, -1 e' queda em linha reta, 0 e' vaivem que
nao foi a lugar nenhum. E' literalmente "que fracao do movimento foi
direcional" -- ou seja, ja E' um percentual, que e' o que foi pedido.
Um deslocamento em pontos (a alternativa obvia) exigiria dividir por um
K escolhido a dedo, e K escolhido a dedo em cima de UM dia e' o comeco
de um overfit.

Por que sobre MINUTO e nao sobre tick: no tick a soma do caminho e'
enorme (~130 mil negocios hoje) e o ER de qualquer janela desaba para
~0,002 -- mede microestrutura, nao tendencia. Tendencia e' conceito de
prazo mais longo que o do robo, que e' justamente o ponto de usa-la como
confirmacao EXTERNA ao sinal.

## As quatro janelas

Todas ancoradas no tempo DECORRIDO da sessao, exatamente como pedido:

    abertura : desde o primeiro negocio do pregao   (100% do decorrido)
    ult_50   : ultimos 50% do tempo decorrido
    ult_25   : ultimos 25% do tempo decorrido
    ult_10   : ultimos 10% do tempo decorrido

Sao janelas que CRESCEM junto com o pregao: as 10:00, "ultimos 25%" sao
15 minutos; as 16:00, sao 105. E' o desenho pedido, e tem uma consequencia
que o resultado precisa carregar: cedo no pregao as janelas curtas tem
poucos minutos e ficam ruidosas. Janela com menos de `MIN_MINUTOS_JANELA`
fechamentos e' declarada INDEFINIDA (peso redistribuido entre as outras),
nunca chutada como zero -- zero e' uma afirmacao ("nao ha direcao"), e
nao havia informacao para afirma-la.

O escore combinado S e' a media ponderada das janelas definidas, e vira
percentual por lado:

    indicacao_long  = 50 + 50 * S        (S = +1  ->  100% para comprar)
    indicacao_short = 50 - 50 * S        (S = +1  ->    0% para vender)

## Os modos, e por que dois deles sao CONTROLE e nao candidato

    bloqueia   -- leitura fiel do pedido ("entrar ou nao"): o lado que a
                  estrategia escolheu so' e' armado se a indicacao dele
                  alcancar o limiar.
    direciona  -- extensao minha, nao pedida: antes de desistir, tenta o
                  lado OPOSTO. A tendencia deixa de so' vetar e passa a
                  sugerir para onde ir.
    invertido  -- CONTROLE. Identico a `bloqueia`, com o sinal do escore
                  TROCADO: exige que a tendencia seja CONTRA o lado. Se
                  render tanto quanto o certo, a tendencia nao esta
                  carregando informacao nenhuma -- o efeito e' de armar
                  menos, nao de armar melhor.
    aleatorio  -- CONTROLE. Bloqueia na MESMA TAXA que o filtro de
                  tendencia bloqueou, mas por sorteio com semente. Isola
                  "menos trades" de "trades melhores", que e' a confusao
                  que arruina este tipo de medicao. Varias sementes, para
                  a comparacao ter dispersao em vez de um numero solto.

`limiar=0` reproduz a baseline byte a byte e e' a primeira linha de toda
tabela, fora da ordenacao.

## Limite deste arquivo, dito antes do numero

**UM pregao nao e' uma medicao.** n=1, sem dispersao entre dias, e o dia
foi escolhido DEPOIS de se saber que deu errado -- amostra selecionada
pela conclusao. Pior: com alvo de 1 tick e stop de 4, o resultado do dia
inteiro e' quase inteiramente decidido por QUANTOS TRADES PERDEM (cada
perda apaga ~4 ganhos). A baseline de hoje perde 2. Toda a diferenca que
qualquer filtro pode mostrar aqui e' uma reordenacao de 2 eventos -- por
isso a secao 2 lista esses trades um a um, com o percentual que o filtro
teria visto em cada um. Essa lista e' a evidencia; a tabela de P&L e'
ilustracao.

Serve para responder "teria mudado a decisao de hoje?". Nao serve para
promover, aposentar ou recalibrar nada.

Uso: `python -u scripts/daytrade/wdof1_tendencia_confirmacao_2026_08_28.py`
"""
from __future__ import annotations

import bisect
import random
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.machine import IntradayBacktestConfig  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import (  # noqa: E402
    LinhaResultado,
    linha_de_resultado,
    num_br,
    tabela,
)
from market_data_intraday.tick_bars import ticks_to_degenerate_bars  # noqa: E402
from strategy.daytrade.base import Bar, EnterLimit, IntradayAction, IntradayOpenPosition  # noqa: E402
from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker  # noqa: E402

SYMBOL = "WDO@"
#: Contrato REAL negociado hoje (o que aparece nos deals do MT5). A serie
#: continua `WDO@` reporta tick 0,001 e preco fora da grade -- ver
#: `SymbolProfile.price_tick_size`. Para UM dia, o contrato real e' a
#: fonte certa e e' literalmente o que a conta operou.
SYMBOL_REAL = "WDOU26"
DIA = datetime(2026, 8, 28)

#: Mesma base nocional do lab desta frente (`wdo_grid_reload_f1_lab.py`):
#: futuro nao tem caixa real neste teste, o limitador e'
#: `max_open_contracts`. Com o capital REAL de R$300 o robo fica INERTE
#: hoje (a reserva de seguranca de 2026-08-28 exige >R$375 para 1
#: contrato) -- rodar assim mediria o portao de capital, nao a tendencia,
#: que e' a pergunta. O capital usado sai impresso no cabecalho.
CAPITAL_NOCIONAL = 1_000_000.0
MAX_OPEN_CONTRATOS = 1
_ECONOMIA_WDO = (0.01, 0.001)

#: Fracoes do tempo DECORRIDO da sessao, na ordem em que o dono pediu.
JANELAS: tuple[tuple[str, float], ...] = (
    ("abertura", 1.00),
    ("ult_50", 0.50),
    ("ult_25", 0.25),
    ("ult_10", 0.10),
)

#: Minimo de fechamentos de minuto para uma janela ser considerada
#: DEFINIDA. Abaixo disso o ER e' ruido de 2 pontos, nao tendencia.
MIN_MINUTOS_JANELA = 3

#: Pesos testados. "igual" nao privilegia prazo nenhum; "recencia" da mais
#: voz ao que acabou de acontecer. Duas leituras plausiveis do pedido,
#: reportadas lado a lado em vez de uma escolhida em silencio.
PESOS = {
    "igual": {"abertura": 0.25, "ult_50": 0.25, "ult_25": 0.25, "ult_10": 0.25},
    "recencia": {"abertura": 0.10, "ult_50": 0.20, "ult_25": 0.30, "ult_10": 0.40},
}

LIMIARES = (50.0, 55.0, 60.0, 65.0, 70.0)
MODOS_TENDENCIA = ("bloqueia", "direciona", "invertido")
SEMENTES_NULO = (11, 23, 37, 53, 71)

#: Entradas REAIS de hoje (deals do MT5, hora de Brasilia).
ENTRADAS_REAIS = (
    ("11:58:53", "long", 5204.0, "abre LONG (fechado 1 tick depois, -R$5)"),
    ("11:58:59", "short", 5203.5, "abre SHORT -- a entrada que perdeu"),
    ("11:59:04", "short", 5204.0, "SHORT DUPLICADO (o bug, nao o sinal)"),
)


# ---------------------------------------------------------------------------
# 1. o escore de tendencia -- puro, incremental, sem look-ahead
# ---------------------------------------------------------------------------

@dataclass
class LeituraTendencia:
    """O que o filtro viu num instante. `por_janela` traz o ER de cada
    janela DEFINIDA (ausente = indefinida, peso redistribuido)."""

    escore: float                      # S combinado, em [-1, +1]
    por_janela: dict[str, float] = field(default_factory=dict)
    minutos_disponiveis: int = 0
    pesos: dict[str, float] = field(default_factory=dict)

    def indicacao(self, lado: str) -> float:
        """Percentual de indicacao PARA ESTE LADO pela MEDIA das janelas."""
        s = self.escore if lado == "long" else -self.escore
        return 50.0 + 50.0 * s

    def acordo(self, lado: str) -> float:
        """Percentual do PESO cujas janelas apontam para `lado` -- quantas
        concordam, nao quanto somam.

        Existe porque a media apaga justamente o que interessa. Em
        2026-08-28 11:58:59, quando a conta vendeu: abertura +0,153,
        ult_50 +0,070, ult_25 +0,070, ult_10 -0,211. A media da +0,020 e a
        `indicacao` de vender sai 49,0% -- um empate, como se nao houvesse
        leitura nenhuma. Mas TRES das quatro janelas apontavam para CIMA
        enquanto o robo vendia: o acordo com o lado vendido era 25%. Nao
        era ausencia de tendencia, era DESACORDO DE PRAZOS, e a media
        destruiu essa informacao ao cancelar +0,153 contra -0,211.

        Achado do dono, 2026-08-28, olhando a tabela da primeira rodada."""
        favor = contra = 0.0
        for nome, er in self.por_janela.items():
            if er == 0:
                continue
            direcao = 1 if er > 0 else -1
            quer = 1 if lado == "long" else -1
            if direcao == quer:
                favor += self.pesos.get(nome, 0.0)
            else:
                contra += self.pesos.get(nome, 0.0)
        total = favor + contra
        return 100.0 * favor / total if total > 0 else 50.0


class TendenciaDaSessao:
    """Agrega os negocios em fechamentos de MINUTO e calcula o ER com sinal
    de cada janela pedida.

    Puro por desenho (regra 5 do AGENTS.md -- isto vai junto com a
    estrategia se ela for portada): entra preco e timestamp, sai numero.
    Sem I/O, sem estado global, sem olhar barra futura -- um minuto so'
    entra na conta depois de FECHADO.

    Custo: `bisect` por janela por barra (O(log n)), nao varredura. Com
    ~130 mil ticks/pregao a versao ingenua (recalcular a soma do caminho a
    cada tick) seria O(n^2) e nao terminaria."""

    def __init__(self, min_minutos: int = MIN_MINUTOS_JANELA):
        self.min_minutos = min_minutos
        self._minutos: list[pd.Timestamp] = []   # inicio de cada minuto FECHADO
        self._fechamentos: list[float] = []
        self._caminho: list[float] = [0.0]       # soma prefixa de |variacao|
        self._minuto_aberto: pd.Timestamp | None = None
        self._ultimo_preco: float | None = None
        self._t_abertura: pd.Timestamp | None = None

    def observa(self, ts: pd.Timestamp, preco: float) -> None:
        """Registra um negocio. Fecha o minuto anterior quando o relogio
        vira -- e' esse fechamento, e so' ele, que entra nas contas."""
        if self._t_abertura is None:
            self._t_abertura = ts
        minuto = ts.floor("min")
        if self._minuto_aberto is None:
            self._minuto_aberto = minuto
        elif minuto > self._minuto_aberto:
            self._fecha_minuto(self._minuto_aberto, self._ultimo_preco)
            self._minuto_aberto = minuto
        self._ultimo_preco = preco

    def _fecha_minuto(self, minuto: pd.Timestamp, fechamento: float | None) -> None:
        if fechamento is None:
            return
        if self._fechamentos:
            self._caminho.append(self._caminho[-1] + abs(fechamento - self._fechamentos[-1]))
        self._minutos.append(minuto)
        self._fechamentos.append(fechamento)

    def leitura(self, agora: pd.Timestamp, pesos: dict[str, float]) -> LeituraTendencia:
        """Escore combinado no instante `agora`, ja ponderado. Os pesos das
        janelas INDEFINIDAS sao redistribuidos entre as definidas -- janela
        sem dado nao vira voto neutro, sai da votacao."""
        n = len(self._fechamentos)
        if n < self.min_minutos or self._t_abertura is None:
            return LeituraTendencia(escore=0.0, minutos_disponiveis=n)

        decorrido = agora - self._t_abertura
        por_janela: dict[str, float] = {}
        for nome, fracao in JANELAS:
            inicio = agora - decorrido * fracao
            i = bisect.bisect_left(self._minutos, inicio)
            if n - i < self.min_minutos:
                continue                      # janela INDEFINIDA, nunca zero
            caminho = self._caminho[n - 1] - self._caminho[i]
            if caminho <= 0:
                continue                      # preco parado: sem direcao a medir
            por_janela[nome] = (self._fechamentos[n - 1] - self._fechamentos[i]) / caminho

        total = sum(pesos[nome] for nome in por_janela)
        escore = (sum(pesos[nome] * er for nome, er in por_janela.items()) / total
                  if total > 0 else 0.0)
        return LeituraTendencia(escore=escore, por_janela=por_janela,
                                minutos_disponiveis=n, pesos=dict(pesos))


# ---------------------------------------------------------------------------
# 2. a estrategia com o filtro por cima -- ADITIVA, o robo original intacto
# ---------------------------------------------------------------------------

class WdoComTendencia(WdoGridReloadMaker):
    """`WdoGridReloadMaker` + confirmacao por tendencia. Subclasse de
    proposito, e apenas neste script: o robo de producao nao muda enquanto
    UM pregao for toda a evidencia.

    O ponto delicado da implementacao e' `state.pending_side`: o pai o
    marca ANTES de devolver a `EnterLimit`. Suprimir a ordem sem
    desmarca-lo deixaria a estrategia esperando para sempre um
    preenchimento que nunca vem -- o robo morreria em silencio no meio do
    pregao, e a tabela mostraria "o filtro reduziu os trades" quando na
    verdade o filtro TRAVOU o robo. Todo caminho de supressao aqui
    restaura o estado.

    Com `limiar_pct=0` a leitura continua sendo calculada e REGISTRADA,
    mas nunca gateia nada -- e' assim que a baseline consegue dizer, trade
    a trade, qual teria sido o percentual (secao 2 do relatorio) sem
    deixar de ser byte a byte o robo original."""

    def __init__(self, *args, limiar_pct: float = 0.0, modo: str = "bloqueia",
                 pesos: dict[str, float] | None = None,
                 taxa_bloqueio: float = 0.0, semente: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self.limiar_pct = float(limiar_pct)
        self.modo = modo
        self.pesos = dict(pesos or PESOS["igual"])
        self.taxa_bloqueio = float(taxa_bloqueio)
        self.semente = int(semente)
        self._tendencia = TendenciaDaSessao()
        self._rng = random.Random(self.semente)
        #: Diario de decisoes -- toda tentativa de armar, com o percentual
        #: que ela viu. E' o que responde a pergunta do dono; a tabela de
        #: P&L sozinha nao responderia.
        self.decisoes: list[dict] = []
        self.armadas = 0
        self.bloqueadas = 0
        self.redirecionadas = 0

    def on_session_start(self, session_date) -> None:
        super().on_session_start(session_date)
        self._tendencia = TendenciaDaSessao()
        self._rng = random.Random(self.semente)

    def _aprova(self, leitura: LeituraTendencia, lado: str) -> bool:
        if self.modo == "aleatorio":
            return self._rng.random() >= self.taxa_bloqueio
        ind = leitura.indicacao(lado)
        if self.modo == "invertido":
            ind = 100.0 - ind
        return ind >= self.limiar_pct

    def on_bar(self, ts: pd.Timestamp, bar: Bar,
               positions: list[IntradayOpenPosition],
               session_pnl_brl: float) -> list[IntradayAction]:
        self._tendencia.observa(ts, bar.close)
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)

        entradas = [a for a in acoes if isinstance(a, EnterLimit)]
        if not entradas:
            return acoes
        entrada = entradas[0]

        leitura = self._tendencia.leitura(ts, self.pesos)
        registro = {
            "ts": ts, "lado_pedido": entrada.side,
            "indicacao": leitura.indicacao(entrada.side),
            "escore": leitura.escore, "janelas": dict(leitura.por_janela),
        }
        self.decisoes.append(registro)

        if self.limiar_pct <= 0.0 and self.modo != "aleatorio":
            registro["desfecho"] = "armada"
            self.armadas += 1
            return acoes                      # baseline byte a byte

        if self._aprova(leitura, entrada.side):
            registro["desfecho"] = "armada"
            self.armadas += 1
            return acoes

        # Reprovada. `pending_side` TEM de voltar (ver docstring da classe).
        outro = "short" if entrada.side == "long" else "long"
        if (self.modo == "direciona"
                and self._aprova(leitura, outro)
                and self._fills_of(outro) < self.max_trades_per_side):
            self._state.pending_side = outro
            nivel = self._level_price(outro)
            registro["desfecho"] = f"redirecionada->{outro}"
            self.redirecionadas += 1
            self.armadas += 1
            return [EnterLimit(
                side=outro, limit_price=nivel,
                initial_target=self._target_price(outro, nivel),
                initial_stop=self._stop_price(outro, nivel),
                quantity=self._quantidade_da_entrada(),
                reason=f"wdo_grid_reload_{outro}_tendencia",
            )]

        self._state.pending_side = None
        registro["desfecho"] = "bloqueada"
        self.bloqueadas += 1
        return [a for a in acoes if not isinstance(a, EnterLimit)]


# ---------------------------------------------------------------------------
# 3. dado de hoje (leitura pura do MT5) + config
# ---------------------------------------------------------------------------

#: Copia em disco do pregao medido. Existe porque `copy_ticks_range` para
#: de responder depois que o terminal desconecta no fim do dia ("Terminal:
#: Call failed", medido 2026-08-28 ~18h) -- sem o cache, o teste deixaria
#: de ser reproduzivel poucas horas depois de ter sido escrito.
CACHE = ROOT / "data" / "raw_ticks" / f"{SYMBOL_REAL}_{DIA:%Y_%m_%d}.parquet"


def carregar_barras_de_hoje() -> pd.DataFrame:
    """Negocios do contrato REAL, em UTC pela convencao do repo
    (`mt5_ticks_source` usa `core.b3_session.MT5_SERVER_TIMEZONE`, nunca
    uma constante -- foi errar isso que matou o stop intradiario em
    2026-08-20).

    Cache em disco primeiro; MT5 so' se ele nao existir, e ai' grava."""
    if CACHE.exists():
        return ticks_to_degenerate_bars(pd.read_parquet(CACHE))

    from market_data_intraday.mt5_ticks_source import fetch_ticks_range

    ticks = fetch_ticks_range(SYMBOL_REAL, DIA.replace(hour=0, minute=0),
                              DIA.replace(hour=23, minute=59))
    if ticks.empty:
        raise SystemExit(
            f"[tendencia] sem tick de {SYMBOL_REAL} para {DIA:%Y-%m-%d} e sem "
            f"cache em {CACHE} -- o terminal MT5 precisa estar aberto, "
            "conectado, e o mercado costuma ter de estar em pregao."
        )
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    ticks.to_parquet(CACHE)
    return ticks_to_degenerate_bars(ticks)


def montar_config() -> IntradayBacktestConfig:
    trade_tick_value, trade_tick_size = _ECONOMIA_WDO
    return config_for(
        profile_for(SYMBOL),
        trade_tick_value=trade_tick_value, trade_tick_size=trade_tick_size,
        initial_capital=CAPITAL_NOCIONAL,
        target_fills_as_maker=True,
        limit_fill_capped_by_volume=True,
        max_open_contracts=MAX_OPEN_CONTRATOS,
    )


def _params_base() -> dict:
    """Geometria de PRODUCAO de hoje (T1/S4, x1) -- e' a que estava no ar
    quando a conta perdeu. `tick_size` vem do PERFIL, nunca digitado."""
    return dict(
        tick_size=profile_for(SYMBOL).price_tick_size,
        level_spacing_ticks=1, profit_ticks=1, stop_ticks=4,
    )


# ---------------------------------------------------------------------------
# 4. forense: o que o filtro teria visto NAS ENTRADAS REAIS de hoje
# ---------------------------------------------------------------------------

def leitura_nas_entradas_reais(bars: pd.DataFrame) -> None:
    """Reproduz a tendencia minuto a minuto e imprime o percentual exato
    nos instantes em que a corretora registrou entrada de verdade.

    Independe de backtest: e' leitura de dado no relogio dos deals. Se o
    filtro tivesse existido hoje, ESTE e' o numero que ele teria visto."""
    print("\n=== 1. o que a tendencia indicava NAS ENTRADAS REAIS de hoje ===")
    print("(deals do MT5, conta 11724331, magic 862399285, WDOU26)\n")

    alvos = {}
    for hora, lado, preco, nota in ENTRADAS_REAIS:
        h, m, s = (int(x) for x in hora.split(":"))
        alvos[DIA.replace(hour=h, minute=m, second=s)] = (hora, lado, preco, nota)
    marcos = sorted(alvos)
    brt = bars.index.tz_convert("America/Sao_Paulo").tz_localize(None)

    for nome_peso, pesos in PESOS.items():
        tend = TendenciaDaSessao()
        proximo = 0
        print(f"--- pesos '{nome_peso}' ---")
        cab = (f"{'hora':>9} {'lado':>6} {'preco':>9} {'abertura':>9} {'ult_50':>8} "
               f"{'ult_25':>8} {'ult_10':>8} {'S':>7} {'IND lado':>9}")
        print(cab)
        print("-" * len(cab))
        for ts, preco in zip(brt, bars["close"].to_numpy()):
            while proximo < len(marcos) and ts >= marcos[proximo]:
                hora, lado, preco_real, nota = alvos[marcos[proximo]]
                leitura = tend.leitura(ts, pesos)
                cel = {j: leitura.por_janela.get(j) for j, _ in JANELAS}
                print(f"{hora:>9} {lado:>6} {num_br(preco_real, 1):>9} "
                      + " ".join(
                          f"{(num_br(cel[j], 3) if cel[j] is not None else '-'):>{larg}}"
                          for j, larg in (("abertura", 9), ("ult_50", 8),
                                          ("ult_25", 8), ("ult_10", 8)))
                      + f" {num_br(leitura.escore, 3):>7}"
                      + f" {num_br(leitura.indicacao(lado), 1) + '%':>9}")
                print(f"{'':>9} {nota}")
                proximo += 1
            if proximo >= len(marcos):
                break
            tend.observa(ts, float(preco))
        print()


def forense_dos_perdedores(bars: pd.DataFrame) -> None:
    """A evidencia central deste arquivo.

    Com alvo de 1 tick e stop de 4, o resultado do dia e' decidido pelos
    POUCOS trades que perdem -- cada perda apaga ~4 ganhos. Aqui saem
    todos os trades da baseline com o percentual de tendencia que o filtro
    teria visto no instante em que a ordem foi ARMADA (nao no
    preenchimento: a decisao de armar e' a decisao que o filtro gateia).

    Se os perdedores tiverem indicacao sistematicamente mais baixa que os
    vencedores, o filtro tem onde morder. Se nao tiverem, nao tem -- e
    nenhuma tabela de P&L de um dia so' consegue desmentir isso."""
    print("\n=== 2. os trades que PERDERAM hoje, e o que a tendencia dizia ===")
    cfg = montar_config()
    strat = WdoComTendencia(**_params_base(), limiar_pct=0.0, pesos=PESOS["igual"])
    resultado = run_intraday_backtest(bars, strat, cfg)
    trades = list(resultado.trades)

    armadas = [d for d in strat.decisoes if d.get("desfecho") == "armada"]
    tempos = [d["ts"] for d in armadas]

    def indicacao_do_trade(t) -> dict | None:
        i = bisect.bisect_right(tempos, t.entry_ts) - 1
        return armadas[i] if i >= 0 else None

    perdedores, vencedores = [], []
    for t in trades:
        d = indicacao_do_trade(t)
        if d is None:
            continue
        (perdedores if t.pnl_brl < 0 else vencedores).append((t, d))

    print(f"baseline hoje: {len(trades)} trades, "
          f"{len(vencedores)} ganharam, {len(perdedores)} perderam, "
          f"liquido R$ {num_br(sum(t.pnl_brl for t in trades))}\n")

    cab = (f"{'entrada (BRT)':>15} {'lado':>6} {'preco':>9} {'saida':>14} "
           f"{'P&L R$':>9} {'IND lado':>9} {'S':>7}")
    print(cab)
    print("-" * len(cab))
    for t, d in perdedores:
        brt = t.entry_ts.tz_convert("America/Sao_Paulo")
        print(f"{brt:%H:%M:%S}".rjust(15)
              + f" {t.side:>6} {num_br(t.entry_price, 1):>9} {t.exit_reason:>14} "
              f"{num_br(t.pnl_brl):>9} "
              f"{num_br(d['indicacao'], 1) + '%':>9} {num_br(d['escore'], 3):>7}")

    if vencedores and perdedores:
        iv = [d["indicacao"] for _, d in vencedores]
        ip = [d["indicacao"] for _, d in perdedores]
        print(f"\nindicacao mediana -- vencedores {num_br(statistics.median(iv), 1)}%"
              f"  x  perdedores {num_br(statistics.median(ip), 1)}%")
        print(f"faixa vencedores: {num_br(min(iv), 1)}% a {num_br(max(iv), 1)}%   |   "
              f"faixa perdedores: {num_br(min(ip), 1)}% a {num_br(max(ip), 1)}%")
        print(f"\nCom {len(perdedores)} perdedor(es), qualquer separacao aqui e' "
              "anedota, nao estatistica.")


# ---------------------------------------------------------------------------
# 5. varredura de limiar x modo x pesos, com controle NULO
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Celula:
    limiar: float
    modo: str
    peso: str
    semente: int = 0
    taxa_bloqueio: float = 0.0

    @property
    def rotulo(self) -> str:
        if self.limiar <= 0 and self.modo != "aleatorio":
            return "baseline (sem filtro)"
        if self.modo == "aleatorio":
            return (f"NULO sorteio {num_br(100 * self.taxa_bloqueio, 1)}% "
                    f"(semente {self.semente})")
        return f"limiar {num_br(self.limiar, 0)}% {self.modo} [{self.peso}]"


def _rodar_celula(celula: _Celula, bars: pd.DataFrame):
    cfg = montar_config()
    strat = WdoComTendencia(
        **_params_base(), limiar_pct=celula.limiar, modo=celula.modo,
        pesos=PESOS[celula.peso], taxa_bloqueio=celula.taxa_bloqueio,
        semente=celula.semente,
    )
    resultado = run_intraday_backtest(bars, strat, cfg)
    tentativas = len(strat.decisoes)
    taxa = (strat.bloqueadas / tentativas) if tentativas else 0.0
    linha = linha_de_resultado(
        celula.rotulo, resultado, CAPITAL_NOCIONAL, capital_nocional=True,
        extras={
            "armadas": f"{strat.armadas}",
            "bloq%": num_br(100 * taxa, 1),
            "redirec.": f"{strat.redirecionadas}",
        },
    )
    return celula, linha, taxa


def _tarefa(args):
    return _rodar_celula(*args)


def _executa(celulas: list[_Celula], bars: pd.DataFrame, titulo: str):
    print(f"\n{titulo} -- {len(celulas)} celulas")
    print("(cada uma imprime a propria linha assim que termina)\n")
    saida: dict[_Celula, tuple[LinhaResultado, float]] = {}
    with ProcessPoolExecutor() as pool:
        futuros = [pool.submit(_tarefa, (c, bars)) for c in celulas]
        for fut in as_completed(futuros):
            celula, linha, taxa = fut.result()
            saida[celula] = (linha, taxa)
            print(f"  [ok] {linha.variante:40s} liquido R$ {num_br(linha.liquido_brl):>9}"
                  f"  trades {linha.trades:>4}  win {num_br(linha.win_rate_pct, 1):>5}%"
                  f"  armadas {linha.extras['armadas']:>6}"
                  f"  bloq {linha.extras['bloq%']:>5}%", flush=True)
    return saida


def varredura(bars: pd.DataFrame) -> None:
    base = _Celula(0.0, "bloqueia", "igual")
    celulas = [base] + [
        _Celula(limiar, modo, peso)
        for peso in PESOS for limiar in LIMIARES for modo in MODOS_TENDENCIA
    ]
    fase_a = _executa(celulas, bars, "=== 3a. tendencia (candidato + controle invertido) ===")

    # Controle NULO: bloquear na MESMA taxa, mas por sorteio.
    nulos = [
        _Celula(0.0, "aleatorio", "igual", semente=s,
                taxa_bloqueio=fase_a[_Celula(limiar, "bloqueia", "igual")][1])
        for limiar in LIMIARES for s in SEMENTES_NULO
    ]
    fase_b = _executa(nulos, bars, "=== 3b. controle NULO (mesma taxa de bloqueio, por sorteio) ===")

    extras = ("armadas", "bloq%", "redirec.")
    print("\n=== 4. tabela padrao (baseline primeiro, fora da ordenacao) ===\n")
    ordem = [base] + [_Celula(limiar, modo, peso)
                      for peso in PESOS for limiar in LIMIARES for modo in MODOS_TENDENCIA]
    print(tabela([fase_a[c][0] for c in ordem], extras))

    print("\n=== 5. candidato x NULO na mesma taxa de bloqueio ===\n")
    cab = (f"{'limiar':>8} {'bloq%':>7} {'tendencia R$':>13} {'invertido R$':>13} "
           f"{'nulo mediano':>13} {'faixa do nulo':>21} {'veredito':>12}")
    print(cab)
    print("-" * len(cab))
    for limiar in LIMIARES:
        cand = fase_a[_Celula(limiar, "bloqueia", "igual")]
        inv = fase_a[_Celula(limiar, "invertido", "igual")][0]
        amostra = sorted(
            fase_b[_Celula(0.0, "aleatorio", "igual", semente=s, taxa_bloqueio=cand[1])][0].liquido_brl
            for s in SEMENTES_NULO
        )
        mediana = statistics.median(amostra)
        acima = cand[0].liquido_brl > amostra[-1]
        print(f"{num_br(limiar, 0):>8} {num_br(100 * cand[1], 1):>7} "
              f"{num_br(cand[0].liquido_brl):>13} {num_br(inv.liquido_brl):>13} "
              f"{num_br(mediana):>13} "
              f"{num_br(amostra[0]) + ' a ' + num_br(amostra[-1]):>21} "
              f"{('acima do nulo' if acima else 'DENTRO do nulo'):>12}")
    print("\n'DENTRO do nulo' = bloquear na mesma taxa POR SORTEIO ja alcanca o mesmo")
    print("resultado; a tendencia nao esta carregando informacao, so' reduzindo")
    print(f"atividade. {len(SEMENTES_NULO)} sementes -- faixa, nao numero solto.")


# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 104)
    print("WDO F1 + tendencia como CONFIRMACAO -- pregao de 2026-08-28 apenas")
    print("=" * 104)
    print("RESSALVA, antes de qualquer numero: os -R$295 de hoje vieram de DUAS")
    print("entradas independentes numa conta com margem para UMA -- bug de execucao,")
    print("ja corrigido no motor por teto dinamico de capital. NAO vieram do sinal.")
    print("Um unico contrato teria perdido R$147,50. O que se mede aqui e' so' se")
    print("aquela venda, sozinha, teria sido AUTORIZADA por uma leitura de tendencia.")
    print("UM pregao, escolhido depois de se saber que deu errado: n=1, sem dispersao.")
    print()

    bars = carregar_barras_de_hoje()
    pregao = bars.index.tz_convert("America/Sao_Paulo")
    print(f"dado: {len(bars):,} negocios de {SYMBOL_REAL}, "
          f"{pregao.min():%H:%M:%S} -> {pregao.max():%H:%M:%S} (Brasilia)")
    print(f"preco: abertura {num_br(float(bars['close'].iloc[0]), 1)} / "
          f"minimo {num_br(float(bars['low'].min()), 1)} / "
          f"maximo {num_br(float(bars['high'].max()), 1)} / "
          f"ultimo {num_br(float(bars['close'].iloc[-1]), 1)}")
    print(f"capital: NOCIONAL R$ {num_br(CAPITAL_NOCIONAL)} com teto de "
          f"{MAX_OPEN_CONTRATOS} contrato -- com o capital REAL de R$300 o robo")
    print("         fica INERTE hoje (a reserva de 2026-08-28 exige >R$375 para 1)")

    leitura_nas_entradas_reais(bars)
    forense_dos_perdedores(bars)
    varredura(bars)

    print("\nlucro/DD e R$/dia com 1 pregao so' nao sao metricas -- sao o mesmo")
    print("numero dividido por 1. Leia 'liquido R$', 'armadas', 'trades' e 'win%'.")


if __name__ == "__main__":
    main()
