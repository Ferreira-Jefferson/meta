"""Frente F7 -- spread relativo WIN@ x WDO@: PASSO 2/3 (regra + custo das
DUAS pernas + nulo sign-flip + calibracao nula).

So' existe porque o PASSO 1 (`spread_relativo_f7_investigate.py`) achou
estrutura de reversao que sobrevive ao nulo de REPAREAMENTO DE DIA:
  - variance ratio do nivel do spread (q=30min): real=0,828, nulo (5
    sementes) media=1,502 min=1,475 max=1,550 -- real no percentil 0%
    (mais mean-reverting que TODO repareamento aleatorio).
  - correlacao(z-score, retorno futuro 15min): real=-0,0162, nulo media
    =-0,0088 min=-0,0141 max=-0,0041 -- real no percentil 0%.
  - Teste de metade: o efeito NAO desaparece na 2a metade (corr(z,fwd15)
    1a=-0,0082, 2a=-0,0266 -- mais forte na 2a, nao artefato do inicio).
  - A autocorrelacao lag-1 (TESTE A do passo 1), ao contrario, ficou DENTRO
    do nulo (percentil 20%) -- e' bounce de cada perna sozinha, NAO efeito
    de par. Este script usa so' a parte que sobreviveu ao nulo (janela de
    z-score de 30min / horizonte de dezenas de minutos), nunca lag-1.

Este script NAO presume que a estrutura estatistica vira lucro -- mede,
com custo das DUAS pernas (WIN + WDO, cada uma com sua propria tarifa de
R$0,50/contrato/round-trip e 1 tick de slippage por perna por fill).

Disciplina desta rodada:
  - Beta (hedge ratio, retorno WIN ~ retorno WDO) estimado SO' na 1a
    metade do IS -- a regra e' aplicada tal e qual na 2a metade, sem
    reajuste (a mesma disciplina de "1a metade escolhe, 2a metade
    confere" tambem vale para o PARAMETRO do hedge, nao so' os thresholds
    de entrada/saida).
  - Nulo sign-flip CORRETO (regra 5 do AGENTS.md desta rodada): bruto_d
    (P&L sem custo) e custo_d (sempre negativo) separados por PREGAO;
    serie sintetica = s_d*bruto_d - custo_d, s_d~{-1,+1}, >=5 sementes.
  - Calibracao nula (regra 8): a MESMA regra, no MESMO repareamento de dia
    do passo 1 -- se o nulo tambem "lucra", o resultado real e' ruido.
  - Sensibilidade de parametro (nao 1 ponto so'): duas razoes de contrato
    (1:1, 2:1 WIN:WDO -- nenhuma bate o hedge notional exato de 0,557
    WDO/WIN com contrato inteiro, reportado como limitacao) x 3 limiares
    de entrada -- 6 combinacoes, nao 1 escolhida a dedo.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from spread_relativo_f7_investigate import carregar_is  # noqa: E402

SEED_BASE = 20260827

# Economia REAL dos dois contratos (documentada em `backtest/intraday/
# profiles.py` e no fallback `_ECONOMIA_CONHECIDA` de `copa_lab.py`):
# point_value = trade_tick_value/trade_tick_size, invariante ao override de
# `price_tick_size` (ver docstring de `SymbolProfile.price_tick_size`).
POINT_VALUE_BRL = {"WIN@": 0.2, "WDO@": 10.0}   # R$ por PONTO
TICK_SIZE = {"WIN@": 5.0, "WDO@": 0.5}          # grade real (WINV26/WDOV26)
TICK_VALUE_BRL = {s: POINT_VALUE_BRL[s] * TICK_SIZE[s] for s in POINT_VALUE_BRL}
FEE_ROUND_TRIP_BRL = 0.50   # por CONTRATO, por PERNA (profiles.FUTURES_FEE_ROUND_TRIP_BRL)
SLIPPAGE_TICKS = 1.0        # por FILL (mesmo default de IntradayCostModel)

JANELA_Z = 30
EXIT_Z = 0.3
STOP_Z = 4.0
MAX_HOLD_BARS = 45


# ============================= carregamento =================================

def dias_ohlc(bars: pd.DataFrame) -> dict:
    out = {}
    for d, g in bars.groupby(bars.index.date):
        out[d] = g[["open", "close"]].copy()
    return dict(sorted(out.items()))


def montar_dias_comuns(win_is: pd.DataFrame, wdo_is: pd.DataFrame):
    win_dias = dias_ohlc(win_is)
    wdo_dias = dias_ohlc(wdo_is)
    comuns = sorted(set(win_dias) & set(wdo_dias))
    merges = {}
    for d in comuns:
        j = win_dias[d].rename(columns={"open": "win_open", "close": "win_close"}).join(
            wdo_dias[d].rename(columns={"open": "wdo_open", "close": "wdo_close"}), how="inner"
        )
        if len(j) >= 100:
            merges[d] = j.reset_index(drop=True)
    return merges


def retornos(dia: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    win_c = dia["win_close"].to_numpy(float)
    wdo_c = dia["wdo_close"].to_numpy(float)
    return win_c[1:] / win_c[:-1] - 1.0, wdo_c[1:] / wdo_c[:-1] - 1.0


def estimar_beta(dias: dict, subset: list) -> tuple[float, float]:
    win_pool, wdo_pool = [], []
    for d in subset:
        wr, dr = retornos(dias[d])
        win_pool.append(wr)
        wdo_pool.append(dr)
    win_pool = np.concatenate(win_pool)
    wdo_pool = np.concatenate(wdo_pool)
    b = np.cov(win_pool, wdo_pool, ddof=1)[0, 1] / np.var(wdo_pool, ddof=1)
    a = win_pool.mean() - b * wdo_pool.mean()
    return a, b


# ============================= z-score do nivel ===============================

def nivel_e_z(dia: pd.DataFrame, a: float, b: float, janela: int) -> tuple[np.ndarray, np.ndarray]:
    """Nivel do spread (cumsum do retorno-residuo) e z-score em CADA barra,
    usando so' as `janela` observacoes ANTERIORES (nao inclui a propria barra
    -- mesma janela do passo 1). `z[i] = nan` onde nao ha janela completa."""
    win_r, wdo_r = retornos(dia)
    spread_r = win_r - a - b * wdo_r
    nivel = np.concatenate([[0.0], np.cumsum(spread_r)])
    n = len(nivel)
    z = np.full(n, np.nan)
    s = pd.Series(nivel)
    mu = s.shift(1).rolling(janela).mean().to_numpy()
    sd = s.shift(1).rolling(janela).std(ddof=1).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (nivel - mu) / sd
    z[sd == 0] = np.nan
    return nivel, z


# ============================= simulacao de 1 dia =============================

def _custo_fill(n_win: int, n_wdo: int, slippage_ticks: float | None = None) -> float:
    """Slippage de 1 fill de CADA perna (`slippage_ticks` adverso, valor em
    R$). `None` (default) usa `SLIPPAGE_TICKS` (1 tick, o realista) --
    parametro existe SO' para a secao de sensibilidade otimista do fim do
    script (`slippage_ticks=0.0`), nunca para trocar o numero-manchete."""
    st = SLIPPAGE_TICKS if slippage_ticks is None else slippage_ticks
    return n_win * st * TICK_VALUE_BRL["WIN@"] + n_wdo * st * TICK_VALUE_BRL["WDO@"]


def simular_dia(dia: pd.DataFrame, z: np.ndarray, entry_z: float, n_win: int, n_wdo: int,
                 slippage_ticks: float | None = None) -> list[dict]:
    """Devolve lista de trades fechados no dia, cada um com `bruto_brl`
    (SEM custo, precos crus de abertura) e `custo_brl` (>=0, tarifa fixa das
    DUAS pernas + slippage de 4 fills: entrada win, entrada wdo, saida win,
    saida wdo)."""
    n = len(z)
    win_open = dia["win_open"].to_numpy(float)
    wdo_open = dia["wdo_open"].to_numpy(float)
    win_close = dia["win_close"].to_numpy(float)
    wdo_close = dia["wdo_close"].to_numpy(float)

    trades = []
    estado = None  # None | "long" | "short"
    entry_i = None
    entry_win_px = entry_wdo_px = None

    fee_total = FEE_ROUND_TRIP_BRL * (n_win + n_wdo)

    i = JANELA_Z
    while i < n - 1:
        zi = z[i]
        if not np.isnan(zi):
            if estado is None:
                if zi > entry_z:
                    estado, entry_i = "short", i
                    entry_win_px, entry_wdo_px = win_open[i + 1], wdo_open[i + 1]
                elif zi < -entry_z:
                    estado, entry_i = "long", i
                    entry_win_px, entry_wdo_px = win_open[i + 1], wdo_open[i + 1]
            else:
                held = i - entry_i
                sair = abs(zi) < EXIT_Z or abs(zi) > STOP_Z or held >= MAX_HOLD_BARS
                if sair:
                    exit_win_px, exit_wdo_px = win_open[i + 1], wdo_open[i + 1]
                    sinal = 1.0 if estado == "long" else -1.0
                    bruto = (
                        sinal * (exit_win_px - entry_win_px) * POINT_VALUE_BRL["WIN@"] * n_win
                        + sinal * (exit_wdo_px - entry_wdo_px) * POINT_VALUE_BRL["WDO@"] * n_wdo
                    )
                    custo = fee_total + _custo_fill(n_win, n_wdo, slippage_ticks) * 2  # entrada + saida
                    trades.append({"bruto_brl": bruto, "custo_brl": custo})
                    estado = None
        i += 1

    if estado is not None:
        # flatten forcado no ultimo preco disponivel do dia (sem barra seguinte
        # para executar) -- mesma disciplina de fim de sessao do motor padrao.
        exit_win_px, exit_wdo_px = win_close[-1], wdo_close[-1]
        sinal = 1.0 if estado == "long" else -1.0
        bruto = (
            sinal * (exit_win_px - entry_win_px) * POINT_VALUE_BRL["WIN@"] * n_win
            + sinal * (exit_wdo_px - entry_wdo_px) * POINT_VALUE_BRL["WDO@"] * n_wdo
        )
        custo = fee_total + _custo_fill(n_win, n_wdo, slippage_ticks) * 2
        trades.append({"bruto_brl": bruto, "custo_brl": custo})

    return trades


def rodar_regra(dias: dict, subset: list, a: float, b: float, entry_z: float,
                 n_win: int, n_wdo: int, slippage_ticks: float | None = None) -> dict:
    """`{data: [trades do dia]}` -- so' dias com pelo menos 1 trade fechado
    aparecem (dias sem sinal nao entram no pool de P&L nem no nulo)."""
    por_dia = {}
    for d in subset:
        _, z = nivel_e_z(dias[d], a, b, JANELA_Z)
        trades = simular_dia(dias[d], z, entry_z, n_win, n_wdo, slippage_ticks)
        if trades:
            por_dia[d] = trades
    return por_dia


def resumo(por_dia: dict) -> dict:
    todos = [t for trs in por_dia.values() for t in trs]
    if not todos:
        return {"trades": 0, "bruto": 0.0, "custo": 0.0, "liquido": 0.0,
                "pregoes_com_trade": 0, "win_pct": float("nan")}
    bruto = sum(t["bruto_brl"] for t in todos)
    custo = sum(t["custo_brl"] for t in todos)
    liquido_trades = [t["bruto_brl"] - t["custo_brl"] for t in todos]
    wins = sum(1 for x in liquido_trades if x > 0)
    return {
        "trades": len(todos), "bruto": bruto, "custo": custo,
        "liquido": bruto - custo, "pregoes_com_trade": len(por_dia),
        "win_pct": 100.0 * wins / len(todos),
    }


# ============================= nulo sign-flip (regra 5) =======================

def bruto_custo_por_dia(por_dia: dict) -> tuple[np.ndarray, np.ndarray]:
    dias = sorted(por_dia)
    bruto_d = np.array([sum(t["bruto_brl"] for t in por_dia[d]) for d in dias])
    custo_d = np.array([sum(t["custo_brl"] for t in por_dia[d]) for d in dias])
    return bruto_d, custo_d


def nulo_sign_flip(bruto_d: np.ndarray, custo_d: np.ndarray, n_sementes: int = 500) -> np.ndarray:
    liquidos = np.empty(n_sementes)
    for s in range(n_sementes):
        rng = np.random.default_rng(SEED_BASE + 1000 + s)
        sinais = rng.choice([-1.0, 1.0], size=len(bruto_d))
        liquidos[s] = float(np.sum(sinais * bruto_d - custo_d))
    return liquidos


# ============================= repareamento de dia (regra 8) ==================

def dias_repareados(dias: dict, subset: list, seed: int) -> dict:
    """Mesmo repareamento POSICIONAL do passo 1 (deslinka WDO do WIN daquele
    dia, preserva a dinamica propria de cada perna) -- devolve um dict
    `data -> DataFrame` sintetico no MESMO formato de `montar_dias_comuns`,
    para rodar a regra REAL de trading em cima do nulo."""
    rng = np.random.default_rng(SEED_BASE + 2000 + seed)
    n_dias = len(subset)
    ordem = np.arange(n_dias)
    for _ in range(200):
        rng.shuffle(ordem)
        if n_dias < 2 or not np.any(ordem == np.arange(n_dias)):
            break
    fake = {}
    for i, d in enumerate(subset):
        d_wdo = subset[ordem[i]]
        win_part = dias[d][["win_open", "win_close"]].reset_index(drop=True)
        wdo_part = dias[d_wdo][["wdo_open", "wdo_close"]].reset_index(drop=True)
        m = min(len(win_part), len(wdo_part))
        fake[d] = pd.concat([win_part.iloc[:m], wdo_part.iloc[:m]], axis=1)
    return fake


def num_br(x: float, casas: int = 0) -> str:
    s = f"{x:,.{casas}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def main() -> None:
    win_is = carregar_is("WIN@")
    wdo_is = carregar_is("WDO@")
    dias = montar_dias_comuns(win_is, wdo_is)
    ordenados = sorted(dias)
    meio = ordenados[len(ordenados) // 2]
    metade1 = [d for d in ordenados if d < meio]
    metade2 = [d for d in ordenados if d >= meio]
    print(f"[f7-regra] dias comuns: {len(ordenados)} | metade1={len(metade1)} "
          f"({metade1[0]}..{metade1[-1]}) | metade2={len(metade2)} "
          f"({metade2[0]}..{metade2[-1]})")

    a_full, b_full = estimar_beta(dias, ordenados)
    a_h1, b_h1 = estimar_beta(dias, metade1)
    print(f"[hedge] beta full-IS pooled={b_full:.4f}  |  beta so' 1a metade={b_h1:.4f}")

    razoes = [(1, 1), (2, 1)]
    entry_zs = [1.0, 1.5, 2.0]

    linhas = []
    for n_win, n_wdo in razoes:
        for ez in entry_zs:
            # (A) full-IS pooled beta, regra rodada no IS inteiro (headline "e
            # os dados vissem tudo de uma vez" -- referencia, NAO o numero
            # honesto de fora-da-amostra, que e' (C) abaixo).
            por_dia_full = rodar_regra(dias, ordenados, a_full, b_full, ez, n_win, n_wdo)
            r_full = resumo(por_dia_full)

            # (B) beta so' da 1a metade, regra rodada na PROPRIA 1a metade
            # (auto-consistencia -- "a 1a metade bate nela mesma?").
            por_dia_h1 = rodar_regra(dias, metade1, a_h1, b_h1, ez, n_win, n_wdo)
            r_h1 = resumo(por_dia_h1)

            # (C) beta so' da 1a metade, regra aplicada na 2a metade SEM
            # reajuste -- o numero que decide (teste de metade de verdade).
            por_dia_h2 = rodar_regra(dias, metade2, a_h1, b_h1, ez, n_win, n_wdo)
            r_h2 = resumo(por_dia_h2)

            linhas.append({
                "razao": f"{n_win}W:{n_wdo}D", "entry_z": ez,
                "full_liq": r_full["liquido"], "full_trades": r_full["trades"],
                "full_pregoes": r_full["pregoes_com_trade"],
                "h1_liq": r_h1["liquido"], "h1_trades": r_h1["trades"],
                "h2_liq": r_h2["liquido"], "h2_trades": r_h2["trades"],
            })

    tab = pd.DataFrame(linhas)
    print("\n[REGRA] liquido R$ (ja com custo das 2 pernas) -- full IS pooled vs "
          "metade1 (auto) vs metade2 (fora da amostra, SEM reajuste):")
    print(tab.to_string(index=False, formatters={
        "full_liq": lambda x: num_br(x, 2), "h1_liq": lambda x: num_br(x, 2),
        "h2_liq": lambda x: num_br(x, 2),
    }))

    # ---- escolhe o candidato de METADE2 mais positivo para aprofundar -------
    melhor = tab.loc[tab["h2_liq"].idxmax()]
    print(f"\n[candidato] melhor liquido em metade2 (fora da amostra): razao="
          f"{melhor['razao']} entry_z={melhor['entry_z']} liquido={num_br(melhor['h2_liq'], 2)} "
          f"({int(melhor['h2_trades'])} trades)")

    n_win, n_wdo = (int(melhor["razao"].split("W:")[0]), int(melhor["razao"].split(":")[1].replace("D", "")))
    ez = float(melhor["entry_z"])

    # ---- nulo sign-flip (regra 5), no candidato, na 2a metade (fora da amostra) ----
    por_dia_h2 = rodar_regra(dias, metade2, a_h1, b_h1, ez, n_win, n_wdo)
    bruto_d, custo_d = bruto_custo_por_dia(por_dia_h2)
    liquido_real = float(np.sum(bruto_d) - np.sum(custo_d))
    n_seeds = 500
    nulo = nulo_sign_flip(bruto_d, custo_d, n_sementes=n_seeds)
    pct = 100.0 * (nulo < liquido_real).mean()
    print(f"\n[NULO sign-flip] candidato na metade2, {len(bruto_d)} pregoes-com-trade, "
          f"{n_seeds} sementes:")
    print(f"  liquido real = {num_br(liquido_real, 2)}")
    print(f"  nulo: media={num_br(nulo.mean(), 2)}  min={num_br(nulo.min(), 2)}  "
          f"max={num_br(nulo.max(), 2)}  dp={num_br(nulo.std(ddof=1), 2)}  n={n_seeds}")
    print(f"  percentil do real no nulo = {pct:.1f}%")

    # ---- calibracao nula (regra 8): MESMA regra sobre repareamento de dia ----
    print(f"\n[CALIBRACAO NULA] mesma regra (razao={n_win}W:{n_wdo}D entry_z={ez}) "
          f"sobre repareamento de dia, 5 sementes, aplicada na metade2:")
    liquidos_calib = []
    for seed in range(5):
        fake = dias_repareados(dias, metade2, seed)
        por_dia_fake = rodar_regra(fake, metade2, a_h1, b_h1, ez, n_win, n_wdo)
        r_fake = resumo(por_dia_fake)
        liquidos_calib.append(r_fake["liquido"])
        print(f"  seed={seed}: liquido={num_br(r_fake['liquido'], 2)}  trades={r_fake['trades']}")
    liquidos_calib = np.array(liquidos_calib)
    print(f"  real (par verdadeiro) = {num_br(liquido_real, 2)}  |  "
          f"repareado: media={num_br(liquidos_calib.mean(), 2)} "
          f"min={num_br(liquidos_calib.min(), 2)} max={num_br(liquidos_calib.max(), 2)}")

    # ---- sensibilidade a custo (regra 2): COM custo (acima) vs SEM
    # slippage -- cenario OTIMISTA/NAO VALIDADO (so' a tarifa fixa fica,
    # como se toda entrada e saida fosse preenchida exatamente no preco
    # de decisao -- equivalente a fill MAKER perfeito, que este script NAO
    # modela de verdade: nao ha ordem-limite parada, so' execucao a
    # mercado na abertura da barra seguinte). Mostrado lado a lado com o
    # numero realista de proposito -- nunca escolher um e esconder o outro.
    print("\n[SENSIBILIDADE] mesma regra, SEM slippage (so' tarifa fixa -- "
          "cenario otimista de fill MAKER perfeito, NAO validado neste "
          "script -- comparar com o [REGRA] realista acima, nunca ler "
          "isto sozinho):")
    linhas_sem_slip = []
    for n_win, n_wdo in razoes:
        for ez in entry_zs:
            r1 = resumo(rodar_regra(dias, metade1, a_h1, b_h1, ez, n_win, n_wdo, slippage_ticks=0.0))
            r2 = resumo(rodar_regra(dias, metade2, a_h1, b_h1, ez, n_win, n_wdo, slippage_ticks=0.0))
            linhas_sem_slip.append({
                "razao": f"{n_win}W:{n_wdo}D", "entry_z": ez,
                "h1_bruto": r1["bruto"], "h1_liq": r1["liquido"], "h1_trades": r1["trades"],
                "h2_bruto": r2["bruto"], "h2_liq": r2["liquido"], "h2_trades": r2["trades"],
            })
    tab2 = pd.DataFrame(linhas_sem_slip)
    print(tab2.to_string(index=False, formatters={
        "h1_bruto": lambda x: num_br(x, 2), "h1_liq": lambda x: num_br(x, 2),
        "h2_bruto": lambda x: num_br(x, 2), "h2_liq": lambda x: num_br(x, 2),
    }))


if __name__ == "__main__":
    main()
