"""Se o campeao estivesse posicionado numa empresa que quebra, o stop segura?

A pergunta do dono do capital
-----------------------------
`liquid_dual10` (o TOP-1 atual) so tem DOIS gatilhos que olham para o proprio
ativo:

  1. stop FIXO de -15% do preco de ENTRADA, checado todo pregao pelo engine
     (`backtest/engine_portfolio.py`). NUNCA sobe -- `current_stop` e setado
     uma vez em `initial_stop()` (`backtest/sizing.py`) na hora da entrada e
     nenhuma estrategia da familia dip emite `AdjustStop`. Nao e trailing.
  2. rotacao por momentum, mas SO no fim do mes (cadencia de `BuyTheDip` /
     `DipTop1Portfolio`).

Nao existe deteccao de volume anomalo, gap, volatilidade explodindo, nem
nada intra-mes alem do stop fixo. Historicamente o robo nunca esteve
posicionado nos piores dias das acoes abaixo -- foi calendario (o papel nao
estava no top-20/21-40 de liquidez, ou nao era rank-1 de momentum naquele
mes), nao defesa ativa. Este script FORCA a posicao e mede o estrago: o
stop de -15% segura, ou o preco passa por baixo dele (gap)?

Metodo -- entrada forcada
--------------------------
Para cada evento, uma subclasse-wrapper de `LiquidDual10`
(`_ForcedEntryDual10`, definida abaixo) roda o robo real sem tocar em uma
linha do seu comportamento organico. No pregao `data_entrada` (10 pregoes
ANTES do pior dia, contados no indice do PROPRIO papel, nao em dias
corridos), o wrapper ACRESCENTA um `Enter` do ticker-alvo a lista de acoes
que `LiquidDual10.on_bar` ja devolveu, com `size_hint = 1/10` (a fatia
normal de um sleeve do dual10). Como todo `Enter`/`Exit` do engine
(`strategy/base.py`), a ordem so e EXECUTADA na abertura do pregao
SEGUINTE (`current_stop` fica ancorado no preco de execucao real, nao no
close de `data_entrada`) -- e o mesmo contrato anti-look-ahead que vale
para toda entrada organica do sistema, e este script nao abre excecao para
a entrada forcada.

Posse (`_owner`): um `Enter` que nao passa por nenhum `LiquidSleeve` nasce
sem dono (`LiquidSleeves5._owner_of` so acha dono via `_owner` ou via
`is_eligible`). O wrapper atribui a posse EXPLICITAMENTE assim que enfileira
o Enter forcado, escolhendo o primeiro sleeve (dos 10) cujo `is_eligible`
for verdadeiro naquele dia; se nenhum for elegivel (o papel caiu fora das
duas faixas de liquidez naquele momento -- plausivel, e o motivo real de o
robo nunca ter comprado o papel sozinho), cai no sleeve 0. O sleeve dono e
IMPRESSO por evento -- e informacao, nao detalhe interno: e o sleeve que vai
carregar o prejuizo e cujo caixa fica reduzido daqui para frente.

Se o engine REJEITAR a entrada forcada (caixa insuficiente, quantidade zero
por causa do lote, sem vaga entre as `max_concurrent_positions` do config,
ou o papel sem dado naquele pregao), o script NAO silencia: confirma o
status no pregao seguinte (a posicao apareceu em `open_positions`? Se nao,
foi rejeitada) e imprime o motivo provavel antes de seguir.

Os tres modelos de preenchimento do stop (`BacktestConfig.stop_fill`, ver
`core/config.py`) rodam em backtests SEPARADOS por evento, porque e
exatamente onde a divergencia entre backtest e operacao real mora:

  stop_or_open  dispara se low<=stop, preenche em min(open, stop) -- hipotese
                OTIMISTA, comportamento historico de todo o diario.
  low           dispara se low<=stop, preenche no low -- limite inferior de
                qualquer feed intradiario com atraso.
  close         dispara se close<=stop, preenche no close -- o que um feed
                que so ve fechamento (ex. `ParquetCloseFeed`) faz de
                verdade: alem de sair pior, as vezes NEM DISPARA no dia do
                tombo (o close pode fechar acima do stop mesmo com o low
                tendo furado).

Os eventos (desastres reais, especificos da empresa, ja em `data/raw/`)
-----------------------------------------------------------------------
  DASA3.SA   2021-04-07  queda de -50,0% num unico pregao
  HAPV3.SA   2025-11-13  queda de -42,2% num unico pregao
  ENEV3.SA   2015-02-13  queda de -35,7% (grupo Eike, recuperacao judicial
                         de dez/2014)
  IRBR3.SA   2020-03-04  queda de -32,0% (fraude contabil revelada em
                         fev/2020)
  USIM5.SA   2024-07-26  queda de -23,6% num unico pregao
  AALR3.SA   2023-08-16  queda de -21,5% num unico pregao

  CONTROLE -- crash de mercado, nao especifico da empresa:
  BPAC11.SA  2020-03-12  queda de -26,9% (crash da Covid, empresa saudavel)

O controle serve para separar "o stop falha porque a empresa quebrou" de
"o stop falha porque o mercado inteiro caiu" -- os dois produzem gap, mas o
segundo nao e evidencia de fragilidade ESPECIFICA do robo.

Vies residual declarado -- o mais importante desta medicao
-------------------------------------------------------------
Estas 7 empresas SOBREVIVERAM. E POR ISSO que estao em `data/raw/`: o
pipeline de dados (`scripts/download_data.py`) so baixa ticker que existe
HOJE na B3. Uma empresa que efetivamente SAIU da bolsa (falencia, OPA de
fechamento de capital, incorporacao com cancelamento de registro) teria
uma serie de preco que simplesmente PARA de existir -- nao ha "pior dia"
para medir, nao ha pregao seguinte para o stop disparar, nao ha dado
nenhum. Este script mede o pior caso DENTRE OS QUE SOBREVIVERAM ao pior
dia; ele NAO consegue medir -- e nao tem como medir, dado o que existe em
`data/raw/` -- o caso em que a acao vai a zero e o stop nao tem em que
disparar porque o papel nunca mais negocia. Qualquer numero abaixo e um
piso otimista do estrago, nao o pior caso possivel.

Este e um script de MEDICAO DIAGNOSTICA, nao de aprovacao/reprovacao.
Nenhum criterio foi declarado antes de rodar porque a pergunta e "o que
acontece", nao "isto passa" -- o script NAO emite veredito.

Uso: .venv/Scripts/python.exe scripts/run_disaster_forced_entry.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from run_sleeve_validation import full_panels

from backtest.runner import run as run_bt
from backtest.sizing import plan_entry
from core.config import BacktestConfig
from core.models import ExitReason
from strategy.base import Enter
from strategy.liquid_dual10 import LiquidDual10

# ------------------------------------------------------------------ parametros

SELIC = "data/raw/selic.parquet"
SIZE_HINT = 1.0 / 10  # fatia normal de UM sleeve do dual10 (10 sleeves no total)
ENTRY_LEAD_BARS = 10  # data_entrada = pior dia - 10 pregoes (indice do PROPRIO papel)
PRE_BARS = 300        # inicio do backtest = data_entrada - 300 pregoes
POST_BARS = 120       # fim do backtest = pior dia + 120 pregoes
STOP_FILL_MODELS = ("stop_or_open", "low", "close")

# (ticker, pior dia, descricao, grupo) -- grupo "empresa" ou "controle"
EVENTOS = [
    ("DASA3.SA", "2021-04-07", "queda de -50,0% num unico pregao", "empresa"),
    ("HAPV3.SA", "2025-11-13", "queda de -42,2% num unico pregao", "empresa"),
    ("ENEV3.SA", "2015-02-13",
     "queda de -35,7% (grupo Eike, recuperacao judicial dez/2014)", "empresa"),
    ("IRBR3.SA", "2020-03-04",
     "queda de -32,0% (fraude contabil revelada fev/2020)", "empresa"),
    ("USIM5.SA", "2024-07-26", "queda de -23,6% num unico pregao", "empresa"),
    ("AALR3.SA", "2023-08-16", "queda de -21,5% num unico pregao", "empresa"),
    ("BPAC11.SA", "2020-03-12",
     "queda de -26,9% (crash Covid, controle -- empresa saudavel)", "controle"),
]

_UNIVERSE_CACHE: dict[str, pd.DataFrame] | None = None


def universe() -> dict[str, pd.DataFrame]:
    """Painel completo do POOL (o universo real do dual10), carregado uma vez.

    Precisa ser o POOL inteiro, nao so o ticker do evento: `LiquidDual10`
    ranqueia liquidez sobre o universo inteiro para decidir top-20/21-40 --
    passar so o ticker-alvo quebraria a propria mecanica do robo que se quer
    testar.
    """
    global _UNIVERSE_CACHE
    if _UNIVERSE_CACHE is None:
        _UNIVERSE_CACHE = full_panels()
    return _UNIVERSE_CACHE


def janela(ticker: str, pior_dia: str) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    """(inicio, data_entrada, fim) contados no indice do PROPRIO papel."""
    idx = universe()[ticker].index
    pior_ts = pd.Timestamp(pior_dia)
    if pior_ts not in idx:
        raise ValueError(f"{ticker}: pior dia {pior_dia} nao encontrado no painel.")
    pos_pior = idx.get_loc(pior_ts)
    pos_entrada = pos_pior - ENTRY_LEAD_BARS
    if pos_entrada < 0:
        raise ValueError(
            f"{ticker}: nao ha {ENTRY_LEAD_BARS} pregoes de historico antes de {pior_dia}."
        )
    pos_inicio = max(0, pos_entrada - PRE_BARS)
    pos_fim = min(len(idx) - 1, pos_pior + POST_BARS)
    return idx[pos_inicio], idx[pos_entrada], idx[pos_fim]


# --------------------------------------------------------------- entrada forcada


class _ForcedEntryDual10(LiquidDual10):
    """`LiquidDual10` real + UM `Enter` forcado no ticker-alvo em `data_entrada`.

    Delega tudo ao `LiquidDual10.on_bar` normal e so ACRESCENTA a acao forcada
    a lista que a classe-mae ja devolveu -- nenhuma outra linha de
    comportamento do robo muda. A confirmacao de preenchimento acontece no
    pregao SEGUINTE (`current_stop`/preco real vem de la, nunca do dia da
    decisao -- mesma regra anti-look-ahead de qualquer Enter do sistema).
    """

    name = "liquid_dual10_forced_probe"
    candidate = False

    def __init__(self, forced_ticker: str, forced_date: pd.Timestamp, **kwargs):
        super().__init__(**kwargs)
        self._forced_ticker = forced_ticker
        self._forced_date = pd.Timestamp(forced_date)
        self._forced_queued = False
        self._await_fill_check = False
        # status: "nao_alcancado" | "ja_aberta_organicamente" | "enfileirado"
        #       | "ok" | "rejeitado"
        self.forced_status: str = "nao_alcancado"
        self.forced_entry_date = None
        self.forced_entry_price: float | None = None
        self.forced_owner: int | None = None
        self.forced_owner_eligible: bool = False
        # Estado no momento em que o Enter forcado foi enfileirado -- so para
        # diagnostico de rejeicao (`medir_evento` usa isto para apontar a
        # causa real em vez de listar "poderia ser qualquer uma destas 4").
        self.forced_diag_open_count: int | None = None
        self.forced_diag_cash: float | None = None

    def on_bar(self, date, open_positions, cash_available):
        if self._await_fill_check:
            self._await_fill_check = False
            pos = open_positions.get(self._forced_ticker)
            if pos is not None:
                self.forced_status = "ok"
                self.forced_entry_date = pos.entry_date
                self.forced_entry_price = float(pos.entry_price)
            else:
                self.forced_status = "rejeitado"

        actions = list(super().on_bar(date, open_positions, cash_available))

        if not self._forced_queued and date == self._forced_date:
            self._forced_queued = True
            if self._forced_ticker in open_positions:
                # Nao deveria acontecer (a premissa e que o robo NUNCA chega
                # organicamente perto desses papeis) -- mas se acontecer, nao
                # forca por cima de uma posicao real.
                self.forced_status = "ja_aberta_organicamente"
            else:
                owner = 0
                eligivel_achado = False
                for i, s in enumerate(self._sleeves):
                    if s.is_eligible(self._forced_ticker, date):
                        owner = i
                        eligivel_achado = True
                        break
                self._owner[self._forced_ticker] = owner
                self.forced_owner = owner
                self.forced_owner_eligible = eligivel_achado
                self.forced_diag_open_count = len(open_positions)
                self.forced_diag_cash = float(cash_available)
                actions.append(Enter(
                    ticker=self._forced_ticker,
                    size_hint=SIZE_HINT,
                    reason="forced_disaster_probe",
                ))
                self._await_fill_check = True
                self.forced_status = "enfileirado"

        return actions


def rodar_forcado(ticker: str, inicio, data_entrada, fim, stop_fill: str):
    cfg = BacktestConfig(initial_capital=1000.0, lot_size=1, cash_yield_path=SELIC,
                          stop_fill=stop_fill)
    bot = _ForcedEntryDual10(forced_ticker=ticker, forced_date=data_entrada)
    r = run_bt(universe(), bot, cfg, start=str(inicio.date()), end=str(fim.date()))
    return r, bot, cfg


def rodar_referencia(inicio, fim, stop_fill: str):
    """Mesma janela, mesma config, `LiquidDual10` puro -- sem a entrada forcada."""
    cfg = BacktestConfig(initial_capital=1000.0, lot_size=1, cash_yield_path=SELIC,
                          stop_fill=stop_fill)
    bot = LiquidDual10()
    r = run_bt(universe(), bot, cfg, start=str(inicio.date()), end=str(fim.date()))
    return r


def diagnostica_rejeicao(ticker: str, data_entrada: pd.Timestamp, cfg: BacktestConfig, bot) -> str:
    """Aponta a causa PROVAVEL da rejeicao, em vez de listar as 4 possiveis.

    Usa o estado capturado pelo wrapper no momento em que o Enter foi
    enfileirado (`forced_diag_open_count`/`forced_diag_cash`) mais o preco de
    abertura do pregao seguinte no painel do proprio papel -- a MESMA
    referencia de preco que `engine_portfolio.py` usaria para preencher a
    ordem (`ref_price = open[data_entrada+1]`).
    """
    if bot.forced_diag_open_count is not None and \
            bot.forced_diag_open_count >= cfg.max_concurrent_positions:
        return (f"SEM VAGA: {bot.forced_diag_open_count}/{cfg.max_concurrent_positions} "
                "posicoes simultaneas ja ocupadas no momento do enfileiramento -- teto "
                "global do engine (config.max_concurrent_positions), nao um teto por "
                "sleeve. Com 10 sleeves competindo por 5 vagas, isto pode acontecer mesmo "
                "com caixa de sobra.")

    idx = universe()[ticker].index
    pos_entrada = idx.get_loc(data_entrada)
    if pos_entrada + 1 >= len(idx):
        return "PAPEL SEM DADO: nao ha pregao seguinte no painel do proprio ticker."
    dia_seguinte = idx[pos_entrada + 1]
    ref_price = float(universe()[ticker].at[dia_seguinte, "open"])
    if pd.isna(ref_price):
        return f"PAPEL SEM DADO: open de {dia_seguinte.date()} e NaN no painel."

    if bot.forced_diag_cash is not None:
        plan = plan_entry(bot.forced_diag_cash, ref_price, SIZE_HINT, cfg)
        if not plan.is_feasible:
            orcamento = bot.forced_diag_cash * SIZE_HINT
            return (f"CAIXA/QUANTIDADE: orcamento {orcamento:.2f} (10% de {bot.forced_diag_cash:.2f} "
                    f"de caixa livre) nao compra 1 lote a {ref_price:.2f}/acao (lot_size="
                    f"{cfg.lot_size}) depois de taxas -- quantidade calculada = 0.")

    return ("motivo residual nao identificado pelo diagnostico (engine rejeitou por razao "
            "nao coberta pelas checagens acima)")


def achar_trade(trades, ticker: str, entry_date):
    """Trade fechado que corresponde a entrada forcada (ticker + data de fill)."""
    alvo = pd.Timestamp(entry_date).date()
    for t in trades:
        if t.ticker == ticker and t.entry_date == alvo:
            return t
    return None


def medir_evento(i: int, total: int, ticker: str, pior_dia: str, motivo: str, grupo: str,
                  linhas: list, impactos: list) -> None:
    inicio, data_entrada, fim = janela(ticker, pior_dia)
    idx_ticker = universe()[ticker].index
    pior_ts = pd.Timestamp(pior_dia)
    pos_pior = idx_ticker.get_loc(pior_ts)

    print(f"\n=== evento {ticker} ({grupo}): {motivo} ===")
    print(f"  janela: {inicio.date()} (inicio) -> {data_entrada.date()} (data_entrada, "
          f"{ENTRY_LEAD_BARS} pregoes antes do pior dia) -> {pior_ts.date()} (pior dia) "
          f"-> {fim.date()} (fim)")

    for stop_fill in STOP_FILL_MODELS:
        r_forcado, bot, cfg = rodar_forcado(ticker, inicio, data_entrada, fim, stop_fill)
        r_ref = rodar_referencia(inicio, fim, stop_fill)

        capital_forcado = float(r_forcado.metrics["final_capital"])
        capital_referencia = float(r_ref.metrics["final_capital"])
        diff = capital_forcado - capital_referencia

        if stop_fill == STOP_FILL_MODELS[0]:
            if bot.forced_owner is not None:
                elig_txt = "elegivel por liquidez" if bot.forced_owner_eligible else \
                    "NENHUM sleeve elegivel nesta data -- fallback sleeve 0"
                print(f"  posse forcada: sleeve {bot.forced_owner} ({elig_txt})")

        row = {
            "ticker": ticker, "grupo": grupo, "stop_fill": stop_fill,
            "status": bot.forced_status,
        }

        if bot.forced_status != "ok":
            if bot.forced_status == "ja_aberta_organicamente":
                motivo_rejeicao = "ja havia posicao organica no ticker em data_entrada"
            elif bot.forced_status == "rejeitado":
                motivo_rejeicao = (
                    "Enter enfileirado em data_entrada NAO apareceu em open_positions no "
                    f"pregao seguinte -- {diagnostica_rejeicao(ticker, data_entrada, cfg, bot)}"
                )
            else:
                motivo_rejeicao = bot.forced_status
            print(f"  [REJEITADO] {ticker} modelo={stop_fill}: {motivo_rejeicao}")
            row.update({
                "entrada_preco": None, "stop_nivel": None, "saida_data": None,
                "saida_motivo": None, "saida_preco": None, "perda_pct": None,
                "gap_pp": None, "pregoes_ate_saida": None, "nao_fechou": None,
            })
            linhas.append(row)
            impactos.append({
                "ticker": ticker, "grupo": grupo, "stop_fill": stop_fill,
                "capital_forcado": capital_forcado, "capital_referencia": capital_referencia,
                "diff": diff,
            })
            print(f"evento {i}/{total} {ticker} modelo={stop_fill} ok", flush=True)
            continue

        trade = achar_trade(r_forcado.trades, ticker, bot.forced_entry_date)
        if trade is None:
            print(f"  [ANOMALIA] {ticker} modelo={stop_fill}: status=ok mas nenhum trade "
                  f"fechado encontrado para {ticker} entrada={bot.forced_entry_date} -- "
                  "pulando metricas deste modelo.")
            row.update({
                "entrada_preco": bot.forced_entry_price, "stop_nivel": None,
                "saida_data": None, "saida_motivo": None, "saida_preco": None,
                "perda_pct": None, "gap_pp": None, "pregoes_ate_saida": None,
                "nao_fechou": None,
            })
            linhas.append(row)
            print(f"evento {i}/{total} {ticker} modelo={stop_fill} ok", flush=True)
            continue

        entrada_preco = trade.entry_price
        stop_nivel = entrada_preco * (1.0 - cfg.stop_loss_pct)
        saida_preco = trade.exit_price
        saida_data = trade.exit_date
        saida_motivo = trade.exit_reason
        perda_pct = (saida_preco / entrada_preco - 1.0) * 100.0
        gap_pp = (stop_nivel - saida_preco) / stop_nivel * 100.0

        ultimo_dia_run = r_forcado.equity_curve.index[-1].date()
        nao_fechou = (saida_motivo == ExitReason.MANUAL and saida_data == ultimo_dia_run)

        try:
            pos_saida = idx_ticker.get_loc(pd.Timestamp(saida_data))
            pregoes_ate_saida = pos_saida - pos_pior
        except KeyError:
            pregoes_ate_saida = None

        row.update({
            "entrada_preco": entrada_preco, "stop_nivel": stop_nivel,
            "saida_data": saida_data, "saida_motivo": saida_motivo.value,
            "saida_preco": saida_preco, "perda_pct": perda_pct, "gap_pp": gap_pp,
            "pregoes_ate_saida": pregoes_ate_saida, "nao_fechou": nao_fechou,
        })
        linhas.append(row)
        impactos.append({
            "ticker": ticker, "grupo": grupo, "stop_fill": stop_fill,
            "capital_forcado": capital_forcado, "capital_referencia": capital_referencia,
            "diff": diff,
        })

        if nao_fechou:
            print(f"  [AVISO] {ticker} modelo={stop_fill}: posicao NAO fechou dentro da "
                  f"janela (+{POST_BARS} pregoes apos o pior dia) -- o valor de saida "
                  "acima e a liquidacao forcada de FIM DE BACKTEST, nao uma decisao real "
                  "do robo.")

        print(f"evento {i}/{total} {ticker} modelo={stop_fill} ok", flush=True)


# ------------------------------------------------------------------------ tabela


def imprime_tabela(linhas: list) -> None:
    hdr = (f"{'ticker':10s} {'grupo':9s} {'stop_fill':13s} {'status':22s} "
           f"{'entrada':>9s} {'stop':>9s} {'saida_data':>11s} {'motivo_saida':>17s} "
           f"{'saida_px':>9s} {'perda%':>8s} {'gap_pp':>8s} {'pregoes':>8s} {'janela':>10s}")
    print("\n" + "=" * len(hdr))
    print("TABELA POR EVENTO x MODELO DE PREENCHIMENTO DO STOP")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for r in linhas:
        if r["status"] != "ok":
            print(f"{r['ticker']:10s} {r['grupo']:9s} {r['stop_fill']:13s} "
                  f"{r['status']:22s} {'--':>9s} {'--':>9s} {'--':>11s} {'--':>17s} "
                  f"{'--':>9s} {'--':>8s} {'--':>8s} {'--':>8s} {'--':>10s}")
            continue
        janela_txt = "NAO fechou" if r["nao_fechou"] else "fechou"
        pregoes_txt = "--" if r["pregoes_ate_saida"] is None else str(r["pregoes_ate_saida"])
        print(f"{r['ticker']:10s} {r['grupo']:9s} {r['stop_fill']:13s} "
              f"{r['status']:22s} {r['entrada_preco']:9.2f} {r['stop_nivel']:9.2f} "
              f"{str(r['saida_data']):>11s} {r['saida_motivo']:>17s} "
              f"{r['saida_preco']:9.2f} {r['perda_pct']:7.1f}% {r['gap_pp']:7.1f}pp "
              f"{pregoes_txt:>8s} {janela_txt:>10s}")
    print("=" * len(hdr))


def imprime_resumo(linhas: list) -> None:
    print("\nRESUMO -- empresa (6 eventos especificos) vs controle (crash de mercado)")
    print(f"{'stop_fill':13s} {'grupo':9s} {'n_ok':>5s} {'perda mediana%':>15s} "
          f"{'pior gap atravessado(pp)':>25s}")
    for stop_fill in STOP_FILL_MODELS:
        for grupo in ("empresa", "controle"):
            subset = [r for r in linhas
                      if r["stop_fill"] == stop_fill and r["grupo"] == grupo
                      and r["status"] == "ok"]
            n_total = sum(1 for r in linhas if r["stop_fill"] == stop_fill and r["grupo"] == grupo)
            if not subset:
                print(f"{stop_fill:13s} {grupo:9s} {'0/' + str(n_total):>5s} "
                      f"{'sem dado (tudo rejeitado)':>15s} {'--':>25s}")
                continue
            perdas = [r["perda_pct"] for r in subset]
            gaps = [r["gap_pp"] for r in subset]
            print(f"{stop_fill:13s} {grupo:9s} {f'{len(subset)}/{n_total}':>5s} "
                  f"{np.median(perdas):14.1f}% {max(gaps):24.1f}pp")


def imprime_impacto(impactos: list) -> None:
    hdr = (f"{'ticker':10s} {'grupo':9s} {'stop_fill':13s} {'capital c/ forcada':>19s} "
           f"{'capital s/ (ref)':>17s} {'diferenca':>12s}")
    print("\n" + "=" * len(hdr))
    print("IMPACTO NA CONTA -- capital final COM a posicao forcada menos SEM ela")
    print("(a posicao e 1/10 do capital; o impacto na conta nao e igual a perda na posicao)")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for r in impactos:
        print(f"{r['ticker']:10s} {r['grupo']:9s} {r['stop_fill']:13s} "
              f"R$ {r['capital_forcado']:14,.2f} R$ {r['capital_referencia']:13,.2f} "
              f"R$ {r['diff']:9,.2f}")
    print("=" * len(hdr))


def main() -> None:
    print(__doc__.split("Uso:")[0])

    linhas: list = []
    impactos: list = []
    total = len(EVENTOS)
    for i, (ticker, pior_dia, motivo, grupo) in enumerate(EVENTOS, 1):
        try:
            medir_evento(i, total, ticker, pior_dia, motivo, grupo, linhas, impactos)
        except ValueError as exc:
            print(f"\n[EVENTO PULADO] {ticker}: {exc}", flush=True)
            print(f"evento {i}/{total} {ticker} modelo=-- pulado (erro de janela)", flush=True)

    imprime_tabela(linhas)
    imprime_resumo(linhas)
    imprime_impacto(impactos)

    print("\nEsta e uma medicao diagnostica -- nenhum criterio de aprovacao foi declarado "
          "e nenhum veredito e emitido. Lembrete do vies residual (ver docstring no topo): "
          "as 7 empresas acima SOBREVIVERAM ao pior dia (por isso tem dado em data/raw/); "
          "uma empresa que saiu de fato da bolsa nao pode ser medida por este metodo.")


if __name__ == "__main__":
    main()
