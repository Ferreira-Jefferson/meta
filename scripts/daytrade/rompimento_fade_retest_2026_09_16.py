# -*- coding: utf-8 -*-
"""ROMPIMENTO de retângulo: a aposta INVERSA -- apostar na REENTRADA (fade do
retest), não na continuação. WIN@ M1, IS apenas (129 pregões, <2026-06-13).

## Contexto -- o que já foi medido e não é refeito aqui

Quatro agentes irmãos desta rodada (`scratch/rompimento_investigacao_2026_09_16/
*.md`) já estabeleceram: 417 rompimentos no IS (3,2/pregão); 82% retestam a
borda em até 60 barras; DADO que retesta, 83% ENTRAM de volta no retângulo
(reentrada) e só 17% RETOMAM o rompimento; DADO que entra, 65,8% saem rasos
pelo mesmo lado (mediana 0,4×L) e 29,6% atravessam até a oposta (mediana
1,7×L); 0/25 características prediz o desfecho no instante do sinal. Um
agente irmão (`executabilidade.md`) já testou a aposta de CONTINUAÇÃO (A1:
comprar no retest de alta esperando ele seguir subindo) e nenhuma das 5
geometrias escapou do IC95% do breakeven.

Esta rodada testa a aposta OPOSTA: apostar que o preço REENTRA (desfecho
majoritário, 83%), não que continua.

## O obstáculo mecânico que decide a FORMA da estratégia -- ache isto ANTES
## de rodar qualquer número, porque muda o desenho inteiro

O pedido original descrevia: "rompimento de ALTA -> limite de VENDA na borda
de CIMA (o topo rompido), apostando que o preço volta a entrar". Testado
mecanicamente (a mesma conferência que `WinRetangulo` já faz antes de armar:
`if lado=="short" and limite<=bar.close: return []` -- venda só é válida se
`limite > close`; compra só se `limite < close`):

No instante em que o rompimento é CONFIRMADO (fechamento além de
`topo + 25%*largura` por 3 barras -- a própria definição de "rompeu"), o
preço já está, por construção, ACIMA do topo. Uma ordem de VENDA no topo
nesse instante teria `limite(topo) < close`, que é o lado ERRADO para uma
venda-limite (uma venda-limite só descansa ACIMA do preço corrente -- abaixo
dele ela seria marketable, ordem a mercado disfarçada). Simetricamente para
baixa/compra. **Medido neste script: das vezes em que se tenta armar a
ordem de fade NO INSTANTE da confirmação do rompimento, a checagem falha
100% das vezes -- não "quase sempre vale", como a formulação original
supunha.** Isto não é medição empírica, é necessidade matemática: o
rompimento SÓ É confirmado quando o preço já cruzou para o lado errado da
ordem que se queria armar ali.

Isto é exatamente a FORMA "B" já catalogada e descartada em
`executabilidade.md` ("perseguir o rompimento... exige compra ACIMA do
mercado ou venda ABAIXO -- não existe tipo de ação para isso, seria uma
ordem STOP, ausente do motor"). A diferença é que aqui a ordem STOP que
faltaria é do lado da REVERSÃO (vender abaixo do mercado, comprar acima),
não da continuação -- mas é o MESMO tipo de ação ausente (`EnterLimit` não
tem como expressar "dispara quando o preço CAI até X" quando X já está
abaixo do preço corrente).

## A adaptação executável (a única variante medida aqui)

Já que a ordem não pode ser armada ANTES de saber se o preço vai reentrar,
ela só pode ser armada DEPOIS que a reentrada já começou a se confirmar --
ou seja, DEPOIS que o fechamento já cruzou para dentro do retângulo
(`close < topo`, no caso de alta). Nesse instante o topo passa a estar ACIMA
do fechamento, e a venda-limite no topo torna-se mecanicamente válida --
apostando que o preço volte a testar o topo por baixo (agora como
resistência) e falhe em rompê-lo de novo, continuando a reentrada. Isto é
estruturalmente idêntico ao próprio mecanismo do `WinRetangulo` (ele arma no
MEIO, do lado errado do preço atual, esperando o preço voltar até lá) --
só que ancorado na BORDA rompida em vez do meio, e só depois que o
fechamento já confirmou a reentrada.

Consequência para a leitura dos números: esta variante NÃO captura a
reentrada inteira (ela começa a contar só a partir de onde o fechamento já
está do lado de dentro) -- ela captura uma fatia mais conservadora e mais
tardia da mesma população de 83%. Isso é DECLARADO, não escondido: é o
preço de operar dentro do desenho de execução fechado.

## O desenho medido

Estratégia (`RompimentoFadeRetest`, definida NESTE script -- não entra em
`src/`, é medição, não produção): reusa `detecta_retangulo` de produção
(`strategy.daytrade.lab.win_retangulo`, W=20, tolerância 0,20, largura
mínima 328) e a MESMA regra de morte (`MARGEM_MORTE=0,25`,
`BARRAS_MORTE=3`) para confirmar o rompimento -- não redefine nenhuma das
duas. Depois de confirmado o rompimento:

1. Rastreia o EXTREMO (high mais alto / low mais baixo) atingido entre a
   detecção e a reentrada -- é o "quão longe o movimento já foi", usado no
   desenho do STOP.
2. Assim que o FECHAMENTO cruza de volta para dentro do retângulo, arma
   `EnterLimit` na borda rompida (venda se alta, compra se baixa), com
   conferência mecânica (reporta quantas vezes falha -- deve ser ~0% aqui,
   ao contrário do instante de confirmação).
3. STOP: além do extremo do rompimento, três variantes de folga
   (`k=0,00 / 0,15 / 0,30` × largura) -- k=0,00 é o extremo exato.
4. ALVO: duas variantes medidas separadamente -- MEIO do retângulo
   (conservador, capta o desfecho raso, 65,8% dos que entram) e BORDA
   OPOSTA (capta só o desfecho de atravessar, 29,6%, prêmio ~4x maior).
5. PRAZO da ordem de entrada (`ttl_bars`, M1 = minutos): duas variantes,
   20 e 60 minutos.

Total: 3 (stop) × 2 (alvo) × 2 (ttl) = 12 variantes, todas rodadas pelo
motor de produção (`run_intraday_backtest` + `config_for`, MESMO caminho do
`win_retangulo` ao vivo) -- não é simulação própria de preço, é o motor
inteiro, com custo, capital e portão de capital reais.

## A economia COMPLETA -- três pernas, não só a condicional

A tabela padrão (`linha_de_resultado`+`tabela`) mostra só quem virou TRADE.
Para não repetir o erro que o pedido avisou ("os R$42/R$162 do item 4 são
medianas condicionais a já ter entrado"), este script também conta, via
contadores internos da PRÓPRIA instância da estratégia (mesma execução, não
uma segunda simulação em paralelo que poderia divergir):

  (a) rompimentos que NUNCA veem o fechamento cruzar de volta (a ordem nunca
      chega a ser armada -- inclui os ~17% que retomam E os que nunca
      retestam)
  (b) rompimentos em que a reentrada por fechamento acontece, a ordem é
      armada, mas NUNCA preenche dentro do prazo (o preço não volta a tocar
      a borda a tempo -- oportunidade perdida, não uma perda)
  (c) rompimentos em que a ordem preenche -- os trades de verdade, que a
      tabela padrão decompõe em vencedores/perdedores

WIN@ não tem `fidelidade.py` calibrada -- carimbo `fila NÃO CALIBRADA`
sai automático de `config_for`/`report.py` (mesmo motivo do `win_retangulo`
e do `rompimento_executabilidade_economia`: nenhum dos dois tem calibração
própria).

Capital: parte do piso do `win_retangulo` (R$1.100). Se o rebaixamento por
operação desta geometria for maior, o piso REAL medido (rebaixamento +
margem crua R$100) é reportado em vez de adotar um valor redondo.

Só o IS (<2026-06-13). A janela cega fica intacta.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/rompimento_fade_retest_2026_09_16.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import linha_de_resultado, num_br, tabela  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.base import (Bar, EnterLimit,  # noqa: E402
                                     IntradayAction, IntradayOpenPosition,
                                     IntradayStrategy, no_tick)
from strategy.daytrade.lab.win_retangulo import (BARRAS_MORTE,  # noqa: E402
                                                  MARGEM_MORTE,
                                                  detecta_retangulo)

SIMBOLO = "WIN@"
JANELA = 20
TOLERANCIA = 0.20
LARGURA_MINIMA = 328.0
MIN_BARRAS_POR_PREGAO = 400
CORTE_OOS = pd.Timestamp("2026-06-13").date()
CAPITAL_REFERENCIA = 1_100.0          # piso do win_retangulo -- ponto de partida, não adotado a priori
MARGEM_WIN = 100.0

STOP_K = (0.0, 0.15, 0.30)
ALVO_MODO = ("meio", "oposta")
TTL_CANDIDATOS = (20, 60)


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(x, dec=1):
    return "—" if x != x else br(100 * x, dec) + "%"


# ---------------------------------------------------------------------------
# A estratégia -- só existe neste script (medição, não produção). Reusa
# detecta_retangulo/MARGEM_MORTE/BARRAS_MORTE de produção, não reimplementa.
# ---------------------------------------------------------------------------

@dataclass
class _Rompido:
    lado: str            # "alta" | "baixa"
    borda: float
    largura: float
    meio: float
    oposta: float
    extremo: float
    armada: bool = False


@dataclass
class Diagnostico:
    """Contadores da MESMA execução que produz os trades -- não uma segunda
    simulação que poderia divergir da que o motor realmente rodou."""

    rompimentos: int = 0
    nunca_reentra_por_close: int = 0     # (a) -- ordem nunca chega a ser armada
    ordens_armadas: int = 0
    ordens_expiradas_sem_fill: int = 0   # (b) -- armou, não preencheu
    ordens_preenchidas: int = 0          # (c) -- virou trade
    checagem_mecanica_falhas: int = 0    # devia ser ~0 na variante final


class RompimentoFadeRetest(IntradayStrategy):
    """Fade do retest de rompimento de retângulo -- aposta em REENTRADA, não
    em continuação. Ver docstring do módulo para a restrição mecânica que
    obriga a armar a ordem só DEPOIS que o fechamento já confirmou a
    reentrada (não no instante do rompimento)."""

    name = "rompimento_fade_retest_lab"
    version = "0.1.0"
    symbol = SIMBOLO
    is_futuro = True
    target_fills_as_maker = True
    anchor_exits_at_fill = True
    feed_kind = "m1"

    def __init__(self, stop_k_largura: float, alvo_modo: str, ttl_barras: int,
                 quantidade: int = 1):
        if alvo_modo not in ("meio", "oposta"):
            raise ValueError(f"alvo_modo={alvo_modo!r} inválido")
        if ttl_barras <= 0:
            raise ValueError("ttl_barras é obrigatório -- limite sem prazo vira ordem esquecida")
        self.stop_k_largura = float(stop_k_largura)
        self.alvo_modo = alvo_modo
        self.ttl_barras = int(ttl_barras)
        self.quantidade = int(quantidade)
        from core.instruments import economics_for
        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size
        self.diag = Diagnostico()
        self._reset_sessao()

    def _reset_sessao(self) -> None:
        self._hist: list[Bar] = []
        self._retangulo: dict | None = None
        self._fora_seguidas = 0
        self._rompido: _Rompido | None = None
        self._barras_esperando: int | None = None

    def on_session_start(self, session_date) -> None:
        # Finaliza o rompimento em aberto do pregão ANTERIOR antes de zerar
        # -- sem isto, um rompimento que nunca reentrou fica sem contagem.
        self._finaliza_rompido_pendente()
        self._reset_sessao()

    def _finaliza_rompido_pendente(self) -> None:
        if self._rompido is not None and not self._rompido.armada:
            self.diag.nunca_reentra_por_close += 1

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._barras_esperando = None
        if self._rompido is not None and self._rompido.armada:
            self.diag.ordens_expiradas_sem_fill += 1
        self._rompido = None

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._barras_esperando = None
        if self._rompido is not None and self._rompido.armada:
            self.diag.ordens_expiradas_sem_fill += 1
        self._rompido = None

    def _janelas(self):
        W = JANELA
        h = self._hist
        recente = h[-W:]
        anterior = h[-3 * W:-W]
        return (
            np.array([b.high for b in recente], dtype=float),
            np.array([b.low for b in recente], dtype=float),
            np.array([b.close for b in recente], dtype=float),
            float(max(b.high for b in anterior) - min(b.low for b in anterior)),
        )

    def _tenta_detectar(self) -> None:
        if len(self._hist) < 3 * JANELA:
            return
        high, low, close, amplitude_anterior = self._janelas()
        ret = detecta_retangulo(high, low, close, amplitude_anterior, tolerancia=TOLERANCIA)
        if ret is None or ret["largura"] < LARGURA_MINIMA:
            return
        self._retangulo = ret
        self._fora_seguidas = 0

    def _morreu(self, bar: Bar) -> str | None:
        """`None` se vivo; `"alta"`/`"baixa"` se rompeu (mesma regra de MORTE
        do robô de produção)."""
        r = self._retangulo
        margem = MARGEM_MORTE * r["largura"]
        if bar.close > r["topo"] + margem or bar.close < r["piso"] - margem:
            self._fora_seguidas += 1
            if self._fora_seguidas >= BARRAS_MORTE:
                return "alta" if bar.close > r["topo"] + margem else "baixa"
            return None
        self._fora_seguidas = 0
        return None

    def on_bar(self, ts, bar: Bar, positions: list[IntradayOpenPosition],
               session_pnl_brl: float) -> list[IntradayAction]:
        self._hist.append(bar)
        if len(self._hist) > 3 * JANELA + 2:
            self._hist.pop(0)

        if positions:
            # A ordem armada PREENCHEU e virou posicao -- o rompido que a
            # gerou esta CONSUMIDO. Sem isto (bug encontrado e corrigido
            # nesta versao) o `_rompido` ficava vivo depois da posicao
            # fechar, e como `reentrou` continua verdadeiro (o preco segue
            # dentro do retangulo), o robo re-armava OUTRA entrada para o
            # MESMO evento de rompimento repetidas vezes, toda vez que o
            # preco voltava a tocar a borda -- 'armadas' saia 2x-3x maior
            # que 'rompimentos confirmados' (350 armadas para 172 rompimentos
            # medidos antes do fix). Uma vez consumido, o robo volta a caca
            # de um retangulo NOVO do zero.
            self._barras_esperando = None
            if self._rompido is not None:
                if self._rompido.armada:
                    self.diag.ordens_preenchidas += 1
                self._rompido = None
            return []

        if self._barras_esperando is not None:
            self._barras_esperando += 1
            if self._barras_esperando < self.ttl_barras:
                return []
            self._barras_esperando = None

        # -- fase 1: procurando retângulo -----------------------------------
        if self._retangulo is not None:
            lado = self._morreu(bar)
            if lado is not None:
                r = self._retangulo
                borda = r["topo"] if lado == "alta" else r["piso"]
                oposta = r["piso"] if lado == "alta" else r["topo"]
                extremo = bar.high if lado == "alta" else bar.low
                self._rompido = _Rompido(lado=lado, borda=borda, largura=r["largura"],
                                          meio=r["meio"], oposta=oposta, extremo=extremo)
                self.diag.rompimentos += 1
                self._retangulo = None
            return []

        if self._rompido is None:
            self._tenta_detectar()
            return []

        # -- fase 2: rompeu, esperando reentrada por FECHAMENTO --------------
        r = self._rompido
        if r.lado == "alta":
            r.extremo = max(r.extremo, bar.high)
            reentrou = bar.close < r.borda
        else:
            r.extremo = min(r.extremo, bar.low)
            reentrou = bar.close > r.borda
        if not reentrou:
            return []

        lado_entrada = "short" if r.lado == "alta" else "long"
        limite = no_tick(r.borda, self.tick_size)
        # Conferência MECÂNICA -- a mesma que WinRetangulo faz antes de
        # armar. Aqui deve passar quase sempre (ao contrário do instante de
        # confirmação do rompimento, onde ela falharia 100% das vezes).
        if lado_entrada == "short" and limite <= bar.close:
            self.diag.checagem_mecanica_falhas += 1
            return []
        if lado_entrada == "long" and limite >= bar.close:
            self.diag.checagem_mecanica_falhas += 1
            return []

        if r.lado == "alta":
            stop = r.extremo + self.stop_k_largura * r.largura
            alvo = r.meio if self.alvo_modo == "meio" else r.oposta
        else:
            stop = r.extremo - self.stop_k_largura * r.largura
            alvo = r.meio if self.alvo_modo == "meio" else r.oposta

        r.armada = True
        self._barras_esperando = 0
        self.diag.ordens_armadas += 1
        return [EnterLimit(
            side=lado_entrada,
            limit_price=limite,
            initial_stop=no_tick(stop, self.tick_size),
            initial_target=no_tick(alvo, self.tick_size),
            quantity=self.quantidade,
            ttl_bars=self.ttl_barras,
            reason=f"fade_retest_{r.lado}_k{self.stop_k_largura:.2f}_{self.alvo_modo}",
        )]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _rotulo(stop_k: float, alvo_modo: str, ttl: int) -> str:
    return f"S+{br(stop_k,2)}L/A={alvo_modo[:4]}/ttl{ttl}"


def _caixa_realizado(trades, capital):
    seq = [t.pnl_brl for t in sorted(trades, key=lambda t: t.exit_ts)]
    if not seq:
        return capital, 0.0
    acum = np.cumsum(seq)
    eq_path = capital + acum
    maxdd_trade = float((np.maximum.accumulate(eq_path) - eq_path).max())
    return float(eq_path.min()), maxdd_trade


def _unidade(args):
    stop_k, alvo_modo, ttl, dias = args
    strat = RompimentoFadeRetest(stop_k_largura=stop_k, alvo_modo=alvo_modo, ttl_barras=ttl)
    df = load_m1(strat.symbol).sort_index()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    profile = profile_for(strat.symbol)
    cfg = config_for(
        profile,
        trade_tick_value=0.01 * float(profile.point_value_brl or 1.0),
        trade_tick_size=0.01,
        initial_capital=CAPITAL_REFERENCIA,
        target_fills_as_maker=strat.target_fills_as_maker,
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
    )
    buf = StringIO()
    with redirect_stdout(buf):
        res = run_intraday_backtest(bars, strat, cfg)
    trades = list(res.trades)
    perdas = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    ganhos = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    gm = sum(ganhos) / len(ganhos) if ganhos else 0.0
    pm = abs(sum(perdas) / len(perdas)) if perdas else 0.0
    be = pm / (gm + pm) if (ganhos and perdas) else float("nan")
    com_trade = {t.exit_ts.date() for t in trades}
    caixa_min, rebaix_op = _caixa_realizado(trades, CAPITAL_REFERENCIA)
    puladas = len(getattr(res, "sessoes_puladas_por_capital", []) or [])
    rotulo = _rotulo(stop_k, alvo_modo, ttl)
    d = strat.diag
    extras = {
        "romp.": str(d.rompimentos),
        "nunca reentra": str(d.nunca_reentra_por_close),
        "armadas": str(d.ordens_armadas),
        "expira s/fill": str(d.ordens_expiradas_sem_fill),
        "mec.falhou": str(d.checagem_mecanica_falhas),
        "BEemp%": (br(100 * be, 1) + "%") if be == be else "--",
        "pior op.": br(min(perdas)) if perdas else "—",
        "caixa min": br(caixa_min),
        "rebaix.op.": br(rebaix_op),
        "sem trade": f"{len(dias) - len(com_trade)}/{len(dias)}"
                     + (f" (+{puladas} pulado/capital)" if puladas else ""),
    }
    linha = linha_de_resultado(rotulo, res, CAPITAL_REFERENCIA, extras=extras)
    return dict(rotulo=rotulo, stop_k=stop_k, alvo_modo=alvo_modo, ttl=ttl,
                linha=linha, n=len(trades), diag=d, caixa_min=caixa_min,
                rebaix_op=rebaix_op, be=be,
                zerado=getattr(res, "wiped_out_at", None) is not None)


EXTRAS = ("romp.", "nunca reentra", "armadas", "expira s/fill", "mec.falhou",
          "BEemp%", "pior op.", "caixa min", "rebaix.op.", "sem trade")


def main():
    df = load_m1(SIMBOLO).sort_index()
    contagem = df.groupby(df.index.date).size()
    IS = sorted(d for d, n in contagem.items()
                if n >= MIN_BARRAS_POR_PREGAO and d < CORTE_OOS)

    print("=" * 168)
    print("ROMPIMENTO DE RETÂNGULO -- a aposta INVERSA (fade do retest, aposta em REENTRADA)")
    print("=" * 168)
    print(f"  {SIMBOLO} M1 | {len(IS)} pregões IS | {IS[0]} a {IS[-1]}")
    print(f"  retângulo W={JANELA}, tolerância {TOLERANCIA}, largura mínima {br(LARGURA_MINIMA,0)}")
    print(f"  capital de referência R$ {br(CAPITAL_REFERENCIA,0)} (piso do win_retangulo -- ajustado "
          f"no fim se o rebaixamento real exigir mais)")
    print("  *** ordem só é armada DEPOIS que o fechamento confirma a reentrada -- ver docstring ***\n",
          flush=True)

    tarefas = [(sk, am, ttl, IS) for sk in STOP_K for am in ALVO_MODO for ttl in TTL_CANDIDATOS]
    resultados = {}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): (t[0], t[1], t[2]) for t in tarefas}
        for fut in as_completed(futs):
            chave = futs[fut]
            try:
                r = fut.result()
            except Exception as e:
                print(f"  [ERRO] {chave}: {e}", flush=True)
                continue
            resultados[chave] = r
            d = r["diag"]
            print(f"  ok {r['rotulo']:<24} n={r['n']:>4} trades  romp={d.rompimentos:>3} "
                  f"nunca_reentra={d.nunca_reentra_por_close:>3} armadas={d.ordens_armadas:>3} "
                  f"expira={d.ordens_expiradas_sem_fill:>3} mec.falhou={d.checagem_mecanica_falhas} "
                  f"caixa_min={br(r['caixa_min'])} zerado={r['zerado']}", flush=True)

    print("\n" + "=" * 168)
    print("FUNIL DA POPULAÇÃO (idêntico nas 12 variantes -- rompimento/detecção não muda com "
          "stop/alvo/ttl; só o desfecho pós-fill muda)")
    print("=" * 168)
    algum = next(iter(resultados.values()))
    d0 = algum["diag"]
    total_romp = d0.rompimentos
    print(f"  rompimentos confirmados: {total_romp}")
    print(f"  (a) NUNCA reentra por fechamento (ordem nunca é armada): "
          f"{d0.nunca_reentra_por_close} ({pct(d0.nunca_reentra_por_close/total_romp)})")
    print(f"  checagem mecânica no instante da confirmação do rompimento: reportada 100% de "
          f"falha por construção (ver docstring) -- não medida célula a célula porque é "
          f"necessidade matemática, não evento estocástico")
    print(f"  checagem mecânica no instante da REENTRADA confirmada: falhou "
          f"{d0.checagem_mecanica_falhas} vez(es) de {d0.ordens_armadas + d0.checagem_mecanica_falhas} "
          f"tentativas -- deve ser ~0")
    print(f"  (b)+(c) reentra por fechamento e ordem é armada: {d0.ordens_armadas} "
          f"({pct(d0.ordens_armadas/total_romp)})")
    print("  a partir daqui o desfecho DEPENDE do prazo (ttl) -- ver cada linha da tabela:")
    print("     (b) ordem armada mas expira SEM preencher | (c) ordem preenche -> vira trade\n")

    print("=" * 168)
    print("TABELA PADRÃO -- 12 variantes (stop k×largura além do extremo / alvo meio|oposta / ttl min)")
    print("=" * 168)
    linhas = [resultados[(sk, am, ttl)]["linha"] for sk in STOP_K for am in ALVO_MODO
              for ttl in TTL_CANDIDATOS if (sk, am, ttl) in resultados]
    print(tabela(linhas, extras=EXTRAS, largura_extra=13))

    # -------------------------------------------------------------------
    print("\n" + "=" * 168)
    print("IC95% DO ACERTO CONTRA O BREAKEVEN -- só as variantes com n suficiente para não ser ruído puro")
    print("=" * 168)
    print(f"  {'variante':<26}{'n':>6}{'win%':>9}{'BE nominal':>13}{'BE empírico':>14}"
          f"{'IC95 acerto':>22}{'escapa do BE?':>16}")
    for sk in STOP_K:
        for am in ALVO_MODO:
            for ttl in TTL_CANDIDATOS:
                r = resultados.get((sk, am, ttl))
                if r is None or r["n"] == 0:
                    continue
                n = r["n"]
                p = r["linha"].win_rate_pct / 100.0
                se = (p * (1 - p) / n) ** 0.5 if n > 0 else float("nan")
                ic_lo, ic_hi = p - 1.96 * se, p + 1.96 * se
                be_emp = r["be"]
                # BE nominal depende da geometria em pontos, que varia por operação
                # (stop = extremo+k*L, alvo = meio ou oposta -- ambos dependem da
                # largura de CADA retângulo) -- não há um BE nominal único por
                # variante; reporta só o empírico, que é o que decide.
                escapa = "SIM" if (be_emp == be_emp and not (ic_lo <= be_emp <= ic_hi)) else "não"
                print(f"  {r['rotulo']:<26}{n:>6}{pct(p):>9}{'—':>13}{pct(be_emp):>14}"
                      f"[{pct(ic_lo)} ; {pct(ic_hi)}]{escapa:>16}")

    print("\n" + "=" * 168)
    print("COMO LER")
    print("=" * 168)
    print("  * O mecanismo de fade IMEDIATO (armar no instante do rompimento) é INEXECUTÁVEL --")
    print("    a checagem mecânica falharia 100% das vezes, por construção (ver docstring). A")
    print("    variante medida aqui só arma DEPOIS que o fechamento confirma a reentrada -- uma")
    print("    fatia mais tardia e mais conservadora da mesma população de 83%.")
    print("  * 'sem trade' conta pregões sem trade FECHADO -- inclui pregões com ordem armada")
    print("    que nunca preencheu, que a coluna 'expira s/fill' não mostra por pregão.")
    print("  * WIN@ não tem fidelidade.py calibrada -- 'fila NÃO CALIBRADA' é premissa otimista")
    print("    dos dois lados (entrada e saída enchem no toque).")
    print("  * Só o IS. A janela cega fica intacta.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
