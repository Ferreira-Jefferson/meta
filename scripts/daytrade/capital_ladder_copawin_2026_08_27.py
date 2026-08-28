"""Escada de capital da `CopaWin` (WIN@) -- 2026-08-27.

Pergunta do dono: para cada teto de contratos N (1..10, ESTATICO -- sem a
realocacao dinamica de `capital_dinamico_rerun_2026_08_27.py`, que ja
mostrou ser insegura para esta estrategia), qual e' o MENOR capital inicial
que sobrevive ao teste de rejeicao de fila (i.i.d. p=50%, 30 sementes) sem
NENHUMA semente arruinar (equity <= 0) em algum ponto do IN-SAMPLE? E o
quanto esse numero excede o "piso ingenuo" N x R$100 (margem/contrato) x
MARGIN_BUFFER_FUTUROS (2.0) -- o piso que so' cobre 1x a margem nominal, sem
nenhuma folga para sequencia de perdas.

## Modo ESTATICO, de proposito

`CopaWin(teto_contratos=N, ...)` SEM `margin_per_contract_brl` (fica `None`,
default) -- `quantidade_por_entrada` so' olha `teto_contratos x
fracao_entrada`, NUNCA o caixa (`copa_win.py:262-274`). E' o modo que
`capital_dinamico_rerun_2026_08_27.py` chama de "ESTATICO", deliberadamente
SEM o `margin_per_contract_brl` que ativaria a realocacao dinamica -- essa
ficou fora de escopo aqui por pedido explicito da missao (comportamento
dinamico "ja mostrou ser inseguro para essa estrategia").

`config.max_open_contracts` fica FIXO em `TETO_MOTOR=15` (o teto oficial
documentado da Copa BTG para WIN@, `profiles.py:225`) para todo N testado
(1..10) -- nunca menor que N, entao a armadilha de engine descrita na missao
(`_cabe_no_teto`/`_recusa_por_teto`, `machine.py:763-778`) nunca trunca
silenciosamente nenhuma das rodadas.

## Atalho computacional -- DECLARADO explicitamente

A rodada do MOTOR (`run_intraday_backtest`) roda **UMA UNICA VEZ por N**,
com capital NOCIONAL grande (`CAPITAL_NOCIONAL`, de `copa_lab`), e a
sequencia de trades resultante e' reaproveitada para TODAS as avaliacoes da
busca binaria (todo candidato de capital, todas as 30 sementes) -- NENHUMA
rodada do motor com o capital REAL candidato acontece.

Isto so' e' correto porque, no modo ESTATICO, o resultado do motor
(lado/quantidade/preco de entrada e saida/motivo de saida, portanto
`pnl_brl`) e' **matematicamente independente** de `config.initial_capital`:

  1. `quantidade_por_entrada` so' olha `teto_contratos x fracao_entrada`
     (nunca o caixa) quando `margin_per_contract_brl` e' `None` --
     `copa_win.py:262-274`.
  2. `enforce_capital_minimo` (o unico portao do MOTOR que consultaria o
     caixa para decidir se um pregao roda) resolve para `profile.
     max_open_contracts is None` quando nao passado explicitamente
     (`profiles.py:408-409`) -- WIN@ declara `max_open_contracts=15`, entao
     esse portao fica `False` e nenhum pregao e' pulado por capital
     (`engine.py:182`).
  3. As UNICAS leituras de `config.initial_capital` dentro do motor sao
     `on_capital_update` (so' importa quando `margin_per_contract_brl` esta
     setado -- `machine.py:1126`) e o campo de METADADO `capital_base` de
     `IntradayTrade` (`machine.py:1689`), que nao entra em `pnl_brl`
     (`machine.py:263-267`).

Ou seja: rodar o motor de novo para cada capital candidato produziria os
MESMOS trades, byte-a-byte -- so' a leitura POS-HOC do equity (onde comeca
a curva) muda. A reconstrucao pos-hoc por semente (mesma tecnica de
`capital_dinamico_rerun_2026_08_27.py::rejeicao_p_alvo`) e' portanto uma
OTIMIZACAO exata, nao uma perda de rigor -- e e' o que permite usar as 30
sementes completas em TODO passo da busca binaria (nenhuma reducao de
sementes durante a busca foi necessaria).

## "Ruina" e busca binaria

Mesmo criterio do freio incondicional do motor (`engine.py:258`,
`if equity_atual <= 0: wiped_out_at = ts; break`), aplicado pos-hoc sobre a
subamostra de uma semente: `equity = capital_inicial`, depois um degrau por
trade ACEITO (sorteio i.i.d. p=0,5, independente do resultado do trade), na
ORDEM cronologica original; se a curva toca <=0 em algum degrau, a semente
"zerou". Os accepts sao gerados por semente/`n` (nunca por capital) --
capital MAIOR desloca a curva inteira para cima por uma constante, entao
"zerou" e' MONOTONICO NAO-CRESCENTE em capital (prova: mesma mascara de
aceitos, curva_alta(t) = curva_baixa(t) + delta para todo t) -- e' essa
monotonicidade que garante que a busca binaria converge para o minimo
correto.

Busca: comeca no piso ingenuo; se ja for seguro, busca para BAIXO (metade em
metade) ate achar um ponto inseguro; senao, expande para CIMA
geometricamente (x1,5) ate achar um ponto seguro; bisecta entre o par
(inseguro, seguro) ate a faixa convergir dentro de max(R$500, 5% do lado
seguro). O resultado final e' arredondado para CIMA em multiplos de R$50
(preserva a garantia de seguranca, por monotonicidade) e reverificado com as
30 sementes completas.

Janela: SO' o IN-SAMPLE (`copa_lab.barras("WIN@").in_sample()`) -- o corte
congelado OOS_CUTOFF=2026-06-13 (`profiles.py:103`) nunca e' tocado, `.
unlock()` nunca e' chamado.

Uso: `python -u scripts/daytrade/capital_ladder_copawin_2026_08_27.py`
"""
from __future__ import annotations

import csv
import dataclasses
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts" / "daytrade") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.report import maxdd_brl, num_br  # noqa: E402
from strategy.daytrade.base import MARGIN_BUFFER_FUTUROS  # noqa: E402

import copa_lab as L  # noqa: E402
from run_copa_score import CALIBRACAO_IS  # noqa: E402

# ---------------------------------------------------------------------------
# constantes da missao
# ---------------------------------------------------------------------------
SYMBOL = "WIN@"
MARGEM_CONTRATO_BRL = 100.0     # margem/contrato conhecida (portao de capital real anterior)
TETO_MOTOR = 15                  # teto oficial Copa BTG WIN@ (profiles.py:225), fixo p/ nao truncar N 1..10
N_SEMENTES = 30
P_REJEICAO = 0.5
SEED_BASE = 0
N_VALUES = list(range(1, 11))

TOL_ABS_BRL = 500.0
TOL_REL = 0.05
ARREDONDA_BRL = 50.0

OUT_DIR = ROOT / "scripts" / "daytrade"
TRADE_LOG_N1_CSV = OUT_DIR / "capital_ladder_copawin_n1_trades_2026_08_27.csv"
RESULT_JSON = OUT_DIR / "capital_ladder_copawin_result_2026_08_27.json"


# ---------------------------------------------------------------------------
# rodada do motor -- UMA VEZ por N (ver docstring do modulo: "atalho
# computacional").
# ---------------------------------------------------------------------------

def roda_base(n: int, bars: pd.DataFrame, params: dict):
    """`teto_contratos=n`, ESTATICO (`margin_per_contract_brl` nao passado),
    capital NOCIONAL (via `L.config`, grande o bastante p/ nunca quebrar por
    acidente) e `max_open_contracts` elevado para `TETO_MOTOR` (>= n sempre)."""
    instancia = L.robo(SYMBOL, n, **params)
    cfg_nocional = L.config(SYMBOL, n, pernas_maker=int(getattr(instancia, "pernas_maker", 1)))
    cfg = dataclasses.replace(cfg_nocional, max_open_contracts=TETO_MOTOR)
    return run_intraday_backtest(bars, instancia, cfg)


# ---------------------------------------------------------------------------
# rejeicao i.i.d. p=50% pos-hoc -- mesma tecnica de
# `capital_dinamico_rerun_2026_08_27.py::rejeicao_p_alvo`, sem rerodar o
# motor (justificativa completa na docstring do modulo).
# ---------------------------------------------------------------------------

def _mascara(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.random(n) < P_REJEICAO if n else np.array([], dtype=bool)


def n_zerou(trades: list, capital: float, n_sementes: int = N_SEMENTES,
            seed_base: int = SEED_BASE) -> int:
    """Quantas das `n_sementes` sementes tocam equity<=0 em algum ponto,
    partindo de `capital`. Pos-hoc, sem rerodar o motor."""
    if capital <= 0:
        return n_sementes
    n = len(trades)
    count = 0
    for s in range(n_sementes):
        aceita = _mascara(n, seed_base + s)
        acc = capital
        zerou = False
        for t, a in zip(trades, aceita):
            if not a:
                continue
            acc += t.pnl_brl
            if acc <= 0:
                zerou = True
                break
        if zerou:
            count += 1
    return count


def maxdd_sementes(trades: list, capital: float, n_sementes: int = N_SEMENTES,
                    seed_base: int = SEED_BASE) -> np.ndarray:
    """MaxDD (R$) por semente, curva reconstruida a partir de `capital`."""
    n = len(trades)
    out = np.empty(n_sementes)
    for s in range(n_sementes):
        aceita = _mascara(n, seed_base + s)
        curva = [capital]
        acc = capital
        for t, a in zip(trades, aceita):
            if not a:
                continue
            acc += t.pnl_brl
            curva.append(acc)
        out[s] = maxdd_brl(pd.Series(curva))
    return out


# ---------------------------------------------------------------------------
# busca binaria pelo menor capital seguro
# ---------------------------------------------------------------------------

def busca_capital_minimo(trades: list, piso_ingenuo: float) -> tuple[float, float]:
    """Devolve `(capital_minimo_seguro, ultimo_ponto_inseguro_conhecido)`.

    Monotonicidade (ver docstring do modulo): "zerou" e' nao-crescente em
    capital para uma sequencia de trades e sementes fixas -- garante que a
    bisseccao converge para o minimo correto."""
    if n_zerou(trades, piso_ingenuo) == 0:
        seguro = piso_ingenuo
        inseguro = 0.0
        cand = piso_ingenuo
        while cand > 1.0:
            cand2 = cand / 2.0
            if n_zerou(trades, cand2) == 0:
                seguro = cand2
                cand = cand2
            else:
                inseguro = cand2
                break
    else:
        inseguro = piso_ingenuo
        seguro = piso_ingenuo
        fator = 1.5
        guarda = 0
        while n_zerou(trades, seguro) > 0:
            inseguro = seguro
            seguro *= fator
            guarda += 1
            if guarda > 200:
                raise RuntimeError(
                    f"[capital_ladder] busca para cima nao convergiu (inseguro={inseguro}, "
                    f"seguro={seguro}) -- travado apos {guarda} expansoes geometricas."
                )

    while (seguro - inseguro) > max(TOL_ABS_BRL, TOL_REL * seguro):
        meio = (inseguro + seguro) / 2.0
        if n_zerou(trades, meio) == 0:
            seguro = meio
        else:
            inseguro = meio

    seguro_arred = ARREDONDA_BRL * (int(seguro // ARREDONDA_BRL) + (1 if seguro % ARREDONDA_BRL else 0))
    if n_zerou(trades, seguro_arred) != 0:
        # salva-guarda: se o arredondamento (que so' pode subir) quebrar a
        # garantia por algum efeito de borda, sobe de ARREDONDA_BRL em
        # ARREDONDA_BRL ate' resolver, em vez de reportar um numero errado.
        while n_zerou(trades, seguro_arred) != 0:
            seguro_arred += ARREDONDA_BRL
    return seguro_arred, inseguro


# ---------------------------------------------------------------------------
# trade log (N=1) -- CSV
# ---------------------------------------------------------------------------

def salva_trade_log(trades: list, path: Path) -> None:
    campos = ["entry_ts", "exit_ts", "entry_price", "exit_price", "side",
              "quantity", "pnl_brl", "exit_reason"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(campos)
        for t in trades:
            w.writerow([
                t.entry_ts.isoformat(), t.exit_ts.isoformat(),
                t.entry_price, t.exit_price, t.side, t.quantity,
                t.pnl_brl, t.exit_reason.value if hasattr(t.exit_reason, "value") else str(t.exit_reason),
            ])


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    params = dict(CALIBRACAO_IS[SYMBOL])
    bars = L.barras(SYMBOL).in_sample()
    print(f"[capital_ladder] {SYMBOL} IN-SAMPLE: {L.descreve_janela(bars)}")
    print(f"[capital_ladder] parametros CopaWin (CALIBRACAO_IS): {params}")
    print(f"[capital_ladder] margem/contrato=R${num_br(MARGEM_CONTRATO_BRL,0)} | "
          f"MARGIN_BUFFER_FUTUROS={MARGIN_BUFFER_FUTUROS} | teto do motor (fixo)={TETO_MOTOR}")
    print(f"[capital_ladder] rejeicao i.i.d. p={num_br(P_REJEICAO*100,0)}%, {N_SEMENTES} sementes "
          f"(seed_base={SEED_BASE}), tolerancia de convergencia = max(R${num_br(TOL_ABS_BRL,0)}, "
          f"{num_br(TOL_REL*100,0)}%)\n")

    linhas: list[dict] = []

    for n in N_VALUES:
        resultado = roda_base(n, bars, params)
        trades = list(resultado.trades)
        piso_ingenuo = n * MARGEM_CONTRATO_BRL * MARGIN_BUFFER_FUTUROS

        if n == 1:
            salva_trade_log(trades, TRADE_LOG_N1_CSV)
            print(f"[capital_ladder] N=1: trade log salvo em {TRADE_LOG_N1_CSV} ({len(trades)} trades)")

        seguro, inseguro = busca_capital_minimo(trades, piso_ingenuo)
        razao = seguro / piso_ingenuo if piso_ingenuo else float("nan")
        dds = maxdd_sementes(trades, seguro)
        n_zerou_final = n_zerou(trades, seguro)

        linha = dict(
            n=n, trades=len(trades), piso_ingenuo_brl=piso_ingenuo,
            capital_minimo_seguro_brl=seguro, ultimo_inseguro_conhecido_brl=inseguro,
            razao=razao, maxdd_media_brl=float(dds.mean()),
            maxdd_std_brl=float(dds.std(ddof=1)) if len(dds) > 1 else 0.0,
            zerou_no_seguro=n_zerou_final,
        )
        linhas.append(linha)

        print(f"N={n:>2} | trades={len(trades):>5} | piso ingenuo=R${num_br(piso_ingenuo,0):>10} | "
              f"capital minimo seguro=R${num_br(seguro,0):>10} | razao={num_br(razao,2)}x | "
              f"MaxDD@seguro=R${num_br(float(dds.mean()),0)} +/- R${num_br(float(dds.std(ddof=1)) if len(dds)>1 else 0.0,0)} | "
              f"zerou@seguro={n_zerou_final}/{N_SEMENTES} (deve ser 0)", flush=True)

    RESULT_JSON.write_text(json.dumps({
        "symbol": SYMBOL, "params": params, "margem_contrato_brl": MARGEM_CONTRATO_BRL,
        "margin_buffer_futuros": MARGIN_BUFFER_FUTUROS, "teto_motor": TETO_MOTOR,
        "n_sementes": N_SEMENTES, "p_rejeicao": P_REJEICAO, "seed_base": SEED_BASE,
        "tol_abs_brl": TOL_ABS_BRL, "tol_rel": TOL_REL, "janela": L.descreve_janela(bars),
        "resultados": linhas,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[capital_ladder] resultado agregado salvo em {RESULT_JSON}")

    print("\n\n=== ESCADA DE CAPITAL -- CopaWin (WIN@), ESTATICO, IN-SAMPLE ===")
    print(f"{'N':>3}{'piso ingenuo':>16}{'capital minimo seguro':>24}{'razao':>10}"
          f"{'trades':>10}{'MaxDD@seguro':>24}")
    print("-" * 90)
    for l in linhas:
        print(f"{l['n']:>3}{('R$'+num_br(l['piso_ingenuo_brl'],0)):>16}"
              f"{('R$'+num_br(l['capital_minimo_seguro_brl'],0)):>24}{num_br(l['razao'],2)+'x':>10}"
              f"{l['trades']:>10}"
              f"{('R$'+num_br(l['maxdd_media_brl'],0)+' +/- R$'+num_br(l['maxdd_std_brl'],0)):>24}")


if __name__ == "__main__":
    main()
