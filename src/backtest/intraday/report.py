"""TABELA PADRAO de resultado intradiario — uma unica definicao de "como se
mostra o resultado de um backtest", usada por TODO script de day trade.

Existe por decisao do dono (2026-08-25): "defina uma tabela padrao de output
para sempre seguir o mesmo padrao; ela deve contemplar tudo o que e'
necessario, e em comparacoes entre testes/ativos/estrategias vai ser
adaptada, mas deve ter uma base bem definida e conhecida por todos".

O problema que ela resolve e' concreto e ja aconteceu neste repo: cada script
imprimia o SEU conjunto de colunas, com o SEU formato de numero, e comparar
duas rodadas virava trabalho de leitura em vez de leitura direta. Pior: uma
coluna com o MESMO nome significava coisas diferentes em scripts diferentes.

## As 12 colunas da BASE (sempre presentes, sempre nesta ordem)

| coluna | o que e' |
|---|---|
| `variante` | rotulo da linha (parametro, ativo, estrategia — o que a rodada compara) |
| `retorno` | retorno percentual sobre o capital inicial; `—` quando o capital e' NOCIONAL |
| `liquido R$` | P&L liquido total, ja com custo — o numero que decide |
| `MaxDD %` | pior queda percentual da curva de patrimonio; `—` com capital nocional |
| `MaxDD R$` | pior queda em reais — a unica leitura valida de DD com capital nocional |
| `lucro/DD` | `liquido R$ / MaxDD R$` — quantos reais de lucro por real de queda |
| `win%` | percentual de trades vencedores |
| `trades` | numero de trades fechados |
| `R$/dia` | liquido dividido por pregao COM DADO (nao por dia de calendario) |
| `trd/dia` | trades por pregao — o giro do desenho, em uma coluna |
| `capital final` | capital inicial + liquido; `—` quando o capital e' nocional |
| `pregoes` | pregoes distintos cobertos pela run |

Quem compara N variantes acrescenta colunas com `extras` (dict ordenado, ja
formatado como texto) — elas entram DEPOIS da base, nunca no lugar dela.

## O aviso `desliz.alvo Nt`

Colado no fim da linha (nunca uma coluna — ver `LinhaResultado.aviso`)
quando a run cobrou deslize da saida por ALVO maker
(`IntradayCostModel.target_slippage_ticks`, ligado por default em
`config_for` desde 2026-09-08). E' PREMISSA DE CUSTO, nao alerta: duas
linhas com o mesmo `liquido R$` e premissas de deslize diferentes nao sao
comparaveis, e antes disto elas sairiam identicas na tabela. Ver o item 4.8
de `LICOES_DE_PRODUCAO.md` para a medicao (8 de 8 saidas por alvo nativo do
WDO F1 executaram pior que o nivel pedido em 2026-09-08).

## O aviso `fila E/S`

O irmao do anterior, do outro lado da execucao: quanta FILA a run assumiu na
frente da nossa ordem-limite, ENTRADA/SAIDA (`IntradayBacktestConfig.queue_
ahead_qty` / `exit_queue_ahead_qty`, ligados por default em `config_for`
desde 2026-09-09 a partir de `backtest.intraday.fidelidade`).

Tambem e' PREMISSA, nao alerta, e pela mesma razao esta' no `aviso` e nao
numa coluna. O tamanho do que ele denuncia: simulando o pregao real de
2026-09-09 (WDO F1, 34 operacoes, -R$3,00 cada), o motor sem fila devolvia
+R$3,82 por operacao -- errava o SINAL, nao a magnitude.

Ele tem TRES estados, e o terceiro e' o que faz diferenca:

| carimbo | significa |
|---|---|
| `fila 438/489` | a calibracao medida do simbolo (hoje so' o WDO@) |
| `fila 0/0` | simbolo medido, mas a run zerou de proposito (reproduz o motor de ate 2026-09-08) |
| `fila NAO CALIBRADA` | ninguem mediu este simbolo -- Gremah em acao B3, CopaWin em WIN@ |

Sem o terceiro, a linha de um simbolo nunca medido sairia IGUAL a uma linha
sem premissa nenhuma. Uma linha sem carimbo e' indistinguivel de uma linha
que ninguem sabe se esta certa, e foi exatamente assim que `queue_ahead_qty`
passou um mes inteiro no default 0,0 sem ninguem notar.

## Duas escolhas que valem explicacao

**`lucro/DD` no lugar do Calmar anualizado.** `backtest.metrics.calmar`
anualiza o retorno, e este motor roda janelas de semanas a meses: anualizar
uma janela curta AMPLIFICA o numero em vez de estima-lo. E' a mesma razao
que ja fez `run_intraday_backtest` reportar `metrics.period_return` sob a
chave `"cagr"` (ver `backtest/intraday/engine.py`). `liquido R$ / MaxDD R$`
e' adimensional, nao depende de anualizacao nenhuma e significa a MESMA coisa
com capital real ou nocional.

**Capital NOCIONAL (`capital_nocional=True`).** Um mini-futuro na Copa BTG
nao tem saldo: a margem e' simulada como infinita e o limitador e' o teto de
contratos abertos. Um `initial_capital` ali e' so' uma linha de base para a
curva de patrimonio existir — dividir por ele produziria "retorno de X%"
sobre um numero inventado. Nesses casos as tres colunas que dependem da base
(`retorno`, `MaxDD %`, `capital final`) saem como `—`, em vez de sairem com
um numero que ninguem pode usar.

Numero em formato BR (milhar com ponto, decimal com virgula) porque e' assim
que o dono le' — mesma convencao ja usada nas tabelas de conversa.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from backtest.intraday.machine import IntradayTrade

#: Larguras das 12 colunas da base, na ordem. Ficam aqui (e nao espalhadas em
#: f-strings) para o cabecalho e as linhas nunca saírem desalinhados: os dois
#: leem a MESMA tupla.
#: Largura da coluna `variante`. Publica porque quem MONTA rotulo precisa
#: caber nela: um rotulo truncado faz duas combinacoes diferentes aparecerem
#: como a MESMA linha da tabela (aconteceu 2026-08-25 numa varredura de 1.152
#: combinacoes). Quem gera rotulo checa contra esta constante em vez de
#: repetir o numero.
LARGURA_VARIANTE = 30

_BASE = (
    ("variante", LARGURA_VARIANTE, "<"),
    ("retorno", 9, ">"),
    ("liquido R$", 13, ">"),
    ("MaxDD %", 9, ">"),
    ("MaxDD R$", 12, ">"),
    ("lucro/DD", 9, ">"),
    ("win%", 7, ">"),
    ("trades", 7, ">"),
    ("R$/dia", 11, ">"),
    ("trd/dia", 8, ">"),
    ("capital final", 15, ">"),
    ("pregoes", 8, ">"),
)

_VAZIO = "—"


def num_br(valor: float | None, casas: int = 2) -> str:
    """`1234.5` -> `"1.234,50"`. `None` -> `"—"`. Formato BR em UM lugar so':
    a alternativa (cada script formatando do seu jeito) ja produziu tabelas
    em que a mesma grandeza aparecia com separador diferente em duas linhas
    vizinhas."""
    if valor is None:
        return _VAZIO
    inteiro = f"{valor:,.{casas}f}"
    return inteiro.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


@dataclass(frozen=True)
class LinhaResultado:
    """Uma linha da tabela padrao. Montada por `linha_de_resultado` a partir
    de um `IntradayBacktestResult` — construir na mao so' em teste."""

    variante: str
    liquido_brl: float
    maxdd_brl: float
    win_rate_pct: float
    trades: int
    pregoes: int
    #: `None` quando o capital e' NOCIONAL (ver docstring do modulo).
    retorno_pct: float | None = None
    maxdd_pct: float | None = None
    capital_final: float | None = None
    #: Colunas extras da rodada, ja em texto e na ordem de exibicao.
    extras: dict[str, str] = field(default_factory=dict)
    #: Texto curto colado no fim da linha (ex.: "ZERADO", "pulou 48d") —
    #: nunca uma coluna, porque nao existe em toda rodada.
    aviso: str = ""

    @property
    def lucro_por_dd(self) -> float | None:
        """`None` quando nao houve queda nenhuma — dividir por zero daria
        `inf`, que numa tabela ordenada por esta coluna poe uma run sem
        drawdown (tipicamente uma run com 1 trade) acima de tudo."""
        if self.maxdd_brl <= 0:
            return None
        return self.liquido_brl / self.maxdd_brl

    @property
    def liquido_por_pregao(self) -> float | None:
        if self.pregoes <= 0:
            return None
        return self.liquido_brl / self.pregoes

    @property
    def trades_por_pregao(self) -> float | None:
        if self.pregoes <= 0:
            return None
        return self.trades / self.pregoes


def maxdd_brl(equity_curve: pd.Series) -> float:
    """Pior queda da curva de patrimonio em REAIS (pico-a-vale), sempre >= 0.

    Em reais, e nao em percentual, porque com capital nocional o percentual
    nao quer dizer nada — e porque a comparacao que interessa ("o bloco
    mediano de 4 pregoes ganha mais do que a pior queda?") e' entre duas
    grandezas em reais."""
    if equity_curve is None or equity_curve.empty:
        return 0.0
    pico = equity_curve.cummax()
    return float((pico - equity_curve).max())


def maxdd_intradiario_mediano_brl(equity_curve: pd.Series) -> float:
    """Mediana, entre os pregoes, da pior queda DENTRO de cada pregao (R$).

    Diferente de `maxdd_brl`, que e' a pior queda da janela INTEIRA: um robo
    de day trade zera todo dia, entao o que ele pede de estomago no dia a dia
    e' esta queda intradiaria, nao a queda acumulada de meses.

    Existe para o portao G2 do plano da Copa ("o bloco mediano tem de ganhar
    mais do que o MaxDD intradiario mediano"): comparar lucro tipico com
    sofrimento tipico, os dois em reais."""
    if equity_curve is None or equity_curve.empty:
        return 0.0
    def _dd(serie: pd.Series) -> float:
        return float((serie.cummax() - serie).max())
    por_dia = equity_curve.groupby(pd.DatetimeIndex(equity_curve.index).date).apply(_dd)
    return float(por_dia.median()) if len(por_dia) else 0.0


def linha_de_resultado(
    variante: str,
    result,
    initial_capital: float,
    capital_nocional: bool = False,
    extras: dict[str, str] | None = None,
) -> LinhaResultado:
    """Traduz um `IntradayBacktestResult` na linha padrao.

    `capital_nocional=True` (futuro em ambiente de margem infinita) apaga as
    tres colunas que dependem de um capital de verdade — ver a docstring do
    modulo. O aviso de conta zerada / pregao pulado sai automatico do proprio
    resultado, para nenhum script esquecer de mostra-lo (ja aconteceu: uma
    tabela com capital final bonito e a conta zerada no meio da janela)."""
    trades: list[IntradayTrade] = list(result.trades)
    liquido = sum(t.pnl_brl for t in trades)
    equity = result.equity_curve
    pregoes = 0
    if equity is not None and not equity.empty:
        pregoes = len(set(pd.DatetimeIndex(equity.index).date))
    vencedores = sum(1 for t in trades if t.pnl_brl > 0)

    avisos: list[str] = []
    if getattr(result, "wiped_out_at", None) is not None:
        avisos.append("ZERADO")
    puladas = len(getattr(result, "sessoes_puladas_por_capital", []) or [])
    if puladas:
        avisos.append(f"pulou {puladas}d")
    # PREMISSA DE CUSTO, nao alerta de problema -- mas mora no mesmo lugar
    # (`aviso`) e pelo mesmo motivo: nao existe em toda rodada, entao nao
    # pode virar coluna da base. Sai AUTOMATICO do proprio resultado para
    # nenhum script poder esquecer de mostra-la; ate 2026-09-08 o motor
    # entregava a saida por ALVO maker exatamente no nivel pedido, de graca,
    # e nenhuma tabela deste repo avisava que aquele numero dependia disso
    # (item 4.8 de LICOES_DE_PRODUCAO.md -- 8 de 8 saidas reais do WDO F1
    # sairam PIORES que o nivel, R$45,00 num pregao de -R$116,00). Duas
    # linhas com o mesmo `liquido R$` e premissas de deslize diferentes nao
    # sao comparaveis, e sem este aviso elas pareciam identicas.
    deslize = float(getattr(result, "deslize_alvo_ticks", 0.0) or 0.0)
    if deslize:
        avisos.append(f"desliz.alvo {num_br(deslize, 1)}t")
    # MESMO motivo do aviso acima, do outro lado da execucao: quanta FILA a
    # run assumiu na frente da nossa ordem-limite, entrada/saida. Ate
    # 2026-09-09 o motor enchia toda limite no PRIMEIRO TOQUE do nivel, dos
    # dois lados, e nenhuma tabela deste repo avisava disso -- o mesmo pregao
    # real do WDO F1 rendia +R$3,82 por operacao no motor sem fila contra
    # -R$3,00 no extrato (ver `backtest.intraday.fidelidade`). Duas linhas
    # com o mesmo `liquido R$` e premissas de PREENCHIMENTO diferentes nao
    # sao comparaveis, e sem o carimbo elas sairiam identicas.
    #
    # TRES estados, nao dois, e o terceiro e' o que importa: `fila 438/489`
    # (calibrado), `fila 0/0` (premissa deliberada -- reproduzir o motor
    # antigo num simbolo QUE FOI medido) e `fila NAO CALIBRADA` (ninguem
    # mediu este simbolo -- Gremah em acao B3, CopaWin em WIN@). Sem o
    # terceiro, a linha de um simbolo nunca medido sai igual a uma linha sem
    # premissa nenhuma, que e' o mesmo silencio de sempre.
    fila_ent = float(getattr(result, "fila_entrada_qty", 0.0) or 0.0)
    fila_sai = float(getattr(result, "fila_saida_qty", 0.0) or 0.0)
    calibrada = getattr(result, "fila_calibrada", None)
    if fila_ent or fila_sai:
        carimbo = f"fila {num_br(fila_ent, 0)}/{num_br(fila_sai, 0)}"
        # Numero de fila num simbolo sem medicao e' sensibilidade/chute do
        # chamador, e nao pode passar por calibracao na leitura da tabela.
        avisos.append(carimbo + (" (nao calibrada)" if calibrada is False else ""))
    elif calibrada is False:
        avisos.append("fila NAO CALIBRADA")
    elif calibrada is True:
        avisos.append("fila 0/0")

    return LinhaResultado(
        variante=variante,
        liquido_brl=liquido,
        maxdd_brl=maxdd_brl(equity),
        win_rate_pct=(100.0 * vencedores / len(trades)) if trades else 0.0,
        trades=len(trades),
        pregoes=pregoes,
        retorno_pct=(None if capital_nocional or initial_capital <= 0
                     else 100.0 * liquido / initial_capital),
        maxdd_pct=(None if capital_nocional
                   else 100.0 * result.metrics.get("max_drawdown", 0.0)),
        capital_final=(None if capital_nocional else initial_capital + liquido),
        extras=dict(extras or {}),
        aviso=" ".join(avisos),
    )


def _celula(texto: str, largura: int, alinha: str) -> str:
    return f"{texto:{alinha}{largura}}"


def cabecalho(extras: tuple[str, ...] = (), largura_extra: int = 12) -> str:
    """Cabecalho da tabela + a regua embaixo. `extras` na ordem em que as
    linhas as declaram — quem imprime e' responsavel por passar as MESMAS
    chaves aqui e em cada `LinhaResultado.extras`."""
    partes = [_celula(nome, larg, alinha) for nome, larg, alinha in _BASE]
    partes += [_celula(nome, largura_extra, ">") for nome in extras]
    linha = "".join(partes)
    return linha + "\n" + "-" * len(linha)


def linha(item: LinhaResultado, extras: tuple[str, ...] = (), largura_extra: int = 12) -> str:
    valores = [
        item.variante[:LARGURA_VARIANTE],
        _VAZIO if item.retorno_pct is None else f"{num_br(item.retorno_pct, 1)}%",
        num_br(item.liquido_brl, 2),
        _VAZIO if item.maxdd_pct is None else f"{num_br(item.maxdd_pct, 1)}%",
        num_br(item.maxdd_brl, 2),
        num_br(item.lucro_por_dd, 2),
        f"{num_br(item.win_rate_pct, 1)}%",
        str(item.trades),
        num_br(item.liquido_por_pregao, 2),
        num_br(item.trades_por_pregao, 1),
        num_br(item.capital_final, 2),
        str(item.pregoes),
    ]
    partes = [_celula(v, larg, alinha) for v, (_, larg, alinha) in zip(valores, _BASE)]
    partes += [_celula(item.extras.get(nome, _VAZIO), largura_extra, ">") for nome in extras]
    texto = "".join(partes)
    return texto + (f"  {item.aviso}" if item.aviso else "")


def tabela(linhas: list[LinhaResultado], extras: tuple[str, ...] = (),
           largura_extra: int = 12) -> str:
    """A tabela inteira em texto, cabecalho incluso — nao ordena nada: a
    ORDEM e' decisao de quem chama (a linha 'atual'/baseline costuma vir
    primeiro, fora da ordenacao, para a comparacao ser imediata)."""
    return "\n".join([cabecalho(extras, largura_extra)]
                     + [linha(item, extras, largura_extra) for item in linhas])
