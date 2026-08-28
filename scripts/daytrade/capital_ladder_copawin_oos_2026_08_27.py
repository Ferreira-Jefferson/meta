"""Escada de capital da `CopaWin` (WIN@) contra o OOS -- 2026-08-27, confirmacao
final autorizada pelo dono (ver `copa_win_confirmacao_oos_2026_08_27.py` para o
numero isolado de R$/pregao e o modelo de custo/preenchimento).

Reusa (NAO reimplementa) toda a logica de busca binaria/rejeicao i.i.d. de
`capital_ladder_copawin_2026_08_27.py` (mesmo `MARGEM_CONTRATO_BRL=R$100`,
`MARGIN_BUFFER_FUTUROS=2.0`, `TETO_MOTOR=15`, 30 sementes, p=50%, mesma
tolerancia/arredondamento de convergencia) -- so' TROCA a janela de dado:

  (a) OOS-only  -- `copa_lab.barras("WIN@").out_of_sample()` (51 pregoes),
      confirmacao ISOLADA, mesmo tamanho de amostra que o OOS permitir.
  (b) IS+OOS combinado cronologicamente -- numero FINAL consolidado. Valido
      porque o OOS ja foi destravado por decisao do dono para esta rodada
      (nao e' mais um "peek": e' medicao final, mesmo raciocinio de
      `copa_oos_gasto_2026_08_26`).

Aplica a MESMA correcao de margem documentada em
`capital_ladder_qualidade_sinal_reversao_2026_08_27` (bug corrigido no mesmo
dia): a busca original so' checava `capital + pnl_acumulado <= 0`, nunca se o
capital cobriria a margem para sequer ABRIR a posicao. Correcao (deslocamento
aditivo puro da curva de equity, sem rerodar nada):

    capital_minimo_real(N) = capital_minimo_seguro_medido(N) + piso_ingenuo(N)
    piso_ingenuo(N) = N * MARGEM_CONTRATO_BRL * MARGIN_BUFFER_FUTUROS

EXATA para futuro (margem por contrato e' fixa, ao contrario de acao onde o
piso usa o MAIOR preco observado como cota conservadora).

Uso: `python -u scripts/daytrade/capital_ladder_copawin_oos_2026_08_27.py`
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts" / "daytrade") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))

from backtest.intraday.report import num_br  # noqa: E402

import copa_lab as L  # noqa: E402
from run_copa_score import CALIBRACAO_IS  # noqa: E402

# Reuso DIRETO -- nao reimplementa bisseccao/rejeicao/constantes.
import capital_ladder_copawin_2026_08_27 as CL  # noqa: E402

SYMBOL = "WIN@"
UNLOCK_REASON = (
    "Validacao final autorizada pelo dono em 2026-08-27 para consolidar "
    "capital/sinal antes de atualizar producao"
)

OUT_JSON = ROOT / "scripts" / "daytrade" / "capital_ladder_copawin_oos_2026_08_27_result.json"


def roda_escada(rotulo: str, bars: pd.DataFrame, params: dict) -> list[dict]:
    """Mesma escada N=1..10 de `capital_ladder_copawin_2026_08_27.main()`,
    reusando `CL.roda_base`/`CL.busca_capital_minimo`/`CL.n_zerou`/
    `CL.maxdd_sementes`, aplicada a `bars` (OOS-only ou combinado)."""
    linhas: list[dict] = []
    print(f"\n[capital_ladder_oos] === {rotulo}: {L.descreve_janela(bars)} ===")
    for n in CL.N_VALUES:
        resultado = CL.roda_base(n, bars, params)
        trades = list(resultado.trades)
        piso = n * CL.MARGEM_CONTRATO_BRL * CL.MARGIN_BUFFER_FUTUROS

        seguro, inseguro = CL.busca_capital_minimo(trades, piso)
        capital_minimo_real = seguro + piso
        razao_real = capital_minimo_real / piso if piso else float("nan")
        dds = CL.maxdd_sementes(trades, seguro)
        n_zerou_final = CL.n_zerou(trades, seguro)

        linha = dict(
            n=n, trades=len(trades), piso_ingenuo_brl=piso,
            capital_minimo_seguro_medido_brl=seguro,
            ultimo_inseguro_conhecido_brl=inseguro,
            capital_minimo_real_brl=capital_minimo_real,
            razao_real=razao_real,
            maxdd_media_brl=float(dds.mean()) if len(dds) else 0.0,
            maxdd_std_brl=float(dds.std(ddof=1)) if len(dds) > 1 else 0.0,
            zerou_no_seguro=n_zerou_final,
        )
        linhas.append(linha)
        print(f"N={n:>2} | trades={len(trades):>4} | piso ingenuo=R${num_br(piso,0):>9} | "
              f"seguro(medido)=R${num_br(seguro,0):>9} | REAL(medido+piso)=R${num_br(capital_minimo_real,0):>9} | "
              f"razao real={num_br(razao_real,2)}x | zerou@seguro={n_zerou_final}/{CL.N_SEMENTES}", flush=True)
    return linhas


def main() -> None:
    params = dict(CALIBRACAO_IS[SYMBOL])
    print(f"[capital_ladder_oos] parametros CopaWin (CALIBRACAO_IS): {params}")
    print(f"[capital_ladder_oos] margem/contrato=R${num_br(CL.MARGEM_CONTRATO_BRL,0)} | "
          f"MARGIN_BUFFER_FUTUROS={CL.MARGIN_BUFFER_FUTUROS} | teto do motor (fixo)={CL.TETO_MOTOR} | "
          f"{CL.N_SEMENTES} sementes, p={num_br(CL.P_REJEICAO*100,0)}%")

    travadas = L.barras(SYMBOL)
    travadas.unlock(UNLOCK_REASON)
    ins = travadas.in_sample()
    oos = travadas.out_of_sample()
    combinado = pd.concat([ins, oos])

    linhas_oos = roda_escada("OOS-ONLY (confirmacao isolada, 51 pregoes)", oos, params)
    linhas_comb = roda_escada("IS+OOS COMBINADO (numero final consolidado, 180 pregoes)", combinado, params)

    OUT_JSON.write_text(json.dumps({
        "symbol": SYMBOL, "params": params,
        "margem_contrato_brl": CL.MARGEM_CONTRATO_BRL,
        "margin_buffer_futuros": CL.MARGIN_BUFFER_FUTUROS, "teto_motor": CL.TETO_MOTOR,
        "n_sementes": CL.N_SEMENTES, "p_rejeicao": CL.P_REJEICAO,
        "janela_oos": L.descreve_janela(oos), "janela_combinado": L.descreve_janela(combinado),
        "resultados_oos_only": linhas_oos,
        "resultados_is_oos_combinado": linhas_comb,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[capital_ladder_oos] resultado salvo em {OUT_JSON}")

    print("\n\n=== TABELA FINAL -- capital_minimo_real(N) = medido + piso de margem ===")
    print(f"{'N':>3}{'OOS-only':>16}{'IS+OOS combinado':>20}")
    print("-" * 42)
    by_n_oos = {l['n']: l for l in linhas_oos}
    by_n_comb = {l['n']: l for l in linhas_comb}
    for n in CL.N_VALUES:
        ro = by_n_oos[n]['capital_minimo_real_brl']
        rc = by_n_comb[n]['capital_minimo_real_brl']
        print(f"{n:>3}{('R$'+num_br(ro,0)):>16}{('R$'+num_br(rc,0)):>20}")


if __name__ == "__main__":
    main()
