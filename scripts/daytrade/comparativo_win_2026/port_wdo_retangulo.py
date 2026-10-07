"""Porte de mt5/WdoRetangulo.mq5 (v1.01) para replay tick a tick no WIN, estilo Testador.

Duas versoes, mesmos inputs que o dono roda no Testador (Janela 25, Tol 0,28, alvo 4,5xL, stop 4,5xL, ttl 10, zera 18:20):
  WdoRetangulo       -> TickSizeWdo = 0,5 (ordens fora da grade de 5 pontos sao RECUSADAS pelo servidor)
  WdoRetangulo_tick5 -> TickSizeWdo = 5   (tudo na grade)

O que o EA faz e este port reproduz (lido no .mq5 e conferido no log do Testador de 2026-10-05):
 - decisao so' na 1a tick de cada barra M1 nova (IsNewBar), sobre a ULTIMA barra FECHADA (CopyRates shift 1);
   inclui a virada de pregao: a 1a decisao do dia usa a ultima barra do dia anterior (que ainda e' "o mesmo dia"
   para o EA) -- so' a 2a decisao zera o historico (ResetSessao);
 - NoTick(p) = NormalizeDouble(round(p/tick)*tick, _Digits=0): com tick 0,5 o x,5 sobe para o inteiro e quase nunca
   cai na grade de 5 -> BuyLimit/SellLimit recusados (retcode 10015) e o EA tenta de novo a cada barra (nada fica armado);
 - preenchimento da limite -> stop nativo (PositionModify) e alvo (limite oposta) com os precos ancorados; cada um
   e' recusado separadamente se fora da grade (10016 / 10015); sem stop e sem alvo a posicao segue ate' 18:20;
 - stop executa no `last` do tick que o cruza; limite executa no preco da limite; zeragem a mercado na 1a tick >= 18:20;
 - ordens colocadas na tick i so' casam a partir da tick i+1; posicao preenchida na tick k ganha stop/alvo ja' na
   mesma OnTick, validos a partir da tick k+1.
Nao reproduzido: LimiteEquity (so' aproximado pelo PnL fechado), StopsLevel da corretora, fila/liquidez.

Uso: python port_wdo_retangulo.py valida | final
"""
from __future__ import annotations
import math, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dados

TOQUES_MIN, VISITAS_MIN, CRUZ_MIN = 2, 2, 3
CONTENCAO_MIN, CONTRACAO_MAX, ESPALH_MIN, DERIVA_MAX = 0.95, 0.55, 1.0 / 3.0, 0.25
MARGEM_MORTE, BARRAS_MORTE, LARGURA_MIN_TICKS = 0.25, 3, 4.4
GRADE = 5.0  # tick real do WIN
REF = Path(__file__).resolve().parent / "ref_testador_WdoRetangulo_WINV26_2026_08_12_a_10_01.csv"


@dataclass(frozen=True)
class Cfg:
    janela: int = 25
    tol: float = 0.28
    alvo_frac: float = 4.5
    stop_frac: float = 4.5
    ttl: int = 10
    larg_min_pts: float = 0.0
    tick: float = 0.5
    hora_zerar: int = 18
    min_zerar: int = 20


def _visitas(pos):
    return 1 + int(np.sum(np.diff(pos) > 1)) if len(pos) else 0


def detecta(h, l, c, tol, amp_ant):
    n = len(c)
    topo = float(np.quantile(h, 0.90)); piso = float(np.quantile(l, 0.10))
    larg = topo - piso
    if larg <= 0:
        return None
    meio = (topo + piso) / 2; zona = tol * larg
    tm = h >= topo - zona; pm = (~tm) & (l <= piso + zona)
    pt = np.flatnonzero(tm); pp = np.flatnonzero(pm)
    if len(pt) < TOQUES_MIN or len(pp) < TOQUES_MIN:
        return None
    if _visitas(pt) < VISITAS_MIN or _visitas(pp) < VISITAS_MIN:
        return None
    m = ESPALH_MIN * n
    if pt[-1] - pt[0] < m or pp[-1] - pp[0] < m:
        return None
    lados = np.where(tm, 1, np.where(pm, -1, 0)); lados = lados[lados != 0]
    if int(np.sum(lados[1:] != lados[:-1])) < 2:
        return None
    ac = c > meio
    if int(np.sum(ac[1:] != ac[:-1])) < CRUZ_MIN:
        return None
    if np.mean((c >= piso) & (c <= topo)) < CONTENCAO_MIN:
        return None
    t3 = n // 3
    if abs(c[n - t3:].mean() - c[:t3].mean()) > DERIVA_MAX * larg:
        return None
    if amp_ant > 0 and larg / amp_ant > CONTRACAO_MAX:
        return None
    return topo, piso, larg, meio


def no_tick(p, tick):
    x = math.floor(p / tick + 0.5) * tick           # MathRound
    return float(math.floor(x + 0.5))                # NormalizeDouble(.., 0): o x,5 sobe para o inteiro


def na_grade(p):
    return abs(p / GRADE - round(p / GRADE)) < 1e-9


class EA:
    def __init__(self, cfg: Cfg, nome: str, prev_bar):
        self.c, self.nome = cfg, nome
        self.prev_bar = prev_bar           # (t_ms, high, low, close) da ultima barra fechada
        self.g_dia = None
        self.H, self.L, self.C = [], [], []
        self.tem = False; self.topo = self.piso = self.larg = self.meio = 0.0; self.fora = 0
        self.pend = None; self.esp = 0     # limite de entrada parada: dict(lado, lim, stop, alvo)
        self.pos = None                    # dict(lado, ent, t_ent, stop, alvo)
        self.trades = []; self.pnl = 0.0; self.parou = False
        self.falhas = dict(entrada=0, stop=0, alvo=0, armadas=0)

    # ---- ordens / execucao -------------------------------------------------
    def _fecha(self, t_ms, px, motivo):
        p = self.pos
        tr = dados.trade(self.nome, p["t_ent"], t_ms, p["lado"], 1, p["ent"], px, motivo)
        self.trades.append(tr); self.pnl += tr["rs"]; self.pos = None
        if dados.CAPITAL + self.pnl <= 0:     # LimiteEquity=0: TesterStop
            self.parou = True

    def _cancela_pend(self):
        self.pend = None; self.esp = 0

    def avanca(self, t, p, a, b):
        """Casa ordens/stop nas ticks [a, b). Chamada com o estado vigente no inicio de a."""
        while a < b and (self.pend is not None or self.pos is not None) and not self.parou:
            if self.pos is None:
                pd_ = self.pend; seg = p[a:b]
                hit = seg >= pd_["lim"] if pd_["lado"] == -1 else seg <= pd_["lim"]
                if not hit.any():
                    return
                k = a + int(hit.argmax())
                self.pos = dict(lado=pd_["lado"], ent=pd_["lim"], t_ent=int(t[k]), stop=None, alvo=None)
                self.pend = None; self.esp = 0
                # OnTick(k): ancora stop e alvo (delta = 0: a limite preenche no proprio preco)
                lado, px = self.pos["lado"], float(p[k])
                st = no_tick(pd_["stop"], self.c.tick); al = no_tick(pd_["alvo"], self.c.tick)
                if na_grade(st) and ((lado == 1 and st < px) or (lado == -1 and st > px)):
                    self.pos["stop"] = st
                else:
                    self.falhas["stop"] += 1
                if na_grade(al) and ((lado == 1 and al > px) or (lado == -1 and al < px)):
                    self.pos["alvo"] = al
                else:
                    self.falhas["alvo"] += 1
                a = k + 1
                continue
            ps = self.pos; seg = p[a:b]; lado = ps["lado"]
            n = len(seg); ks = ka = n
            if ps["stop"] is not None:
                m = seg <= ps["stop"] if lado == 1 else seg >= ps["stop"]
                if m.any():
                    ks = int(m.argmax())
            if ps["alvo"] is not None:
                m = seg >= ps["alvo"] if lado == 1 else seg <= ps["alvo"]
                if m.any():
                    ka = int(m.argmax())
            if ks == n and ka == n:
                return
            if ks <= ka:
                self._fecha(int(t[a + ks]), float(seg[ks]), "stop"); a = a + ks + 1
            else:
                self._fecha(int(t[a + ka]), ps["alvo"], "alvo"); a = a + ka + 1

    # ---- OnTick na tick de barra nova --------------------------------------
    def zerar(self, t, p, a):
        self._cancela_pend()
        if self.pos is not None:
            self._fecha(int(t[a]), float(p[a]), "zeragem")
        self.tem = False

    def _reset_sessao(self):
        self.H, self.L, self.C = [], [], []
        self.tem = False; self.fora = 0; self._cancela_pend()

    def _tenta(self):
        n = len(self.C); W = self.c.janela
        if n < 3 * W:
            return
        h = np.asarray(self.H[n - W:]); l = np.asarray(self.L[n - W:]); c = np.asarray(self.C[n - W:])
        d = n - 3 * W
        amp = max(self.H[d:n - W]) - min(self.L[d:n - W])
        r = detecta(h, l, c, self.c.tol, amp)
        if r is None:
            return
        if r[2] < LARGURA_MIN_TICKS * self.c.tick or r[2] < self.c.larg_min_pts:
            return
        self.topo, self.piso, self.larg, self.meio = r
        self.tem = True; self.fora = 0

    def processa(self):
        tb, hb, lb, cb = self.prev_bar
        dia = int(tb // 86_400_000)
        if dia != self.g_dia:
            self.g_dia = dia; self._reset_sessao()
        self.H.append(hb); self.L.append(lb); self.C.append(cb)
        if self.tem:
            marg = MARGEM_MORTE * self.larg
            if cb > self.topo + marg or cb < self.piso - marg:
                self.fora += 1
                morreu = self.fora >= BARRAS_MORTE
            else:
                self.fora = 0; morreu = False
            if morreu:
                self.tem = False; self._cancela_pend()
        if not self.tem:
            self._tenta()
            if not self.tem:
                return
        if self.pos is not None:
            return
        if self.pend is not None:
            self.esp += 1
            if self.esp < self.c.ttl:
                return
            self._cancela_pend()
        meio, larg = self.meio, self.larg
        if cb < meio:
            lado = -1; alvo = meio - self.c.alvo_frac * larg; stop = meio + self.c.stop_frac * larg
        elif cb > meio:
            lado = 1; alvo = meio + self.c.alvo_frac * larg; stop = meio - self.c.stop_frac * larg
        else:
            return
        lim = no_tick(meio, self.c.tick)
        if lado == -1 and lim <= cb:
            return
        if lado == 1 and lim >= cb:
            return
        if not na_grade(lim):                      # servidor recusa (10015); nada fica armado, tenta na proxima barra
            self.falhas["entrada"] += 1
            return
        self.falhas["armadas"] += 1
        self.pend = dict(lado=lado, lim=lim, stop=no_tick(stop, self.c.tick), alvo=no_tick(alvo, self.c.tick))
        self.esp = 0


def roda(nome: str, cfg: Cfg, ini: date, fim: date, sintetico: bool = False, verbose=True):
    """Roda o EA sobre os pregoes ini..fim (inclusive). sintetico=True usa 4 ticks por M1 em todos os dias."""
    m1 = dados.m1()
    dias = [d for d in sorted(set(m1.index.date)) if ini <= d <= fim]
    antes = m1[m1.index.date < dias[0]]
    ant = antes.iloc[-1]
    ea = EA(cfg, nome, (dados.ms(antes.index[-1]), float(ant.high), float(ant.low), float(ant.close)))
    zer = cfg.hora_zerar * 60 + cfg.min_zerar
    t0 = time.time()
    for dia in dias:
        if sintetico:
            t, p, _ = dados._sinteticos(m1[m1.index.date == dia])
        else:
            t, p, _, _ = dados.ticks(dia)
        t = np.asarray(t, dtype=np.int64); p = np.asarray(p, dtype=float)
        mn = t // 60000
        starts = np.flatnonzero(np.r_[True, mn[1:] != mn[:-1]]); ends = np.r_[starts[1:], len(t)]
        hi = np.maximum.reduceat(p, starts); lo = np.minimum.reduceat(p, starts); cl = p[ends - 1]
        tmin = mn[starts] * 60000
        for i in range(len(starts)):
            a, b = int(starts[i]), int(ends[i])
            if ea.pend is not None or ea.pos is not None:
                ea.avanca(t, p, a, a + 1)
            if i > 0:
                ea.prev_bar = (int(tmin[i - 1]), float(hi[i - 1]), float(lo[i - 1]), float(cl[i - 1]))
            if (int(mn[a]) % 1440) >= zer:
                ea.zerar(t, p, a)
            else:
                ea.processa()
            if ea.pend is not None or ea.pos is not None:
                ea.avanca(t, p, a + 1, b)
            if ea.parou:
                break
        ea.prev_bar = (int(tmin[-1]), float(hi[-1]), float(lo[-1]), float(cl[-1]))
        if ea.parou:
            break
    if verbose:
        print(f"[{nome}] {len(ea.trades)} trades, R$ {ea.pnl:.2f}, falhas {ea.falhas}, {time.time()-t0:.0f}s", flush=True)
    return ea


def mensal(trades) -> pd.Series:
    df = pd.DataFrame(trades)
    if df.empty:
        return pd.Series(dtype=float)
    return df.groupby(pd.to_datetime(df.saida, format="mixed").dt.strftime("%Y-%m")).rs.sum()


def _job(nome, tick):
    ea = roda(nome, Cfg(tick=tick), date(2026, 1, 2), date(2026, 10, 5))
    dados.salvar(nome, ea.trades)
    return nome, len(ea.trades), ea.pnl, mensal(ea.trades).round(2).to_dict(), ea.falhas


def final():
    with ProcessPoolExecutor(max_workers=2) as ex:
        fs = [ex.submit(_job, "WdoRetangulo", 0.5), ex.submit(_job, "WdoRetangulo_tick5", 5.0)]
        for f in as_completed(fs):
            nome, n, rs, mes, fal = f.result()
            print(f"== {nome}: {n} trades, liquido R$ {rs:.2f}, falhas {fal}", flush=True)
            for k, v in sorted(mes.items()):
                print(f"   {k}: {v:10.2f}", flush=True)


def valida():
    ref = pd.read_csv(REF, parse_dates=["t_ent", "t_sai"])
    for rotulo, sint in (("ticks reais do dados.py", False), ("ticks sinteticos (4/M1)", True)):
        ea = roda("val", Cfg(tick=0.5), date(2026, 8, 12), date(2026, 9, 30), sintetico=sint)
        mine = pd.DataFrame(ea.trades)
        mine["t_ent"] = pd.to_datetime(mine.entrada, format="mixed"); mine["t_sai"] = pd.to_datetime(mine.saida, format="mixed")
        print(f"\n--- {rotulo}: port {len(mine)} trades, R$ {mine.rs.sum():.2f} | Testador {len(ref)} trades, R$ {ref.pts.sum()*0.2:.2f}", flush=True)
        ident = 0
        for _, r in ref.iterrows():
            m = mine[(mine.t_ent.dt.date == r.t_ent.date()) & (mine.lado == r.lado)]
            s = "FALTA no port"
            if len(m):
                x = m.iloc[0]
                if x.preco_entrada == r.ent and x.t_ent.floor("min") == r.t_ent.floor("min") and x.preco_saida == r.sai:
                    ident += 1; s = "identico"
                else:
                    s = f"port ent {x.preco_entrada:.0f}@{x.t_ent:%H:%M:%S} sai {x.preco_saida:.0f}@{x.t_sai:%H:%M:%S} {x.motivo}"
            print(f"  {r.t_ent:%m-%d %H:%M:%S} lado {r.lado:+d} ent {r.ent:.0f} sai {r.sai:.0f} ({r.t_sai:%H:%M:%S}) -> {s}", flush=True)
        extra = mine[~mine.t_ent.dt.date.isin(ref.t_ent.dt.date)]
        print(f"  identicos {ident} de {len(ref)}; trades do port sem par no Testador: {len(extra)}", flush=True)
        for _, x in extra.iterrows():
            print(f"    extra {x.t_ent:%m-%d %H:%M:%S} lado {x.lado:+d} ent {x.preco_entrada:.0f} sai {x.preco_saida:.0f} {x.motivo}", flush=True)


if __name__ == "__main__":
    {"valida": valida, "final": final}[sys.argv[1] if len(sys.argv) > 1 else "final"]()
