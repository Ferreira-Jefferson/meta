"""Salva as barras TICK do WDO@ (IS + OOS) em parquet, UMA vez.

Motivo: `buscar_ticks` leva ~10,7 min para 123 pregoes (123 chamadas de
`copy_ticks_range`, ~5,2s cada) e era pago de novo em TODA rodada. Com o
parquet no disco, a leitura passa a ser de segundos e sobra so' o tempo de
motor -- que por sua vez e' paralelizavel (ver
`wdof1_rerun_paralelo_2026_08_27.py`).

AVISO 2026-09-07 -- RESOLVIDO: o parquet em disco ESTAVA TRUNCADO
==================================================================
O `WDO_A_f1.parquet` que existia ate' 2026-09-07 tinha sido gerado pela
versao ERRADA de `wdo_grid_reload_f1_tick_probe.py::buscar_ticks` (ler o
AVISO no topo daquele arquivo): cobria 14:58..18:29 de cada pregao -- 3h31
de um pregao de 9h30, 4.011.197 ticks -- porque a janela pedida ao terminal
andava +3h e o index vinha rotulado 3h cedo. A funcao foi corrigida e ESTE
SCRIPT foi rodado de novo (~10,7 min) no mesmo dia, substituindo o arquivo
truncado: 4.011.197 -> 20.646.379 ticks (5,15x), cobertura de minutos de
pregao (mediana/pregao) de 212/570 para 570/570 (38,2% -> 100,0%). Os
conjuntos de dias IS (72, 2026-02-27..2026-06-12) e OOS (51,
2026-06-15..2026-08-25, 2 deles `m1_fallback`) ficaram os MESMOS -- so' a
cobertura dentro de cada dia mudou. Verificacao de identidade de negocio
(instante+preco+volume): os 4.010.057 ticks do arquivo truncado acharam par
identico no canonico, zero negocio perdido na troca. Backup do arquivo
truncado em `data/raw_ticks/WDO_A_f1.parquet.bak-2026-09-07` (gitignored).
Suite depois da troca: 1698 passed, 1 skipped.

Nao inventa dado: usa exatamente `carregar_tick_bars()` (IS) e
`carregar_oos_bars()` (OOS, com o fallback M1 dos 2 dias sem tick retido) dos
labs existentes, e grava o resultado tal como eles devolvem. Os 2 dias de
fallback M1 ficam MARCADOS na coluna `fonte` para nao se perder a distincao.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wdo_grid_reload_f1_tick_lab import carregar_tick_bars  # noqa: E402
from wdo_grid_reload_f1_tick_lab_oos_2026_08_27 import carregar_oos_bars  # noqa: E402

DESTINO = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"


def main() -> None:
    t0 = time.perf_counter()
    print("[cache] baixando tick do IS ...", flush=True)
    dias_is, bars_is = carregar_tick_bars()
    bars_is = bars_is.copy(); bars_is["fonte"] = "tick"; bars_is["janela"] = "IS"

    print("[cache] baixando OOS (tick + fallback M1) ...", flush=True)
    oos = carregar_oos_bars()
    b = oos["bars_mixed"].copy()
    fallback = {pd.Timestamp(d).date() if not hasattr(d, "date") else d
                for d in oos["dias_m1_fallback"]}
    b["fonte"] = ["m1_fallback" if ts.date() in fallback else "tick" for ts in b.index]
    b["janela"] = "OOS"

    todo = pd.concat([bars_is, b]).sort_index()
    # `dia` como COLUNA (nao so' no indice): quem paraleliza por pregao filtra
    # vetorizado (`df.dia.isin(...)`) em vez de iterar 4M timestamps em Python
    # -- na 1a versao do runner paralelo esse comprehension era o gargalo, e
    # rodava uma vez por TAREFA.
    todo["dia"] = todo.index.date
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    todo.to_parquet(DESTINO)
    dt = time.perf_counter() - t0
    print(f"\n[cache] {len(todo):,} barras gravadas em {DESTINO}")
    print(f"[cache] IS {len(bars_is):,} ({len(dias_is)} pregoes) | "
          f"OOS {len(b):,} ({len(oos['dias_oos'])} pregoes, "
          f"{len(oos['dias_m1_fallback'])} em fallback M1)")
    print(f"[cache] colunas: {list(todo.columns)}")
    print(f"[cache] {dt/60:.1f} min -- esse custo nao se paga de novo")


if __name__ == "__main__":
    main()
