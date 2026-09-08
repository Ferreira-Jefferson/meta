"""Pedido do dono 2026-09-04, depois do item 4.8 (alvo nativo do WDO F1
desliza e zera o bruto de um trade T1): investigar, só na semana ATUAL
(2026-08-31 a 2026-09-04 -- a mais parecida com o regime de mercado de
agora, e a semana em que a operação REAL começou), quanto o preço se
afastou de cada entrada -- em favor (MFE, "até que preço eu poderia ter
colocado o alvo") e contra (MAE, "até que preço chegou do stop") -- mais
volume e volatilidade antes de cada entrada, pra alimentar uma análise de
padrões (rodada à parte, por um agente Opus 5) em cima do CSV que este
script grava.

## Config usada: T1/S16 (a que rodou de VERDADE esta semana)

`profit_ticks=1, stop_ticks=16, level_spacing_ticks=1` -- é a config que
esteve em produção a semana inteira (o default de `WdoGridReloadMaker`
só mudou pra T2 HOJE, depois do incidente do item 4.8, e ainda nem foi
reiniciado no processo ao vivo). As ENTRADAS não dependem de
profit_ticks/stop_ticks (mesma ordem-limite a `level_spacing_ticks` do
open/último preço, alternando lado) -- só o instante de SAÍDA muda -- mas
para o MFE/MAE ficarem ligados a um trade real (janela entrada->saída
definida), a config importa: é o T1/S16 real que definiu essas janelas.

## Força de compra/venda por regra de tick -- REFUTADA, removida

Versão anterior deste script calculava uma "força compradora/vendedora"
por PROXY de regra de tick (tick-rule clássica), porque o terminal MT5
(Rico) não entrega o agressor real para WDO@ (`bid`/`ask` SEMPRE 0.0,
`flags` CONSTANTE em toda amostra testada). Um agente Opus 5 testou essa
coluna (`forca_compra_proxy_15s_antes`/`_60s_antes`) contra MFE, duração
e o próprio lado do trade nas 177 linhas da rodada de 2026-09-04: TODOS
os testes deram p>=0,13 -- nenhuma correlação sobrevive nem de longe a
significância, muito menos correção por múltiplos testes. Removida do
script (ver `LICOES_DE_PRODUCAO.md`, mesmo espírito de
`candle_patterns_refuted`). `volume_*`/`volatilidade_ticks_*` abaixo
NÃO foram refutados -- tiveram correlação real com duração do trade
(rho≈-0,33), sobreviveu correção por múltiplos testes.

## Janelas de volume/volatilidade antes da entrada

Duas janelas de tempo antes de `entry_ts` (`JANELAS_SEGUNDOS` abaixo): uma
curta (15s) e uma mais longa (60s) -- não escolhidas por calibração
nenhuma, só pra dar à análise posterior mais de uma escala pra comparar.
`volatilidade_*` é o range (max-min) do preço nessa janela, em ticks --
proxy simples de volatilidade de curtíssimo prazo, não um ATR de verdade
(não haveria período suficiente pra isso na escala de segundos usada).

## Fuso e fetch parcial -- os DOIS defeitos corrigidos em 2026-09-07

A primeira versão deste script chamava `mt5.copy_ticks_range` na mão e
rotulava `time_msc` como UTC (`tz_localize("UTC")`). Os dois estão errados,
e nenhum dos dois levanta exceção:

1. **`time_msc` é hora de PAREDE do servidor** (= horário de Brasília,
   medido em `core/b3_session.py`), não UTC. Rotular direto como UTC erra
   em exatamente 3h. Estrago principal: TODO `entry_ts`/`exit_ts` do CSV
   saía 3h cedo, e era por isso que ele não batia com os fills reais de
   `db/live.sqlite` -- pela rota correta todo fill de 04/09 casa no mesmo
   milissegundo. Estrago LATENTE, medido 2026-09-07 e que por sorte não se
   realizou aqui: a máquina compara `ts.time()` direto contra
   `session_end_time` do perfil (UTC, `session_end_policy="fixed"`), então
   um rótulo 3h cedo desloca o flatten forçado de fim de pregão junto. No
   `WDO@` o corte é 21:30 UTC e o dado termina 21:29:59, então o flatten de
   sessão não dispara nem com rótulo certo nem com errado -- os dois
   caminhos dão exatamente o mesmo resultado (1.859 trades, R$7.545,50,
   conferido lado a lado). Qualquer corte que caísse DENTRO de
   12:00..21:29 UTC teria disparado na hora errada, em silêncio.

2. **`copy_ticks_range` devolve fetch PARCIAL sem avisar** quando o
   `date_from` cai dentro do pregão do próprio dia (medido 2026-08-24,
   Rico/XP -- é a razão de `_SAFE_FETCH_LOOKBACK` existir em
   `live/tick_feed.py`). Sintoma real de 04/09: o CSV parou em 03/09 10:04
   e reportou "zero trades em 04/09" num dia com atividade real, e isso foi
   investigado como bug de produção quando era só o terminal sincronizando.
   Defesa aqui: janela alargada em `_FOLGA_FETCH` para cada lado + recorte
   pelo index JÁ corrigido + `_conferir_cobertura`, que FALHA alto se algum
   pregão da semana estiver faltando ou truncado.

Sobre o formato do limite pedido ao terminal (`_limite_servidor`): medido
2026-09-07 neste terminal, o pacote `MetaTrader5` converte o `datetime` do
limite com `.timestamp()`, ou seja um NAIVE é reinterpretado no fuso da
MÁQUINA (aqui, Brasília) -- pedir naive 12:00 devolveu negócios de 15:00 de
parede do servidor, +3h. Um `datetime` tz-aware UTC cujo relógio de parede
já É o do servidor não sofre reinterpretação nenhuma (pedir 15:00 UTC
devolveu exatamente 15:00 de parede). Por isso o limite aqui é
`utc_to_server_wall_clock(...).replace(tzinfo=timezone.utc)`, e não o naive
que `live/tick_feed.py` usa -- lá o piso de 1 dia de lookback torna o
deslocamento de 3h inofensivo; numa janela apertada como esta, não seria.

## MFE/MAE: janela é o próprio trade (entrada -> saída REAL)

Medido dentro de `[entry_ts, exit_ts]` do trade tal como o motor fechou de
verdade (por alvo, stop, ou fechamento de pregão) -- não um horizonte fixo
independente. Isso significa que MFE/MAE aqui descrevem "o que aconteceu
DENTRO do trade que o T1/S16 realmente abriu e fechou", não "o máximo
teórico que o mercado permitiria se a posição ficasse aberta pra sempre".

Uso: `python wdof1_mfe_mae_semana_2026_09_04.py`
"""
from __future__ import annotations

import inspect
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.b3_session import MT5_SERVER_TIMEZONE, utc_to_server_wall_clock  # noqa: E402
from market_data_intraday.mt5_ticks_source import fetch_ticks_range  # noqa: E402
from market_data_intraday.tick_bars import ticks_to_degenerate_bars  # noqa: E402
from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker  # noqa: E402
from wdo_grid_reload_f1_lab import montar_config, rodar  # noqa: E402

SYMBOL = "WDO@"

#: A semana medida, em DATAS de pregão (Brasília) -- os limites em UTC saem
#: daqui, nunca digitados na mão.
PRIMEIRO_PREGAO = date(2026, 8, 31)
ULTIMO_PREGAO = date(2026, 9, 4)


def _meia_noite_brt_em_utc(d: date) -> datetime:
    return datetime.combine(d, time(0, 0), tzinfo=MT5_SERVER_TIMEZONE).astimezone(timezone.utc)


INICIO_SEMANA = _meia_noite_brt_em_utc(PRIMEIRO_PREGAO)
FIM_SEMANA = _meia_noite_brt_em_utc(ULTIMO_PREGAO + timedelta(days=1))  # exclusivo

#: Quanto a janela PEDIDA ao terminal é alargada para cada lado, para nunca
#: cair no fetch parcial de `copy_ticks_range` (ver a seção "Fuso e fetch
#: parcial" na docstring do módulo). Mesmo número de
#: `live/tick_feed.py::_SAFE_FETCH_LOOKBACK`. O recorte para a janela de
#: verdade é feito DEPOIS, sobre o index já corrigido de fuso.
_FOLGA_FETCH = timedelta(days=1)

#: Fronteiras do pregão do WDO em Brasília (fecho medido 18:29, ver
#: `backtest/intraday/profiles.py`), usadas só pela conferência de cobertura.
_ABERTURA_BRT = time(9, 0)
_FECHO_BRT = time(18, 29)
#: Tolerância da conferência: um pregão cujo primeiro negócio venha depois de
#: 09:30 ou cujo último venha antes de 18:00 está TRUNCADO, não "sem liquidez".
_TOLERANCIA_ABERTURA = time(9, 30)
_TOLERANCIA_FECHO = time(18, 0)

JANELAS_SEGUNDOS = (15, 60)
SAIDA_CSV = Path(__file__).resolve().parent / "wdof1_mfe_mae_semana_2026_09_04.csv"

#: Teto de trades POR LADO da estratégia, lido da assinatura dela (nunca
#: digitado aqui) -- ver `_avisar_teto_por_lado`.
_TETO_POR_LADO = int(
    inspect.signature(WdoGridReloadMaker.__init__).parameters["max_trades_per_side"].default
)


def _limite_servidor(instant_utc: datetime) -> datetime:
    """O limite a passar para `copy_ticks_range`: o relógio de PAREDE do
    servidor, rotulado como UTC.

    Não é o naive de `live/tick_feed.py` de propósito -- ver a seção "Fuso e
    fetch parcial" na docstring do módulo: o pacote `MetaTrader5` chama
    `.timestamp()` no limite, então um naive é reinterpretado no fuso da
    MÁQUINA e a janela anda o offset local inteiro (+3h nesta máquina). Um
    tz-aware UTC cujo relógio de parede já é o do servidor é imune a isso, em
    qualquer máquina."""
    return utc_to_server_wall_clock(instant_utc).replace(tzinfo=timezone.utc)


def _conferir_cobertura(bars: pd.DataFrame) -> None:
    """FALHA se algum pregão da semana estiver faltando ou truncado.

    Existe porque `copy_ticks_range` devolve dado incompleto em silêncio
    (nem exceção, nem `last_error`): sem esta conferência, "zero trades na
    sexta" é indistinguível de "o terminal ainda estava sincronizando", e já
    foi investigado uma vez como se fosse bug de produção."""
    brt = bars.index.tz_convert(MT5_SERVER_TIMEZONE)
    por_dia = pd.DataFrame({"dia": brt.date, "hora": brt.time}).groupby("dia")["hora"]
    cobertura = pd.DataFrame({
        "n": por_dia.size(), "primeiro": por_dia.min(), "ultimo": por_dia.max(),
    })
    print(f"[mfe_mae] cobertura por pregão (hora de Brasília, pregão {_ABERTURA_BRT}..{_FECHO_BRT}):",
          flush=True)
    for d, linha in cobertura.iterrows():
        print(f"[mfe_mae]   {d}  {int(linha['n']):>8,} ticks  "
              f"{linha['primeiro']} .. {linha['ultimo']}", flush=True)

    esperados = [PRIMEIRO_PREGAO + timedelta(days=i)
                 for i in range((ULTIMO_PREGAO - PRIMEIRO_PREGAO).days + 1)]
    esperados = [d for d in esperados if d.weekday() < 5]  # feriado vira falha explícita
    problemas = []
    for d in esperados:
        if d not in cobertura.index:
            problemas.append(f"{d}: NENHUM tick (feriado? ou terminal ainda sincronizando)")
            continue
        linha = cobertura.loc[d]
        if linha["primeiro"] > _TOLERANCIA_ABERTURA:
            problemas.append(f"{d}: começa em {linha['primeiro']}, depois de {_TOLERANCIA_ABERTURA}")
        if linha["ultimo"] < _TOLERANCIA_FECHO:
            problemas.append(f"{d}: termina em {linha['ultimo']}, antes de {_TOLERANCIA_FECHO}")
    if problemas:
        raise SystemExit(
            "[mfe_mae] FETCH PARCIAL -- o terminal devolveu menos do que a semana "
            "pedida, sem levantar erro nenhum:\n  " + "\n  ".join(problemas) +
            "\n[mfe_mae] Não grave CSV a partir disto: a análise leria 'não houve "
            "trade' onde na verdade não houve DADO. Confira que o terminal MT5 está "
            "aberto, logado e com o histórico de WDO@ sincronizado, e rode de novo."
        )


def buscar_ticks_semana() -> pd.DataFrame:
    """Barras degeneradas (1 por negócio) da semana, index em UTC de VERDADE.

    Usa `market_data_intraday.mt5_ticks_source.fetch_ticks_range` -- a mesma
    rota que `live/tick_feed.py` -- em vez de chamar o terminal na mão: é ela
    que faz a conversão `time_msc` (parede do servidor) -> UTC pelo FUSO
    declarado em `core.b3_session`, e não por uma constante."""
    erros: list[tuple[str, Exception]] = []
    ticks = fetch_ticks_range(
        SYMBOL,
        _limite_servidor(INICIO_SEMANA - _FOLGA_FETCH),
        _limite_servidor(FIM_SEMANA + _FOLGA_FETCH),
        on_error=lambda k, e: erros.append((k, e)),
    )
    if ticks.empty:
        raise SystemExit(
            f"[mfe_mae] 0 ticks para {SYMBOL} em {INICIO_SEMANA:%Y-%m-%d}.."
            f"{FIM_SEMANA:%Y-%m-%d} (UTC). Erros do terminal: {erros}"
        )
    # Recorte para a janela de verdade DEPOIS da conversão de fuso -- o dia
    # civil do servidor não é o dia civil em UTC (mesma disciplina de
    # `live/tick_feed.py::session_bars_until`).
    ticks = ticks[(ticks.index >= INICIO_SEMANA) & (ticks.index < FIM_SEMANA)]
    if ticks.empty:
        raise SystemExit(
            f"[mfe_mae] o terminal devolveu ticks, mas NENHUM dentro de "
            f"{INICIO_SEMANA}..{FIM_SEMANA} (UTC) -- fetch parcial."
        )
    bars = ticks_to_degenerate_bars(ticks).sort_index()
    bars.index.name = "time"
    _conferir_cobertura(bars)
    return bars


def _janela_antes(precos: pd.Series, volumes: pd.Series, entry_ts, segundos: int):
    """(volume_total, volatilidade_ticks) nos `segundos` imediatamente
    ANTES de `entry_ts`. `volatilidade_ticks` é o range (max-min) do preço
    na janela, em ticks."""
    inicio = entry_ts - pd.Timedelta(seconds=segundos)
    # Mascara booleana POSICIONAL, nao reindex por rotulo -- timestamps de
    # tick podem repetir (varios negocios no mesmo milissegundo), e
    # `Series.reindex` explode com "duplicate labels" nesse caso. `precos`/
    # `volumes` vem do MESMO DataFrame (`bars`), entao ja estao alinhados
    # posicao-a-posicao; a mesma mascara serve pros dois.
    mascara = (precos.index >= inicio) & (precos.index < entry_ts)
    janela = precos[mascara]
    vols = volumes[mascara]
    if len(janela) < 2:
        return 0.0, 0.0
    precos_arr = janela.to_numpy()
    vols_arr = vols.to_numpy()
    vol_total = float(vols_arr.sum())
    volatilidade_ticks = (precos_arr.max() - precos_arr.min()) / 0.5
    return vol_total, float(volatilidade_ticks)


def _avisar_teto_por_lado(trades: list) -> None:
    """Diz ALTO até que hora do pregão as entradas de fato foram.

    `WdoGridReloadMaker.max_trades_per_side` tem default 200 -- calibrado
    para M1 (~41 trades/dia). Em resolução TICK o robô rearma muito mais
    vezes, o teto satura cedo, e o CSV passa a descrever só o começo do
    pregão sem nada no arquivo dizer isso. A própria docstring da estratégia
    manda conferir o teto contra o número de trades real "para o teto nunca
    decidir o resultado em silêncio" -- é o que esta função faz. Não é falha
    de dado (por isso avisa, não aborta): é uma escolha de parâmetro cujo
    efeito precisa ficar visível para quem for ler o CSV."""
    if not trades:
        return
    por_dia: dict = {}
    for t in trades:
        brt = t.entry_ts.tz_convert(MT5_SERVER_TIMEZONE)
        d = por_dia.setdefault(brt.date(), {"long": 0, "short": 0, "ultima": brt})
        d[t.side] = d.get(t.side, 0) + 1
        d["ultima"] = max(d["ultima"], brt)
    print("[mfe_mae] entradas por pregão (hora de Brasília) -- confira o teto "
          f"`max_trades_per_side` ({_TETO_POR_LADO} por lado, default da estratégia):", flush=True)
    saturou = []
    for d in sorted(por_dia):
        info = por_dia[d]
        marca = ""
        if max(info["long"], info["short"]) >= _TETO_POR_LADO:
            marca = "  <-- TETO BATIDO"
            saturou.append(d)
        print(f"[mfe_mae]   {d}  long={info['long']:>4} short={info['short']:>4}  "
              f"última entrada {info['ultima'].time()}{marca}", flush=True)
    if saturou:
        print(f"[mfe_mae] AVISO: em {len(saturou)} de {len(por_dia)} pregões o robô parou de "
              f"entrar por ter batido `max_trades_per_side={_TETO_POR_LADO}`, NÃO por falta de "
              "sinal. O CSV descreve só o trecho do pregão até a última entrada acima -- "
              "não a semana inteira. O teto é calibrado para M1 (~41 trades/dia); em "
              "resolução TICK ele satura. Quem for analisar o CSV precisa saber disso.",
              flush=True)


def main() -> None:
    print(f"[mfe_mae] baixando ticks da semana ({PRIMEIRO_PREGAO}..{ULTIMO_PREGAO}) ...", flush=True)
    bars = buscar_ticks_semana()
    pregoes = sorted(set(bars.index.tz_convert(MT5_SERVER_TIMEZONE).date))
    print(f"[mfe_mae] {len(bars):,} ticks, {len(pregoes)} pregoes: {pregoes}", flush=True)

    cfg = montar_config()
    resultado = rodar(bars, cfg, profit_ticks=1, stop_ticks=16, level_spacing_ticks=1)
    trades = sorted(resultado.trades, key=lambda t: t.entry_ts)
    print(f"[mfe_mae] {len(trades)} trades (T1 S16, config real desta semana)", flush=True)
    _avisar_teto_por_lado(trades)

    precos = bars["close"]
    volumes = bars["volume"]
    tick_size = 0.5
    linhas = []
    for t in trades:
        caminho = precos[(precos.index >= t.entry_ts) & (precos.index <= t.exit_ts)]
        if t.side == "long":
            mfe_ticks = (caminho.max() - t.entry_price) / tick_size
            mae_ticks = (t.entry_price - caminho.min()) / tick_size
            mfe_price = caminho.max()
            mae_price = caminho.min()
        else:
            mfe_ticks = (t.entry_price - caminho.min()) / tick_size
            mae_ticks = (caminho.max() - t.entry_price) / tick_size
            mfe_price = caminho.min()
            mae_price = caminho.max()

        linha = {
            "entry_ts": t.entry_ts, "exit_ts": t.exit_ts, "side": t.side,
            "entry_price": t.entry_price, "exit_price": t.exit_price,
            "exit_reason": t.exit_reason.value, "pnl_brl": t.pnl_brl,
            "fees_total": t.fees_total, "duracao_seg": (t.exit_ts - t.entry_ts).total_seconds(),
            "n_ticks_no_trade": len(caminho),
            "mfe_ticks": mfe_ticks, "mfe_price": mfe_price,
            "mae_ticks": mae_ticks, "mae_price": mae_price,
        }
        for seg in JANELAS_SEGUNDOS:
            vol_total, volat = _janela_antes(precos, volumes, t.entry_ts, seg)
            linha[f"volume_{seg}s_antes"] = vol_total
            linha[f"volatilidade_ticks_{seg}s_antes"] = volat
        linhas.append(linha)

    saida = pd.DataFrame(linhas)
    saida.to_csv(SAIDA_CSV, index=False)
    print(f"[mfe_mae] gravado: {SAIDA_CSV} ({len(saida)} linhas, {len(saida.columns)} colunas)")
    print(f"[mfe_mae] liquido real da semana (T1 S16): R${saida['pnl_brl'].sum():.2f}")
    print(saida['exit_reason'].value_counts())


if __name__ == "__main__":
    main()
