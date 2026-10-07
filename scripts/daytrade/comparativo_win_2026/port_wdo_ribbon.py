"""Port do EA mt5/WdoRibbonMm34.mq5 (v1.77) para replay tick a tick no WIN$N (comparativo WIN 2026).

Duas versoes (ver `VERSOES`):
  - WdoRibbonMm34      inputs padrao do EA (tick 0,5, RangeMax 65, ...), exatamente como o Testador rodaria no WIN.
  - WdoRibbonMm34_win  so' ESCALA: TickSizeWdo=5 e RangeMaxAntesEntrada = 65 x razao(amplitude diaria WIN/WDO).

Como o Testador executa o EA (e como este port reproduz):
  - O EA so' age no PRIMEIRO tick de cada barra M1 (IsNewBar). Nesse tick processa a barra FECHADA anterior
    (CopyRates(1,1)); a ordem a mercado executa no `last` desse tick (bid = ask = last).
  - SL/TP anexados na posicao: SL dispara quando o last toca/atravessa e sai no last do tick; TP e' limite, sai no
    preco do TP. Checados em todos os ticks entre os eventos de barra (vetorizado com numpy, sem loop por tick).
  - Zeragem: no primeiro tick de barra com hora >= 18:20 (TimeCurrent), fecha a mercado no last.
  - Servidor: SL/TP fora da grade de preco do ativo (WIN: multiplos de 5) sao recusados (invalid stops/price).
    `NormalizeDouble(x, _Digits)` do WIN (0 casas) arredonda o stop para inteiro ANTES de ir ao servidor.
    Apos a recusa o EA nao faz mais nada: o contador de ondas ja' foi incrementado e o lado ja' ficou travado
    (a entrada simplesmente se perde). Trailing recusado: o stop antigo permanece.
    Tambem recusadas: SL do lado errado do preco / TP do lado errado (mercado andou entre sinal e ordem).
  - O primeiro evento de barra de cada dia processa a ultima barra do dia ANTERIOR (CopyRates(1,1) no 1o tick);
    reproduzido de proposito.

Modo `legado` (so' validacao): reproduz a logica v1.63 da classe Python `WdoRibbonMm34` (MMs continuas, vela so'
pelo corpo, alvo = 25x largura do ribbon) para provar contra a replica antiga do WDO que o motor do port preserva
a logica. Nao e' usado na rodada do WIN.

Uso:
  python port_wdo_ribbon.py --escala      # mede a razao WIN/WDO e imprime a conta
  python port_wdo_ribbon.py --validar     # port x replica antiga no WDO
  python port_wdo_ribbon.py --rodar       # 2026-01-02 -> 2026-10-05, gera resultados/*.csv
"""
from __future__ import annotations

import argparse
import math
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
ROOT = AQUI.parents[2]
sys.path.insert(0, str(AQUI))
import dados  # noqa: E402

LONG, SHORT, NENHUM = 1, -1, 0
TENDENCIA, CONTRARIA = 1, 2
VELOCIDADE = (1, 2, 0, 3)  # SMA, EMA, SMMA, LWMA


@dataclass(frozen=True)
class Cfg:
    periodo: int = 34
    stop_alem: float = 0.0
    max_ondas: int = 3
    range_max: float = 65.0
    tick: float = 0.5          # TickSizeWdo (arredondamento do EA)
    digits: int = 0            # _Digits do simbolo (WIN = 0)
    hora_zerar: int = 18
    min_zerar: int = 20
    tick_servidor: float = 5.0  # grade de preco que o servidor aceita em SL/TP (WIN = 5)
    legado: bool = False        # v1.63 (so' validacao)
    mult_alvo_legado: float = 25.0


def norm(x: float, d: int) -> float:
    """NormalizeDouble do MQL5: arredonda meio para longe do zero."""
    f = 10.0 ** d
    return math.copysign(math.floor(abs(x) * f + 0.5) / f, x)


def na_grade(x: float, g: float) -> bool:
    q = x / g
    return abs(q - round(q)) < 1e-6


class Ribbon:
    """Maquina de estados de ProcessarBarraFechada()."""

    def __init__(self, cfg: Cfg):
        self.c = cfg
        self.dia_atual = None
        self.reset_regime()
        self.travado = {LONG: False, SHORT: False}
        self.ref = None
        self.sempre_apontando = True
        self.entradas_hoje = 0
        self.dia_high = self.dia_low = 0.0
        self.dia_tem_range = False
        self._zera_medias()
        self.largura = 0.0

    # --- MMs so' do pregao (v1.77) -------------------------------------------------
    def _zera_medias(self):
        self.fech, self.sma, self.ema, self.smma, self.lwma = [], [], [], [], []

    def _atualiza_medias(self, fechamento: float):
        P = self.c.periodo
        n = len(self.fech)
        self.fech.append(fechamento)
        for a in (self.sma, self.ema, self.smma, self.lwma):
            a.append(None)
        if n < P - 1:
            return
        soma = soma_p = soma_w = 0.0
        for w in range(1, P + 1):
            cc = self.fech[n - P + w]
            soma += cc
            soma_p += cc * w
            soma_w += w
        self.sma[n] = soma / P
        self.lwma[n] = soma_p / soma_w
        if n == P - 1:
            self.ema[n] = self.sma[n]
            self.smma[n] = self.sma[n]
        else:
            k = 2.0 / (P + 1)
            self.ema[n] = fechamento * k + self.ema[n - 1] * (1.0 - k)
            self.smma[n] = (self.smma[n - 1] * (P - 1) + fechamento) / P

    # --- helpers -------------------------------------------------------------------
    def reset_regime(self):
        self.lado = NENHUM
        self.fase = 0

    def no_tick(self, x):
        c = self.c
        return norm(math.floor(x / c.tick + 0.5) * c.tick, c.digits)

    def stop_compra(self, mm):
        c = self.c
        return norm(math.floor((mm - c.stop_alem) / c.tick + 1e-9) * c.tick, c.digits)

    def stop_venda(self, mm):
        c = self.c
        return norm(math.ceil((mm + c.stop_alem) / c.tick - 1e-9) * c.tick, c.digits)

    @staticmethod
    def apontam(lado, atual, antes):
        if antes is None:
            return False
        if lado == LONG:
            return all(a > b for a, b in zip(atual, antes))
        return all(a < b for a, b in zip(atual, antes))

    @staticmethod
    def cruzou_contra(lado, ref, atual):
        for i in range(4):
            for j in range(4):
                if VELOCIDADE[i] <= VELOCIDADE[j]:
                    continue
                if lado == LONG and ref[i] > ref[j] and atual[i] < atual[j]:
                    return True
                if lado == SHORT and ref[i] < ref[j] and atual[i] > atual[j]:
                    return True
        return False

    def novo_dia_legado(self):
        self.reset_regime()
        self.travado = {LONG: False, SHORT: False}
        self.entradas_hoje = 0
        self.dia_tem_range = False

    # --- ProcessarBarraFechada -------------------------------------------------------
    def processa(self, ts, o, h, l, cl, pos, mm=None):
        """pos = None | (lado, stop_atual). Devolve None | ('trail', candidato) |
        ('enter', lado, stop, alvo, fechamento). Em modo legado `mm` = (valores, anteriores)."""
        c = self.c
        if not c.legado:
            dia = ts.date()
            if dia != self.dia_atual:
                self.dia_atual = dia
                self.novo_dia_legado()
                self._zera_medias()
            if not self.dia_tem_range:
                self.dia_high, self.dia_low, self.dia_tem_range = h, l, True
            else:
                self.dia_high, self.dia_low = max(self.dia_high, h), min(self.dia_low, l)
            self._atualiza_medias(cl)
            n = len(self.fech)
            if n < c.periodo + 1:
                return None
            valores = (self.sma[n - 1], self.ema[n - 1], self.smma[n - 1], self.lwma[n - 1])
            anteriores = (self.sma[n - 2], self.ema[n - 2], self.smma[n - 2], self.lwma[n - 2])
        else:
            if mm is None:
                return None
            valores, anteriores = mm
            if not self.dia_tem_range:
                self.dia_high, self.dia_low, self.dia_tem_range = h, l, True
            else:
                self.dia_high, self.dia_low = max(self.dia_high, h), min(self.dia_low, l)
        rmax, rmin = max(valores), min(valores)

        if cl <= rmax:
            self.travado[LONG] = False
        if cl >= rmin:
            self.travado[SHORT] = False

        if pos is not None:
            lado_p, stop_atual = pos
            if lado_p == LONG:
                cand = self.stop_compra(rmax)
                aperta = cand > stop_atual
            else:
                cand = self.stop_venda(rmin)
                aperta = cand < stop_atual
            return ('trail', cand) if aperta else None

        verde, vermelha = cl > o, cl < o
        if c.legado:
            baixo, alto = min(o, cl), max(o, cl)   # so' o corpo
        else:
            baixo, alto = l, h                      # vela inteira (corpo + pavio)
        if baixo > rmax:
            lado, a_favor, contra, ref = LONG, verde, vermelha, rmax
        elif alto < rmin:
            lado, a_favor, contra, ref = SHORT, vermelha, verde, rmin
        else:
            self.reset_regime()
            return None

        if self.lado != lado or (self.lado != NENHUM and self.cruzou_contra(lado, self.ref, valores)):
            self.reset_regime()

        def queima():
            self.reset_regime()
            self.travado[lado] = True

        if self.fase == 0:
            if a_favor and not self.travado[lado]:
                self.lado, self.fase, self.ref = lado, TENDENCIA, valores
                self.sempre_apontando = self.apontam(lado, valores, anteriores)
            return None
        self.sempre_apontando = self.sempre_apontando and self.apontam(lado, valores, anteriores)
        if self.fase == TENDENCIA:
            if contra:
                self.fase = CONTRARIA
            return None
        if contra:
            queima()
            return None
        if not a_favor:
            return None
        if not self.sempre_apontando:
            queima()
            return None
        if c.max_ondas > 0 and self.entradas_hoje >= c.max_ondas:
            queima()
            return None
        if c.range_max > 0.0 and (self.dia_high - self.dia_low) >= c.range_max:
            queima()
            return None

        self.reset_regime()
        self.entradas_hoje += 1
        stop = self.stop_compra(ref) if lado == LONG else self.stop_venda(ref)
        if c.legado:
            self.largura = rmax - rmin
            alvo = None
        else:
            dist = abs(cl - o)
            alvo = self.no_tick(cl + dist) if lado == LONG else self.no_tick(cl - dist)
        self.travado[lado] = True
        return ('enter', lado, stop, alvo, cl)


# ------------------------------------------------------------------------------------
# Execucao tick a tick (Testador, WIN)
# ------------------------------------------------------------------------------------
def ordem_valida(lado, preco, sl, tp, g):
    if not (na_grade(sl, g) and na_grade(tp, g)):
        return False
    if lado == LONG:
        return sl < preco < tp
    return tp < preco < sl


def simular(nome: str, cfg: Cfg, dias_: list, log=print):
    m = dados.m1()
    idx_min = m.index.values.astype("datetime64[m]").astype(np.int64)  # minutos epoch
    O, H, L, C = (m[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    tss = m.index
    eng = Ribbon(cfg)
    zerar_min = cfg.hora_zerar * 60 + cfg.min_zerar
    trades = []
    pos = None  # dict(lado, pe, sl, tp, t_ent)
    ultimo_min = None
    rej = dict(enter=0, trail=0, entradas=0)

    for dia in dias_:
        t, p, _v, _r = dados.ticks(dia)
        if len(t) == 0:
            continue
        minuto = t // 60000
        ev = np.flatnonzero(np.r_[True, minuto[1:] != minuto[:-1]])
        if ultimo_min is not None and minuto[0] == ultimo_min:
            ev = ev[1:]
        chk = 0
        for i in ev:
            # 1) SL/TP nos ticks (chk..i] (o tick i ja' conta: o Testador checa antes de chamar OnTick)
            if pos is not None:
                seg = p[chk:i + 1]
                if pos['lado'] == LONG:
                    hit = (seg <= pos['sl']) | (seg >= pos['tp'])
                else:
                    hit = (seg >= pos['sl']) | (seg <= pos['tp'])
                if hit.any():
                    j = chk + int(hit.argmax())
                    px_ = p[j]
                    if (pos['lado'] == LONG and px_ >= pos['tp']) or (pos['lado'] == SHORT and px_ <= pos['tp']):
                        px_, mot = pos['tp'], 'alvo'
                    else:
                        mot = 'stop'
                    trades.append(dados.trade(nome, pos['t_ent'], t[j], pos['lado'], 1, pos['pe'], px_, mot))
                    pos = None
            chk = i + 1
            # 2) OnTick: so' em barra nova
            hh_mm = int(t[i] // 60000 % 1440)
            if hh_mm >= zerar_min:
                if pos is not None:
                    trades.append(dados.trade(nome, pos['t_ent'], t[i], pos['lado'], 1, pos['pe'], p[i], '18:20'))
                    pos = None
                eng.reset_regime()
                continue
            k = int(np.searchsorted(idx_min, minuto[i])) - 1  # barra fechada = anterior a' do tick
            if k < 0:
                continue
            acao = eng.processa(tss[k], O[k], H[k], L[k], C[k], None if pos is None else (pos['lado'], pos['sl']))
            if acao is None:
                continue
            if acao[0] == 'trail':
                cand = acao[1]
                ok = (na_grade(cand, cfg.tick_servidor) and
                      ((pos['lado'] == LONG and cand < p[i]) or (pos['lado'] == SHORT and cand > p[i])))
                if ok:
                    pos['sl'] = cand
                else:
                    rej['trail'] += 1
            else:
                _, lado, stop, alvo, _cl = acao
                rej['entradas'] += 1
                if ordem_valida(lado, p[i], stop, alvo, cfg.tick_servidor):
                    pos = dict(lado=lado, pe=float(p[i]), sl=stop, tp=alvo, t_ent=t[i])
                else:
                    rej['enter'] += 1
        # ticks apos o ultimo evento do dia
        if pos is not None and chk < len(p):
            seg = p[chk:]
            hit = ((seg <= pos['sl']) | (seg >= pos['tp'])) if pos['lado'] == LONG else ((seg >= pos['sl']) | (seg <= pos['tp']))
            if hit.any():
                j = chk + int(hit.argmax())
                px_ = p[j]
                if (pos['lado'] == LONG and px_ >= pos['tp']) or (pos['lado'] == SHORT and px_ <= pos['tp']):
                    px_, mot = pos['tp'], 'alvo'
                else:
                    mot = 'stop'
                trades.append(dados.trade(nome, pos['t_ent'], t[j], pos['lado'], 1, pos['pe'], px_, mot))
                pos = None
        ultimo_min = minuto[-1]
    if pos is not None:  # fim do teste com posicao aberta: o Testador fecha no ultimo preco
        trades.append(dados.trade(nome, pos['t_ent'], t[-1], pos['lado'], 1, pos['pe'], p[-1], 'fim_teste'))
    log(f"{nome}: entradas sinalizadas={rej['entradas']} recusadas pelo servidor={rej['enter']} "
        f"trailing recusado={rej['trail']} trades={len(trades)}")
    return trades


# ------------------------------------------------------------------------------------
# Escala WIN/WDO
# ------------------------------------------------------------------------------------
def medir_escala():
    wdo = pd.read_csv(ROOT / "data" / "wdo-mt5" / "WDO@D_M1_202109290900_202609291020.csv", sep="\t")
    wdo["d"] = pd.to_datetime(wdo["<DATE>"], format="%Y.%m.%d").dt.date
    aw = wdo.groupby("d").apply(lambda g: g["<HIGH>"].max() - g["<LOW>"].min())
    m = dados.m1()
    ai = m.groupby(m.index.date).apply(lambda g: g["high"].max() - g["low"].min())
    ini = date(2026, 1, 2)
    comum = sorted(d for d in set(aw.index) & set(ai.index) if ini <= d <= date(2026, 9, 29))
    mw, mi = float(np.median(aw[comum])), float(np.median(ai[comum]))
    return len(comum), mw, mi, mi / mw


def rs(x: float, g: float = 5.0) -> float:
    return round(x / g) * g


def cfg_versoes():
    base = Cfg()
    n, mw, mi, r = medir_escala()
    rng = rs(65.0 * r)
    return {
        "WdoRibbonMm34": base,
        "WdoRibbonMm34_win": replace(base, tick=5.0, range_max=rng),
    }, (n, mw, mi, r, rng)


def _rodar(nome, cfg):
    dd = [d for d in dados.dias() if d >= date(2026, 1, 2)]
    tr = simular(nome, cfg, dd, log=lambda s: print(s, flush=True))
    return nome, tr


def rodar():
    vers, (n, mw, mi, r, rng) = cfg_versoes()
    print(f"escala: {n} pregoes comuns, mediana amplitude WDO={mw:.1f} WIN={mi:.0f} razao={r:.2f} -> RangeMax win={rng:.0f}", flush=True)
    with ProcessPoolExecutor(max_workers=2) as pool:
        fs = [pool.submit(_rodar, nome, cfg) for nome, cfg in vers.items()]
        for f in as_completed(fs):
            nome, tr = f.result()
            dados.salvar(nome, tr)
            df = pd.DataFrame(tr)
            print(f"== {nome}: {len(tr)} trades", flush=True)
            if len(tr):
                df["mes"] = df.saida.str[:7]
                print(df.groupby("mes").rs.agg(["count", "sum"]).round(2).to_string(), flush=True)
                print(f"liquido total R$ {df.rs.sum():.2f}", flush=True)


# ------------------------------------------------------------------------------------
# Validacao no WDO: port (modo legado) x replica antiga
# ------------------------------------------------------------------------------------
def validar(ini="2026-09-01", fim="2026-09-28"):
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))
    import wdo_ribbon_mm34_replica_tester_2026_09_29 as rep
    from datetime import datetime
    from core.indicators import ema, lwma, sma, smma
    from strategy.daytrade.base import AdjustStop, Enter

    class Adaptador:
        def __init__(self):
            self.eng = Ribbon(Cfg(legado=True, digits=3, tick=0.5, range_max=65.0))
            self.mm = {}

        def initialize(self, bars):
            cl = bars["close"]
            md = pd.concat([sma(cl, 34), ema(cl, 34), smma(cl, 34), lwma(cl, 34)], axis=1)
            ant = md.shift(1)
            ok = md.notna().all(axis=1)
            oka = ant.notna().all(axis=1)
            for ts_, row, ra, a, b in zip(md.index, md.to_numpy(), ant.to_numpy(), ok, oka):
                if a:
                    self.mm[ts_] = (tuple(row), tuple(ra) if b else None)

        def on_session_start(self, d):
            self.eng.novo_dia_legado()

        def alvo_para(self, lado, entrada, stop):
            dist = 25.0 * self.eng.largura
            if dist < 0.5:
                return None
            s = 1 if lado == "long" else -1
            return norm(math.floor((entrada + s * dist) / 0.5 + 0.5) * 0.5, 3)

        def on_bar(self, ts, bar, positions, pnl):
            pos = None
            if positions:
                p0 = positions[0]
                pos = (LONG if p0.side == "long" else SHORT, p0.current_stop)
            a = self.eng.processa(ts, bar.open, bar.high, bar.low, bar.close, pos, self.mm.get(ts))
            if a is None:
                return []
            if a[0] == 'trail':
                return [AdjustStop(new_stop=a[1])]
            lado = "long" if a[1] == LONG else "short"
            alvo = self.alvo_para(lado, a[4], a[2])
            if alvo is None:
                return []
            return [Enter(side=lado, initial_stop=a[2], initial_target=alvo, quantity=1, reason="x")]

    i_, f_ = datetime.strptime(ini, "%Y-%m-%d"), datetime.strptime(fim, "%Y-%m-%d")
    df = rep.carregar_m1(i_, f_)
    antiga = rep.simular(df, i_)
    novo = rep.simular(df, i_, estrategia=Adaptador())
    print(f"periodo {ini} -> {fim}: replica antiga {len(antiga)} trades, {antiga.pontos.sum():+.1f} pts; "
          f"port {len(novo)} trades, {novo.pontos.sum():+.1f} pts", flush=True)
    cols = ["entrada", "lado", "preco", "stop_inicial", "alvo", "saida", "preco_saida", "motivo", "pontos"]
    n = min(len(antiga), len(novo))
    iguais = int(sum(antiga[cols].iloc[k].tolist() == novo[cols].iloc[k].tolist() for k in range(n)))
    print(f"trades identicos (todas as colunas): {iguais} de {max(len(antiga), len(novo))}", flush=True)
    return iguais, len(antiga), len(novo)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--escala", action="store_true")
    ap.add_argument("--validar", action="store_true")
    ap.add_argument("--ini", default="2026-09-01")
    ap.add_argument("--fim", default="2026-09-28")
    ap.add_argument("--rodar", action="store_true")
    a = ap.parse_args()
    if a.escala:
        n, mw, mi, r = medir_escala()
        print(f"{n} pregoes comuns 2026; mediana amplitude diaria WDO={mw:.1f} pts, WIN={mi:.0f} pts; razao={r:.2f}; "
              f"RangeMax win = 65 x {r:.2f} = {65 * r:.0f} -> {rs(65 * r):.0f}", flush=True)
    if a.validar:
        validar(a.ini, a.fim)
    if a.rodar:
        rodar()
