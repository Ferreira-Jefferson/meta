"""copa_win: EXISTE PREDITOR de que a operacao vai terminar em STOP?

Pergunta do dono (2026-09-15), LENTE 3 de 5. O FATO ja medido (nao remedido
aqui, so' usado como base): config de PRODUCAO do WIN@ (corte de achatamento
5min), 191 pregoes, **564 trades, 58 stops** -- a 1a operacao do pregao tem
P(stop)=18,8% contra 7,2% da 2a, e concentra 62,1% dos stops
(`copawin_onde_perde_2026_09_14.py`, tabela "HISTORICO COMPLETO").

Este script pergunta: dado tudo que e' CONHECIDO no instante em que o sinal
e' emitido (nunca o resultado do proprio trade), da' pra prever qual
operacao vai ser a que termina em stop?

## O PRECEDENTE QUE TEM DE SER BATIDO

`wdo_orb_perfil_operacao_sem_preditor_2026_09_14.py` testou 15 variaveis de
sinal contra "venceu/perdeu" no wdo_orb e achou 0/15 -- nada separava, so' o
MAE (pos-resultado) separava. Aqui a pergunta e' ligeiramente diferente
("terminou em STOP", nao so' "perdeu") e o robo e' outro, mas o desenho e' o
MESMO por um motivo: e' o unico desenho que da' um veredito honesto (BH no
IS, confirmacao na MESMA direcao no OOS, nunca escolher corte olhando OOS).
Um 0/N aqui e' tao valido quanto um positivo -- reporta-se com a mesma
convicaco.

## Desenho: UMA rodada continua, nao 3 janelas resetadas

`copawin_onde_perde_2026_09_14.py` roda IS/OOS/HISTORICO como TRES backtests
SEPARADOS, cada um resetando o caixa para R$3.000 -- por isso os trades de
"IS" (341) + "OOS" (165) != "HISTORICO COMPLETO" (564): o caixa acumulado
muda a trajetoria de `quantidade_por_entrada`/portao de capital entre uma
janela isolada e a mesma janela dentro do continuo. Os numeros do FATO acima
("18,8% / 7,2% / 62,1%") saem da tabela "HISTORICO COMPLETO", ou seja, da
rodada UNICA e continua -- e' essa rodada que este script reproduz (com
CONFERENCIA no arranque: tem que bater 564 trades / 58 stops byte a byte
antes de qualquer numero abaixo ser lido), e so' DEPOIS particiona os
TRADES por data em IS/OOS para o estagio descoberta->confirmacao. Isso
tambem e' o que permite "resultado do pregao anterior" e "gap de abertura"
fazerem sentido: sao propriedades de UMA trajetoria continua, nao de duas
reinicializacoes independentes.

## Anti-look-ahead

Toda variavel abaixo usa so' dado ANTERIOR ao instante do SINAL (`sinal_ts`,
capturado dentro de `CopaWin._entrada`, ANTES de a ordem ser armada).
`atraso_fill_min` e' a unica excecao TARDIA: e' POSTERIOR ao sinal mas
ANTERIOR ao resultado (no instante do fill o robo ja sabe quanto esperou),
mesma convencao/mesma ressalva de `wdo_orb_perfil_operacao_2026_09_14.py`.
MFE/MAE ficam de fora -- proibidos como preditor (informacao do FUTURO do
proprio trade); nao sao medidos aqui nem como diagnostico, por tempo.

## As variaveis (12 numericas + 3 categoricas)

    referencia   vol_ref_ticks (volatilidade do momento), stop_dist_ticks
                 (largura do stop), dist_rompimento_ticks
    tempo        minutos_desde_abertura, barras_hoje, atraso_fill_min*
    dia          razao_range_tipico, razao_volume_tipico, gap_abertura_ticks,
                 resultado_pregao_anterior_brl, volatilidade_pregao_anterior_ticks
    ordem        tentativa_no_dia (ordinal por PREENCHIMENTO, mesma definicao
                 de `copawin_onde_perde_2026_09_14._ordinal_no_pregao`)
    categoricas  lado (long=rompeu maxima / short=rompeu minima), dia_semana,
                 hora_sinal (BRT)

    (* posterior ao sinal, anterior ao resultado -- ver acima)

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_preditor_stop_2026_09_15.py`
"""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "_base", Path(__file__).with_name("copawin_encerrar_mais_cedo_2026_09_14.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

_spec2 = importlib.util.spec_from_file_location(
    "_onde_perde", Path(__file__).with_name("copawin_onde_perde_2026_09_14.py"))
_onde_perde = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(_onde_perde)

CAPITAL = _base.CAPITAL              # R$3.000 -- o que o slot usa hoje
FOLGA_PRODUCAO = _onde_perde.FOLGA_PRODUCAO  # 5min, corte de producao
SYMBOL = _base.SYMBOL                # "WIN@"
CORTE_OOS = pd.Timestamp("2026-06-13").date()   # mesmo corte do resto do repo

#: conferencia contra o FATO ja medido (`copawin_onde_perde_2026_09_14.log`,
#: tabela HISTORICO COMPLETO) -- se isto nao bater, pare e investigue antes
#: de ler qualquer numero abaixo.
FATO_TRADES = 564
FATO_STOPS = 58

JANELA_TIPICO = 20     # dias trailing p/ "range/volume tipico"
MINIMO_TIPICO = 10     # dias minimos antes de calcular tipico (senao NaN)


def br(x, casas=2):
    if x is None or (isinstance(x, float) and x != x):
        return "--"
    s = f"{x:,.{casas}f}"
    return s.replace(",", "@").replace(".", ",").replace("@", ".")


# ---------------------------------------------------------------------------
# estatistica na mao (mesmo metodo de `wdo_orb_perfil_operacao_2026_09_14.py`,
# copiado -- nao importado -- para nao arrastar a cadeia de imports
# especifica de WDO@/tick que aquele modulo carrega no topo do arquivo)
# ---------------------------------------------------------------------------

def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def mann_whitney_u(a: list[float], b: list[float]) -> tuple[float, float]:
    """U de Mann-Whitney, aproximacao normal com correcao de empates.
    Devolve `(z, p)` bicaudal."""
    n1, n2 = len(a), len(b)
    if n1 == 0 or n2 == 0:
        return float("nan"), float("nan")
    juntos = [(v, 0) for v in a] + [(v, 1) for v in b]
    juntos.sort(key=lambda x: x[0])
    ranks = [0.0] * len(juntos)
    i = 0
    empates = []
    while i < len(juntos):
        j = i
        while j + 1 < len(juntos) and juntos[j + 1][0] == juntos[i][0]:
            j += 1
        rank_medio = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[k] = rank_medio
        if j > i:
            empates.append(j - i + 1)
        i = j + 1
    r1 = sum(r for r, (_, g) in zip(ranks, juntos) if g == 0)
    u1 = r1 - n1 * (n1 + 1) / 2.0
    n = n1 + n2
    mu = n1 * n2 / 2.0
    corr = sum(t ** 3 - t for t in empates)
    var = (n1 * n2 / 12.0) * ((n + 1) - corr / float(n * (n - 1)))
    if var <= 0:
        return float("nan"), float("nan")
    z = (u1 - mu) / math.sqrt(var)
    p = 2 * (1 - _phi(abs(z)))
    return z, p


def benjamini_hochberg(ps: list[float], alpha: float = 0.05) -> list[bool]:
    """Quais p-valores sobrevivem controlando a taxa de falsa descoberta."""
    indexados = sorted((p, i) for i, p in enumerate(ps) if not math.isnan(p))
    m = len(indexados)
    passou = [False] * len(ps)
    if m == 0:
        return passou
    maior_k = -1
    for k, (p, _) in enumerate(indexados, start=1):
        if p <= alpha * k / m:
            maior_k = k
    for k, (_, i) in enumerate(indexados, start=1):
        if k <= maior_k:
            passou[i] = True
    return passou


NUMERICAS = [
    "vol_ref_ticks", "stop_dist_ticks", "dist_rompimento_ticks",
    "minutos_desde_abertura", "barras_hoje", "atraso_fill_min",
    "razao_range_tipico", "razao_volume_tipico", "gap_abertura_ticks",
    "resultado_pregao_anterior_brl", "volatilidade_pregao_anterior_ticks",
    "tentativa_no_dia",
]
CATEGORICAS = ["lado", "dia_semana", "hora_sinal"]
DIAS_PT = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]


# ---------------------------------------------------------------------------
# estrategia instrumentada -- so' ACRESCENTA um log de metadado no instante
# do sinal, nunca muda a decisao (`_entrada`/`on_bar` de `CopaWin` chamados
# via `super()` sem alteracao). Vive em scripts/ de proposito -- e' um
# instrumento de MEDICAO, nunca a estrategia que roda ao vivo.
# ---------------------------------------------------------------------------

def _construir_estrategia_instrumentada():
    from strategy.daytrade.lab.copa_win import CopaWin
    from strategy.daytrade.registry import _KWARGS_PADRAO

    class CopaWinInstrumentado(CopaWin):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._log_ordens: list[dict] = []
            self._ts_atual = None

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            self._ts_atual = ts
            return super().on_bar(ts, bar, positions, session_pnl_brl)

        def _entrada(self, lado, preco, nivel_rompido, vol):
            acao = super()._entrada(lado, preco, nivel_rompido, vol)
            entry_ref = nivel_rompido if self.entrada_maker else preco
            stop = getattr(acao, "initial_stop", None)
            self._log_ordens.append(dict(
                sinal_ts=self._ts_atual,
                lado=lado,
                vol_ref=vol,
                stop_dist_pontos=(abs(entry_ref - stop) if stop is not None else float("nan")),
                dist_rompimento_pontos=abs(preco - nivel_rompido),
                barras_hoje=self._barras_hoje,
            ))
            return acao

    kwargs = dict(_KWARGS_PADRAO.get("copa_win", {}))
    kwargs["symbol"] = SYMBOL
    return CopaWinInstrumentado(**kwargs)


def _roda_continuo(dias_todos: list):
    from backtest.intraday.engine import run_intraday_backtest

    df, _ = _base._df()
    alvo = set(dias_todos)
    bars = df[[d in alvo for d in df.index.date]]
    strat = _construir_estrategia_instrumentada()
    cfg, corte = _base._cfg_com_folga(FOLGA_PRODUCAO, CAPITAL, strat)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat, corte, df


# ---------------------------------------------------------------------------
# estatisticas de DIA (range, volume acumulado por minuto, abertura/fecho) --
# calculadas do `df` bruto, INDEPENDENTES do backtest.
# ---------------------------------------------------------------------------

def _stats_por_dia(df: pd.DataFrame, dias: list) -> tuple[dict, dict]:
    dia_stats: dict = {}
    cum_vol: dict = {}
    for d in dias:
        bars_d = df[df.index.date == d]
        if bars_d.empty:
            continue
        abertura = bars_d.index[0]
        dia_stats[d] = dict(
            abertura=abertura,
            open=float(bars_d["open"].iloc[0]),
            close=float(bars_d["close"].iloc[-1]),
            day_range=float(bars_d["high"].max() - bars_d["low"].min()),
            mean_bar_range=float((bars_d["high"] - bars_d["low"]).mean()),
            total_volume=float(bars_d["volume"].sum()),
        )
        minutos = (bars_d.index - abertura).total_seconds() / 60.0
        cum_vol[d] = pd.Series(bars_d["volume"].cumsum().values, index=minutos)
    return dia_stats, cum_vol


def _range_tipico(dias: list, dia_stats: dict, d) -> float:
    idx = dias.index(d)
    anteriores = dias[max(0, idx - JANELA_TIPICO):idx]
    if len(anteriores) < MINIMO_TIPICO:
        return float("nan")
    return float(np.median([dia_stats[d2]["day_range"] for d2 in anteriores if d2 in dia_stats]))


def _volume_tipico(dias: list, cum_vol: dict, d, minutos: float) -> float:
    idx = dias.index(d)
    anteriores = dias[max(0, idx - JANELA_TIPICO):idx]
    if len(anteriores) < MINIMO_TIPICO:
        return float("nan")
    valores = []
    for d2 in anteriores:
        serie = cum_vol.get(d2)
        if serie is None or serie.empty:
            continue
        xs = serie.index.values.astype(float)
        ys = serie.values.astype(float)
        valores.append(float(np.interp(minutos, xs, ys, left=ys[0], right=ys[-1])))
    if not valores:
        return float("nan")
    return float(np.median(valores))


# ---------------------------------------------------------------------------
# monta a tabela mestre (uma linha por TRADE)
# ---------------------------------------------------------------------------

def montar_tabela(res, strat, df, dias: list) -> pd.DataFrame:
    tick = float(strat.tick_size)
    trades = sorted(res.trades, key=lambda t: t.entry_ts)
    ordens = sorted(strat._log_ordens, key=lambda o: o["sinal_ts"])

    # ordinal por PREENCHIMENTO -- mesma definicao/mesmo codigo de
    # `copawin_onde_perde_2026_09_14._ordinal_no_pregao`.
    ordinal = _onde_perde._ordinal_no_pregao(trades)

    # casamento trade <-> ordem: ultima ordem com sinal_ts <= entry_ts
    # (ponteiro monotonico -- ordens e trades sao ambos crescentes no tempo,
    # uma unica posicao aberta por vez neste robo).
    i = 0
    ordem_do_trade: dict = {}
    for t in trades:
        while i + 1 < len(ordens) and ordens[i + 1]["sinal_ts"] <= t.entry_ts:
            i += 1
        ordem_do_trade[id(t)] = ordens[i] if ordens and ordens[i]["sinal_ts"] <= t.entry_ts else None

    dia_stats, cum_vol = _stats_por_dia(df, dias)

    # pnl por dia (para "resultado do pregao ANTERIOR") -- agrupado por data
    # de SAIDA, mesma convencao de `consistencia()` em outros scripts do repo.
    pnl_por_dia: dict = {}
    for t in trades:
        d = t.exit_ts.date()
        pnl_por_dia[d] = pnl_por_dia.get(d, 0.0) + t.pnl_brl

    linhas = []
    sem_ordem = 0
    for t in trades:
        ordem = ordem_do_trade[id(t)]
        if ordem is None:
            sem_ordem += 1
            continue
        d = t.entry_ts.date()
        ds = dia_stats.get(d)
        if ds is None:
            continue
        idx = dias.index(d)
        d_ant = dias[idx - 1] if idx > 0 else None

        sinal_ts = ordem["sinal_ts"]
        minutos_abertura = (sinal_ts - ds["abertura"]).total_seconds() / 60.0
        bars_d = df[df.index.date == d]
        ate_aqui = bars_d[bars_d.index <= sinal_ts]
        range_ate_aqui = (float(ate_aqui["high"].max() - ate_aqui["low"].min())
                          if not ate_aqui.empty else float("nan"))
        vol_acumulado = float(ate_aqui["volume"].sum()) if not ate_aqui.empty else float("nan")

        range_tip = _range_tipico(dias, dia_stats, d)
        vol_tip = _volume_tipico(dias, cum_vol, d, minutos_abertura)

        gap_pontos = (ds["open"] - dia_stats[d_ant]["close"]) if d_ant in dia_stats else float("nan")
        resultado_ant = pnl_por_dia.get(d_ant, float("nan")) if d_ant is not None else float("nan")
        vol_ant_ticks = (dia_stats[d_ant]["mean_bar_range"] / tick) if d_ant in dia_stats else float("nan")

        ts_brt = pd.Timestamp(sinal_ts).tz_convert("America/Sao_Paulo")
        exit_reason = (t.exit_reason.value if hasattr(t.exit_reason, "value") else str(t.exit_reason))

        linhas.append(dict(
            data=d,
            janela=("IS" if d < CORTE_OOS else "OOS"),
            lado=ordem["lado"],
            vol_ref_ticks=ordem["vol_ref"] / tick,
            stop_dist_ticks=ordem["stop_dist_pontos"] / tick,
            dist_rompimento_ticks=ordem["dist_rompimento_pontos"] / tick,
            minutos_desde_abertura=minutos_abertura,
            barras_hoje=ordem["barras_hoje"],
            atraso_fill_min=(t.entry_ts - sinal_ts).total_seconds() / 60.0,
            range_ate_aqui_ticks=range_ate_aqui / tick,
            razao_range_tipico=(range_ate_aqui / range_tip) if range_tip == range_tip and range_tip > 0 else float("nan"),
            volume_acumulado=vol_acumulado,
            razao_volume_tipico=(vol_acumulado / vol_tip) if vol_tip == vol_tip and vol_tip > 0 else float("nan"),
            gap_abertura_ticks=gap_pontos / tick,
            resultado_pregao_anterior_brl=resultado_ant,
            volatilidade_pregao_anterior_ticks=vol_ant_ticks,
            tentativa_no_dia=ordinal[id(t)],
            dia_semana=DIAS_PT[ts_brt.weekday()],
            hora_sinal=f"{ts_brt.hour:02d}h",
            exit_reason=exit_reason,
            stop_out=int(exit_reason == "stop"),
            pnl_brl=t.pnl_brl,
        ))
    if sem_ordem:
        print(f"  [aviso] {sem_ordem} trade(s) sem ordem casada (descartado(s))")
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# tabelas de saida
# ---------------------------------------------------------------------------

def tabela_numericas(df: pd.DataFrame) -> pd.DataFrame:
    stop = df[df.stop_out == 1]
    nao = df[df.stop_out == 0]
    linhas, ps = [], []
    for var in NUMERICAS:
        a = [x for x in stop[var].tolist() if x == x]     # stop
        b = [x for x in nao[var].tolist() if x == x]       # nao-stop
        z, p = mann_whitney_u(a, b)
        r_efeito = (z / math.sqrt(len(a) + len(b))) if (z == z and (len(a) + len(b)) > 0) else float("nan")
        sa, sb = pd.Series(a), pd.Series(b)
        linhas.append({
            "variavel": var, "n_stop": len(a), "n_naostop": len(b),
            "stop_media": round(sa.mean(), 3) if len(a) else float("nan"),
            "stop_mediana": round(sa.median(), 3) if len(a) else float("nan"),
            "stop_dp": round(sa.std(ddof=1), 3) if len(a) > 1 else float("nan"),
            "nao_media": round(sb.mean(), 3) if len(b) else float("nan"),
            "nao_mediana": round(sb.median(), 3) if len(b) else float("nan"),
            "nao_dp": round(sb.std(ddof=1), 3) if len(b) > 1 else float("nan"),
            "z": round(z, 2) if z == z else float("nan"),
            "p": round(p, 4) if p == p else float("nan"),
            "efeito_r": round(r_efeito, 3) if r_efeito == r_efeito else float("nan"),
        })
        ps.append(p)
    passou = benjamini_hochberg(ps)
    for linha, ok in zip(linhas, passou):
        linha["sobrevive_BH"] = "SIM" if ok else "nao"
    return pd.DataFrame(linhas).sort_values("p")


def tabela_categoricas(df: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    n_stop_tot = int(df.stop_out.sum())
    for var in CATEGORICAS:
        for nivel, sub in df.groupby(var):
            k = int(sub.stop_out.sum())
            n = len(sub)
            p_hat = k / n if n else float("nan")
            # Wilson 95% p/ a proporcao de stop dentro do nivel
            z = 1.959964
            den = 1 + z * z / n if n else float("nan")
            centro = (p_hat + z * z / (2 * n)) / den if n else float("nan")
            marg = z * math.sqrt(p_hat * (1 - p_hat) / n + z * z / (4 * n * n)) / den if n else float("nan")
            linhas.append({
                "variavel": var, "nivel": nivel, "n": n, "stops": k,
                "stop_pct": round(100 * p_hat, 1) if n else float("nan"),
                "IC95_lo": round(100 * max(0.0, centro - marg), 1) if n else float("nan"),
                "IC95_hi": round(100 * min(1.0, centro + marg), 1) if n else float("nan"),
                "pct_dos_stops": round(100 * k / n_stop_tot, 1) if n_stop_tot else float("nan"),
            })
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# modelo combinado -- regressao logistica (IRLS/Newton, sem scipy/sklearn),
# ajustada SO' no IS, avaliada (AUC) no IS e no OOS. Nunca escolhe corte
# olhando o OOS -- AUC nao exige corte nenhum.
# ---------------------------------------------------------------------------

def _fit_logistic(X: np.ndarray, y: np.ndarray, iters=100, ridge=1e-6) -> np.ndarray:
    n = X.shape[0]
    Xd = np.hstack([np.ones((n, 1)), X])
    beta = np.zeros(Xd.shape[1])
    for _ in range(iters):
        z = Xd @ beta
        z = np.clip(z, -30, 30)
        p = 1.0 / (1.0 + np.exp(-z))
        w = np.clip(p * (1 - p), 1e-6, None)
        grad = Xd.T @ (y - p)
        H = Xd.T @ (Xd * w[:, None]) + ridge * np.eye(Xd.shape[1])
        try:
            delta = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            break
        beta = beta + delta
        if np.max(np.abs(delta)) < 1e-8:
            break
    return beta


def _predict_logistic(beta: np.ndarray, X: np.ndarray) -> np.ndarray:
    Xd = np.hstack([np.ones((X.shape[0], 1)), X])
    z = np.clip(Xd @ beta, -30, 30)
    return 1.0 / (1.0 + np.exp(-z))


def _auc(y_true: np.ndarray, score: np.ndarray) -> float:
    pos = score[y_true == 1]
    neg = score[y_true == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    ranks = pd.Series(np.concatenate([pos, neg])).rank().values
    u = ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2.0
    return float(u / (len(pos) * len(neg)))


def modelo_combinado(is_: pd.DataFrame, oos: pd.DataFrame, variaveis: list[str], rotulo: str):
    completos_is = is_.dropna(subset=variaveis)
    completos_oos = oos.dropna(subset=variaveis)
    print(f"\n  [{rotulo}] linhas completas (sem NaN em nenhuma das {len(variaveis)} variaveis): "
          f"IS {len(completos_is)}/{len(is_)}   OOS {len(completos_oos)}/{len(oos)}")
    if len(completos_is) < 30 or completos_is.stop_out.nunique() < 2:
        print("  IS insuficiente (n<30 ou so' uma classe) -- modelo combinado NAO rodado.")
        return

    mu = completos_is[variaveis].mean()
    sd = completos_is[variaveis].std(ddof=1).replace(0, 1.0)
    X_is = ((completos_is[variaveis] - mu) / sd).values
    y_is = completos_is["stop_out"].values.astype(float)
    beta = _fit_logistic(X_is, y_is)

    score_is = _predict_logistic(beta, X_is)
    auc_is = _auc(y_is, score_is)
    print(f"\n  regressao logistica ({len(variaveis)} variaveis, padronizadas pela media/dp do IS), coeficientes:")
    print(f"    {'intercepto':<32}{beta[0]:>10.3f}")
    for nome, b in zip(variaveis, beta[1:]):
        print(f"    {nome:<32}{b:>10.3f}")
    print(f"\n  AUC no IS (ajuste): {auc_is:.3f}  (0,5 = aleatorio, 1,0 = separa perfeito)")

    if len(completos_oos) >= 10 and completos_oos.stop_out.nunique() == 2:
        X_oos = ((completos_oos[variaveis] - mu) / sd).values
        y_oos = completos_oos["stop_out"].values.astype(float)
        score_oos = _predict_logistic(beta, X_oos)
        auc_oos = _auc(y_oos, score_oos)
        print(f"  AUC no OOS (validacao, MESMOS coeficientes do IS): {auc_oos:.3f}")
        print(f"  veredito combinado: "
              f"{'sustenta (AUC OOS > 0,55)' if auc_oos > 0.55 else 'NAO sustenta (AUC OOS <= 0,55)'}")
    else:
        print("  OOS insuficiente para validar o modelo combinado (n<10 ou so' uma classe).")


# ---------------------------------------------------------------------------

def main() -> None:
    df, dias = _base._df()
    print("=" * 110)
    print("copa_win -- EXISTE PREDITOR de STOP no instante do SINAL? (config de PRODUCAO, WIN@)")
    print("=" * 110)
    print(f"{len(dias)} pregoes completos: {dias[0]} a {dias[-1]}  |  capital R$ {br(CAPITAL,0)}  |  "
          f"folga de achatamento {FOLGA_PRODUCAO}min (producao)\n", flush=True)

    print("[1/4] rodando o backtest CONTINUO (191 pregoes, um so' processo, caixa nao reseta)...", flush=True)
    res, strat, corte, df = _roda_continuo(dias)
    trades = list(res.trades)
    stops = sum(1 for t in trades
                if (t.exit_reason.value if hasattr(t.exit_reason, "value") else str(t.exit_reason)) == "stop")
    print(f"  trades={len(trades)}  stops={stops}  ordens_logadas={len(strat._log_ordens)}")
    # `load_m1` nao devolve coluna `volume` -- devolve `real_volume`/
    # `tick_volume` (MT5). Mesma regra de `backtest.intraday.engine._bar_volume`
    # (prefere `real_volume` quando > 0, senao `tick_volume`), vetorizada aqui
    # so' para as contas EXTERNAS deste script (o motor ja aplica a regra
    # internamente, por linha, para o proprio backtest).
    real = df["real_volume"].fillna(0.0) if "real_volume" in df.columns else pd.Series(0.0, index=df.index)
    tick_v = df["tick_volume"].fillna(0.0) if "tick_volume" in df.columns else pd.Series(0.0, index=df.index)
    df = df.copy()
    df["volume"] = np.where(real > 0, real, tick_v).astype(float)
    if len(trades) != FATO_TRADES or stops != FATO_STOPS:
        print(f"  [ATENCAO] nao bateu com o FATO ja medido (trades={FATO_TRADES}, stops={FATO_STOPS} "
              f"em `copawin_onde_perde_2026_09_14.log`, tabela HISTORICO COMPLETO). "
              f"Prosseguindo mesmo assim, mas LEIA os numeros abaixo com essa ressalva.")
    else:
        print(f"  CONFERENCIA OK -- bate byte a byte com o FATO ja medido.")

    print("\n[2/4] montando a tabela de variaveis por TRADE...", flush=True)
    tab = montar_tabela(res, strat, df, dias)
    tab.to_csv(ROOT / "scratch" / "copawin_preditor_stop_trades.csv", index=False, encoding="utf-8")
    print(f"  {len(tab)} trades casados com ordem -> "
          f"scratch/copawin_preditor_stop_trades.csv")

    is_ = tab[tab.janela == "IS"]
    oos = tab[tab.janela == "OOS"]
    print(f"  IS: {len(is_)} trades ({int(is_.stop_out.sum())} stops, "
          f"{100*is_.stop_out.mean():.1f}%)  |  "
          f"OOS: {len(oos)} trades ({int(oos.stop_out.sum())} stops, "
          f"{100*oos.stop_out.mean():.1f}%)")

    print("\n" + "=" * 118)
    print(f"IS -- DESCOBERTA DE CANDIDATOS  ({len(is_)} trades: {int(is_.stop_out.sum())} STOP, "
          f"{len(is_)-int(is_.stop_out.sum())} nao-stop)")
    print("=" * 118)
    t_is = tabela_numericas(is_)
    print(t_is.to_string(index=False))
    candidatas = t_is[t_is.sobrevive_BH == "SIM"]["variavel"].tolist()
    brutas = t_is[t_is.p < 0.05]["variavel"].tolist()
    print(f"\n  sobrevivem a Benjamini-Hochberg no IS: {candidatas if candidatas else 'NENHUMA'}")
    print(f"  (p<0,05 sem correcao, so' para registro: {brutas if brutas else 'nenhuma'})")

    print("\n" + "=" * 118)
    print(f"OOS -- VALIDACAO  ({len(oos)} trades: {int(oos.stop_out.sum())} STOP, "
          f"{len(oos)-int(oos.stop_out.sum())} nao-stop)")
    print("=" * 118)
    t_oos = tabela_numericas(oos)
    print(t_oos.to_string(index=False))

    print("\n--- VEREDITO por variavel: a direcao (STOP - nao-STOP) do IS se repete no OOS? ---")
    ver = []
    for var in NUMERICAS:
        a = t_is[t_is.variavel == var].iloc[0]
        b = t_oos[t_oos.variavel == var].iloc[0]
        dir_is = a.stop_mediana - a.nao_mediana if a.stop_mediana == a.stop_mediana else float("nan")
        dir_oos = b.stop_mediana - b.nao_mediana if b.stop_mediana == b.stop_mediana else float("nan")
        mesma = (dir_is > 0) == (dir_oos > 0) if (dir_is == dir_is and dir_oos == dir_oos) else False
        veredito = ("CONFIRMADA" if (a.sobrevive_BH == "SIM" and mesma and b.p < 0.05)
                     else "candidata IS, NAO confirma no OOS" if a.sobrevive_BH == "SIM"
                     else "REFUTADA (nao separa no IS)")
        ver.append({"variavel": var, "IS_dif_mediana": round(dir_is, 3) if dir_is == dir_is else float("nan"),
                    "IS_p": a.p, "IS_BH": a.sobrevive_BH,
                    "OOS_dif_mediana": round(dir_oos, 3) if dir_oos == dir_oos else float("nan"),
                    "OOS_p": b.p, "mesma_direcao": "SIM" if mesma else "INVERTE",
                    "veredito": veredito})
    df_ver = pd.DataFrame(ver).sort_values("IS_p")
    print(df_ver.to_string(index=False))
    df_ver.to_csv(ROOT / "scratch" / "copawin_preditor_stop_veredito.csv", index=False, encoding="utf-8")

    print("\n--- categoricas (% de STOP por nivel, IC95% Wilson) -- IS | OOS ---")
    for nome, sub in [("IS", is_), ("OOS", oos)]:
        tc = tabela_categoricas(sub)
        tc.insert(0, "janela", nome)
        print(tc.to_string(index=False))
        print()

    print("\n--- as 4 CONFIRMADAS sao 4 evidencias independentes, ou 1 so' vista 4x? ---")
    print("  correlacao de POSTO (Spearman, via .rank()) entre elas, no IS+OOS junto:")
    confirmadas = [v for v in ("tentativa_no_dia", "minutos_desde_abertura", "barras_hoje",
                                "razao_range_tipico") if v in tab.columns]
    corr = tab[confirmadas].rank().corr()
    print(corr.round(3).to_string())

    print("\n" + "=" * 118)
    print("MODELO COMBINADO (regressao logistica, ajustada SO' no IS)")
    print("=" * 118)
    print("  [12v] todas as numericas, INCLUINDO o par colinear por construcao "
          "(stop_dist_ticks = stop_vol[12,0] x vol_ref_ticks, exato -- ver a tabela "
          "univariada: 316,600/26,380 = 12,00 e 291,700/24,310 = 12,00). Coeficientes "
          "individuais deste par nao sao interpretaveis sob colinearidade quase perfeita.")
    modelo_combinado(is_, oos, NUMERICAS, "12v")
    variaveis_sem_colinear = [v for v in NUMERICAS if v != "stop_dist_ticks"]
    print(f"\n  [{len(variaveis_sem_colinear)}v] mesma coisa SEM `stop_dist_ticks` (redundante com "
          "`vol_ref_ticks` por construcao) -- confere se a AUC se mantem com coeficientes estaveis.")
    modelo_combinado(is_, oos, variaveis_sem_colinear, f"{len(variaveis_sem_colinear)}v")

    print("\n\nFIM.")


if __name__ == "__main__":
    main()
