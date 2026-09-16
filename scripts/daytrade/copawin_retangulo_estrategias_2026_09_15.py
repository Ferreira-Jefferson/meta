# -*- coding: utf-8 -*-
"""WIN@: as DUAS estrategias do dono em cima do retangulo, medidas.

Pedido do dono (2026-09-15), depois de todo o levantamento do retangulo:

  D1 -- ENTRADA NO CENTRO. "Apos identificar uma lateralizacao, identifico o
  centro dela. Se o preco estiver descendo, posiciono uma ordem de venda no
  centro e coloco [o alvo] a 90% da media do centro ao piso; se estiver no piso
  e subindo, coloco uma ordem de compra no centro ate 90% da media de pontos do
  centro ao topo. Se estamos no W30 e sabemos que dura ao todo 61min, podemos
  replicar isso ate a barra 50 se nao romper antes. Podemos abrir neste mesmo
  padrao em W45, W60, etc."

  D2 -- FALSO ROMPIMENTO. "Ao inves do centro, usar a media do topo/fundo.
  Quando [o preco] passa a media do topo, posicionamos uma ordem de venda em X;
  quando voltar para dentro do retangulo vai acionar a ordem. Tentamos
  aproveitar 90% de toda a media do retangulo -- alvo a 10% antes do fundo -- e
  o stop fica um ponto acima de onde o preco alcancou antes de voltar."

## A RESTRICAO MECANICA, e o que ela obrigou a mudar

`CLAUDE.md`, secao "O desenho de execucao e' FECHADO": a entrada e' SEMPRE
ordem-limite parada no livro. E uma limite de VENDA so' descansa ACIMA do
preco corrente; uma de COMPRA, ABAIXO. Os dois desenhos, na forma literal,
pedem ordem-STOP (dispara a mercado quando o preco ATINGE o nivel vindo do
outro lado) -- que e' ordem a mercado disfarcada, e o motor recusa de
proposito. As versoes equivalentes em limite:

  D1: a venda no centro so' descansa se o preco JA ESTIVER ABAIXO do centro.
      Ou seja, o preco ja cruzou para baixo e a ordem pega o REPIQUE de volta
      ao centro, mirando o piso. Preserva a intencao ("vender no centro dentro
      de uma queda") e e' executavel. Simetrico para a compra.

  D2: a ordem de venda e' armada NO TOPO, ANTES do furo -- ela enche na
      propria visita ao topo. O stop "um ponto acima de onde o preco alcancou"
      e' reproduzido com `AdjustStop`: nasce largo (`stop_frac` x largura) e
      APERTA para o extremo alcancado assim que o preco fecha de volta dentro
      do retangulo. O motor aceita apertar stop, so' nao aceita afrouxar --
      entao a ideia sobrevive inteira, so' muda a ordem dos passos.

## O detector roda AO VIVO, barra a barra

Nao le o CSV pre-computado: a mesma funcao `_avalia_janela` do detector e'
chamada a cada barra sobre as ultimas W barras JA FECHADAS. Morte do retangulo
pelo mesmo criterio tolerante (3 fechamentos seguidos alem de 25% da largura).
Tudo causal.

## Convencoes (as do repo, nao negociaveis)

- Config de custo por `config_for(profile_for("WIN@"))`, alvo como ordem-limite
  real (`target_fills_as_maker=True`), ancoragem no fill.
- **1 contrato fixo**, de proposito: isola a GEOMETRIA do portao de capital.
  Dimensionamento e' a pergunta seguinte, nao esta.
- Capital R$3.000; corte de achatamento de producao (5 min).
- IS < 2026-06-13, OOS >= 2026-06-13, mais o HISTORICO COMPLETO.
- Cada W roda como BACKTEST SEPARADO. "Aproveitar todos os W ao mesmo tempo"
  (pedido do dono) nao cabe num backtest so': o motor nao piramida, entao duas
  posicoes simultaneas de W diferentes nao existem. Somar as linhas por W e' a
  aproximacao, e ela IGNORA que o caixa e a margem seriam compartilhados --
  esta' anotado na saida, nao escondido.
- WIN@ **nao tem fila calibrada** (`fidelidade.py` so' tem WDO@): toda ordem
  enche no TOQUE. Para estes dois desenhos isso e' especialmente otimista --
  os dois vivem de ordem-limite parada em nivel redondo e disputado.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_retangulo_estrategias_2026_09_15.py`
"""
from __future__ import annotations

import importlib.util
import sys
from collections import deque
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


def _carrega(nome, apelido):
    spec = importlib.util.spec_from_file_location(apelido, Path(__file__).with_name(nome))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_base = _carrega("copawin_encerrar_mais_cedo_2026_09_14.py", "_base_estr")
_det = _carrega("copawin_retangulo_lateral_2026_09_15.py", "_det_estr")

from core.instruments import economics_for  # noqa: E402
from strategy.daytrade.base import (  # noqa: E402
    AdjustStop, Bar, EnterLimit, IntradayAction, IntradayOpenPosition,
    IntradayStrategy,
)

CAPITAL = _base.CAPITAL
SYMBOL = _base.SYMBOL
FOLGA_PRODUCAO = 5
CORTE_OOS = pd.Timestamp("2026-06-13").date()
#: morte do retangulo -- o criterio TOLERANTE, o mesmo que a medicao de vida usou
MARGEM_MORTE = 0.25
BARRAS_MORTE = 3


def no_tick(preco: float, tick: float) -> float:
    return round(round(preco / tick) * tick, 10)


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


@dataclass
class RetanguloLab(IntradayStrategy):
    """Opera o retangulo. `modo='centro'` = D1; `modo='falso'` = D2."""

    name: str = "retangulo_lab"
    version: str = "0.1.0"
    symbol: str = SYMBOL
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = economics_for(SYMBOL).price_tick_size

    #: janela do detector, em barras M1
    W: int = 60
    modo: str = "centro"
    #: D1: fracao da distancia centro->borda oposta. D2: fracao da largura.
    alvo_frac: float = 0.90
    #: distancia do stop alem do nivel de entrada, em fracao da largura
    stop_frac: float = 0.25
    #: prazo da ordem-limite de entrada, em barras
    ttl_barras: int = 10
    #: para de armar entrada depois de N barras da confirmacao (None = ate morrer)
    max_barras_apos: int | None = None
    quantity: int = 1
    #: D1 apenas: so' arma se o movimento das ultimas K barras concordar com o
    #: lado da operacao (o "se o preco estiver descendo" do dono)
    direcao_filtro: bool = False
    direcao_barras: int = 10

    # -- POLITICA DE RE-ARMAR (pedido do dono, 2026-09-15: "o 'ate a barra 50'
    # nao e' fixo, mede isso tambem") ------------------------------------
    #: uma so' operacao por retangulo: batido alvo ou stop, espera uma NOVA
    #: lateralizacao para operar de novo
    uma_por_retangulo: bool = False
    #: continua armando por N barras DEPOIS de o retangulo morrer, usando os
    #: ultimos niveis conhecidos ("e se rodar 10 barras a mais? 20 a mais?")
    barras_extra_apos_morte: int = 0
    #: so' opera retangulos com largura >= isto (0 = todos). O terco superior
    #: da largura no IS comeca em 388 pontos -- corte congelado la'.
    largura_min_pontos: float = 0.0
    #: teto de VOLUME POR PONTO de largura (volume medio das W barras dividido
    #: pela largura da banda). `inf` = sem filtro. Medido no IS em W=20: os
    #: tercos comecam em 94,6 e 116,2 -- retangulo largo com volume/ponto ALTO
    #: rende -41,89 pts/op contra +35,40 do baixo. E' absorcao: muito negocio
    #: para pouco deslocamento. Correlacao de posto com a largura: so' -0,18,
    #: entao NAO e' a largura disfarcada.
    vol_por_ponto_max: float = float("inf")

    def __post_init__(self):
        self._reset_sessao()

    # -- estado -----------------------------------------------------------
    def _reset_sessao(self):
        self._hist: deque = deque(maxlen=400)
        self._ret: dict | None = None
        self._barras_desde_conf = 0
        self._espera: int | None = None
        self._fora_seguidas = 0
        self._extremo_entrada: float | None = None
        self._lado_aberto: str | None = None
        self._voltou_para_dentro = False
        self._ja_operou = False
        self._morto_ha = 0

    def on_session_start(self, session_date) -> None:
        self._reset_sessao()

    def on_order_rejected(self, ts) -> None:
        self._espera = None

    # -- deteccao ---------------------------------------------------------
    @property
    def janela_barras_detector(self) -> int:
        return int(self.W)

    def _arrays(self, n: int):
        h = list(self._hist)[-n:]
        return (np.array([b.high for b in h]), np.array([b.low for b in h]),
                np.array([b.close for b in h]))

    def _tenta_detectar(self):
        if len(self._hist) < 3 * self.W:
            return
        hi, lo, cl = self._arrays(self.W)
        hi2, lo2, _ = self._arrays(3 * self.W)
        range_antes = float(hi2[:2 * self.W].max() - lo2[:2 * self.W].min())
        ret = _det._avalia_janela(hi, lo, cl, range_antes)
        if ret is None or ret["largura"] < _det.LARGURA_MIN_TICKS * self.tick_size:
            return
        if ret["largura"] < self.largura_min_pontos:
            return
        if self.vol_por_ponto_max != float("inf"):
            janela = list(self._hist)[-self.janela_barras_detector:]
            v = sum(b.volume for b in janela) / max(1, len(janela))
            if ret["largura"] > 0 and (v / ret["largura"]) > self.vol_por_ponto_max:
                return
        self._ret = ret
        self._barras_desde_conf = 0
        self._fora_seguidas = 0
        self._ja_operou = False
        self._morto_ha = 0

    def _checa_morte(self, bar: Bar) -> bool:
        r = self._ret
        L = r["largura"]
        if bar.close > r["topo"] + MARGEM_MORTE * L or bar.close < r["piso"] - MARGEM_MORTE * L:
            self._fora_seguidas += 1
            if self._fora_seguidas >= BARRAS_MORTE:
                return True
        else:
            self._fora_seguidas = 0
        return False

    # -- entradas ---------------------------------------------------------
    def _entrada_centro(self, bar: Bar):
        r = self._ret
        meio, topo, piso, L = r["meio"], r["topo"], r["piso"], r["largura"]
        # limite de VENDA so' descansa ACIMA do preco; de COMPRA, ABAIXO.
        if bar.close < meio:
            lado, alvo_dist = "short", self.alvo_frac * (meio - piso)
            alvo, stop = meio - alvo_dist, meio + self.stop_frac * L
            sentido = -1
        elif bar.close > meio:
            lado, alvo_dist = "long", self.alvo_frac * (topo - meio)
            alvo, stop = meio + alvo_dist, meio - self.stop_frac * L
            sentido = 1
        else:
            return None
        if self.direcao_filtro:
            if len(self._hist) <= self.direcao_barras:
                return None
            var = bar.close - self._hist[-1 - self.direcao_barras].close
            # o "se o preco estiver descendo": a operacao mira o lado para onde
            # o preco ja vinha indo
            if (var < 0 and sentido > 0) or (var > 0 and sentido < 0):
                return None
        return lado, meio, alvo, stop

    def _entrada_falso(self, bar: Bar):
        r = self._ret
        meio, topo, piso, L = r["meio"], r["topo"], r["piso"], r["largura"]
        if bar.close > meio and bar.close < topo:
            # vende NO topo; a ordem descansa acima do preco
            return "short", topo, piso + (1 - self.alvo_frac) * L, topo + self.stop_frac * L
        if bar.close < meio and bar.close > piso:
            return "long", piso, topo - (1 - self.alvo_frac) * L, piso - self.stop_frac * L
        return None

    # -- loop -------------------------------------------------------------
    def on_bar(self, ts, bar: Bar, positions: list[IntradayOpenPosition],
               session_pnl_brl: float) -> list[IntradayAction]:
        self._hist.append(bar)

        if self._ret is not None:
            self._barras_desde_conf += 1
            if self._morto_ha > 0:
                # ja morreu; vive de sobrevida por `barras_extra_apos_morte`
                self._morto_ha += 1
                if self._morto_ha > self.barras_extra_apos_morte:
                    self._ret = None
                    self._espera = None
                    self._morto_ha = 0
            elif self._checa_morte(bar):
                if self.barras_extra_apos_morte > 0:
                    self._morto_ha = 1
                else:
                    self._ret = None
                    self._espera = None
        if self._ret is None:
            self._tenta_detectar()
            if self._ret is None:
                return []

        r = self._ret

        # -- posicao aberta: so' o aperto de stop do D2 ---------------------
        if positions:
            self._espera = None
            self._ja_operou = True
            if self.modo != "falso" or self._lado_aberto is None:
                return []
            pos = positions[0]
            if self._lado_aberto == "short":
                self._extremo_entrada = max(self._extremo_entrada or bar.high, bar.high)
                if bar.close < r["topo"]:      # voltou para DENTRO do retangulo
                    novo = no_tick(self._extremo_entrada + self.tick_size, self.tick_size)
                    if pos.current_stop is not None and novo < pos.current_stop:
                        return [AdjustStop(new_stop=novo)]
            else:
                self._extremo_entrada = min(self._extremo_entrada or bar.low, bar.low)
                if bar.close > r["piso"]:
                    novo = no_tick(self._extremo_entrada - self.tick_size, self.tick_size)
                    if pos.current_stop is not None and novo > pos.current_stop:
                        return [AdjustStop(new_stop=novo)]
            return []

        self._lado_aberto = None
        self._extremo_entrada = None

        # -- ordem pendente ainda viva --------------------------------------
        if self._espera is not None:
            self._espera += 1
            if self._espera < self.ttl_barras:
                return []
            self._espera = None

        if self.max_barras_apos is not None and self._barras_desde_conf > self.max_barras_apos:
            return []
        if self.uma_por_retangulo and self._ja_operou:
            return []

        alvo_entrada = (self._entrada_centro(bar) if self.modo == "centro"
                        else self._entrada_falso(bar))
        if alvo_entrada is None:
            return []
        lado, limite, alvo, stop = alvo_entrada

        # conferencia mecanica: a limite tem de descansar do lado certo
        if lado == "short" and limite <= bar.close:
            return []
        if lado == "long" and limite >= bar.close:
            return []

        self._espera = 0
        self._lado_aberto = lado
        self._extremo_entrada = None
        return [EnterLimit(
            side=lado,
            limit_price=no_tick(limite, self.tick_size),
            initial_stop=no_tick(stop, self.tick_size),
            initial_target=no_tick(alvo, self.tick_size),
            quantity=self.quantity,
            ttl_bars=self.ttl_barras,
            reason=f"{self.modo}_W{self.W}",
        )]


# ---------------------------------------------------------------------------

def _roda(dias, **kw):
    from backtest.intraday.engine import run_intraday_backtest

    strat = RetanguloLab(**kw)
    df, _ = _base._df()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    cfg, _corte = _base._cfg_com_folga(FOLGA_PRODUCAO, CAPITAL, strat)
    return run_intraday_backtest(bars, strat, cfg)


def _unidade(args):
    janela_nome, dias, rotulo, kw = args
    buf = StringIO()
    with redirect_stdout(buf):
        res = _roda(dias, **kw)
    c = _base.consistencia(list(res.trades), dias)
    return dict(janela=janela_nome, rotulo=rotulo, res=res, c=c)


def main():
    df, dias = _base._df()
    janelas = {
        "IS (<2026-06-13)": [d for d in dias if d < CORTE_OOS],
        "OOS (>=2026-06-13)": [d for d in dias if d >= CORTE_OOS],
        "HISTORICO COMPLETO": dias,
    }

    variantes = []
    for modo in ("centro", "falso"):
        for W in (30, 60, 120):
            for stop_frac in (0.25, 0.50):
                variantes.append((f"{modo} W{W} stop{stop_frac:.2f}",
                                  dict(modo=modo, W=W, stop_frac=stop_frac)))
    # o filtro de direcao que o dono descreveu, so' no D1 e num ponto da grade
    for W in (30, 60, 120):
        variantes.append((f"centro W{W} stop0.25 +direcao",
                          dict(modo="centro", W=W, stop_frac=0.25, direcao_filtro=True)))

    print("=" * 112)
    print("WIN@ -- AS DUAS ESTRATEGIAS DO DONO SOBRE O RETANGULO (D1 centro, D2 falso rompimento)")
    print("=" * 112)
    print(f"{len(dias)} pregoes | capital R$ {br(CAPITAL,0)} | 1 CONTRATO FIXO (isola geometria "
          f"do portao de capital)")
    print(f"alvo = 90% (centro->borda no D1; da largura no D2) | prazo da ordem 10 barras | "
          f"{len(variantes)} variantes x {len(janelas)} janelas")
    print("RESSALVA: WIN@ sem fila calibrada -- toda limite enche no TOQUE. Otimista para dois")
    print("desenhos que vivem de ordem parada em nivel disputado.\n", flush=True)

    tarefas = [(jn, dj, rot, kw) for jn, dj in janelas.items() for rot, kw in variantes]
    out: dict = {}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            out.setdefault(r["janela"], {})[r["rotulo"]] = r
            c = r["c"]
            print(f"  {r['janela']:<22}{r['rotulo']:<32} liquido={br(c['liquido']).rjust(11)}"
                  f"  trades={c['n']:>5}  win={br(100*c['win'],1) if c['n'] else '--':>5}%"
                  f"  sem_trade={c['sem_trade']:>3}d", flush=True)

    from backtest.intraday.report import linha_de_resultado, tabela
    EXTRAS = ("preg+", "bl20+", "seq-", "BEemp%", "veredito", "sem_tr")
    for jn, dj in janelas.items():
        print(f"\n\n===== WIN@, R$ {br(CAPITAL,0)}, 1 contrato -- {jn} ({len(dj)} pregoes) =====")
        linhas = []
        for rot, _kw in variantes:
            r = out[jn][rot]
            c = r["c"]
            extras = {
                "preg+": (br(100 * c["frac_preg"], 0) + "%") if c["frac_preg"] == c["frac_preg"] else "--",
                "bl20+": (br(100 * c["frac_bl"], 0) + "%") if c["frac_bl"] == c["frac_bl"] else "--",
                "seq-": str(c["seq_neg"]),
                "BEemp%": (br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
                "veredito": c["veredito"],
                "sem_tr": f"{c['sem_trade']}/{c['pregoes']}",
            }
            linhas.append(linha_de_resultado(rot, r["res"], CAPITAL, extras=extras))
        print(tabela(linhas, extras=EXTRAS))

    print("\n\n" + "=" * 112)
    print("VEREDITO -- positivo no IS E no OOS?")
    print("=" * 112)
    hdr = (f"  {'variante':<32}{'IS liq':>12}{'IS n':>7}{'IS win':>8}"
           f"{'OOS liq':>12}{'OOS n':>7}{'OOS win':>8}{'':>4}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    passou = []
    for rot, _kw in variantes:
        ci = out["IS (<2026-06-13)"][rot]["c"]
        co = out["OOS (>=2026-06-13)"][rot]["c"]
        ok = ci["liquido"] > 0 and co["liquido"] > 0 and ci["n"] >= 30 and co["n"] >= 15
        if ok:
            passou.append(rot)
        print(f"  {rot:<32}{br(ci['liquido']):>12}{ci['n']:>7}"
              f"{(br(100*ci['win'],1) if ci['n'] else '--'):>8}"
              f"{br(co['liquido']):>12}{co['n']:>7}"
              f"{(br(100*co['win'],1) if co['n'] else '--'):>8}{('  <<<' if ok else ''):>4}")
    print()
    if passou:
        print(f"  {len(passou)} de {len(variantes)} variantes positivas nas DUAS janelas: {passou}")
        print("  A 5%, 15 celulas produzem ~0,75 positivo falso -- uma celula isolada num canto")
        print("  da grade ainda e' suspeita; vizinhas acompanhando e' o que separa sinal de ruido.")
    else:
        print(f"  NENHUMA das {len(variantes)} variantes e' positiva nas duas janelas.")
    print("\n  'Aproveitar todos os W ao mesmo tempo' nao esta medido aqui: o motor nao piramida,")
    print("  entao cada W e' um backtest separado. Somar as linhas ignora caixa e margem")
    print("  compartilhados -- e' teto, nao previsao.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
