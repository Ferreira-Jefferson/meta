"""IS (2021-10-01..2024-12-31) do win_deslocamento_matinal: grade de 12 celulas x P0/P1/P2, corrida NOMINAL.
Uso: python -u run_is.py [volume]   (ablacao 'volume' = mesma grade com escala_volume=True)
<=3 workers (RAM), cada unidade imprime a linha assim que termina."""
from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import comum as c  # noqa: E402

SAIDA = HERE / "saidas"


def main() -> None:
    volume = len(sys.argv) > 1 and sys.argv[1] == "volume"
    SAIDA.mkdir(exist_ok=True)
    cels = c.celulas()
    if volume:
        cels = [dict(p, escala_volume=True) for p in cels]
    premissas = ["P2"] if volume else ["P0", "P1", "P2"]
    tarefas = [(p, q) for q in premissas for p in cels]
    print(f"IS {c.IS_INI.date()}..{c.IS_FIM.date()} WIN@ | {len(tarefas)} unidades | capital NOMINAL (diagnostico de edge)", flush=True)
    resultados = []
    cab_impresso = False
    with ProcessPoolExecutor(max_workers=3) as ex:
        fut = {ex.submit(c.unidade, "WIN@", str(c.IS_INI.date()), str(c.IS_FIM.date()), p, q, True): (p, q)
               for p, q in tarefas}
        for f in as_completed(fut):
            r = f.result()
            if not cab_impresso:
                print(r["cab"], flush=True)
                cab_impresso = True
            print(r["texto"], flush=True)
            resultados.append(r)
    nome = "is_volume" if volume else "is_grade"
    (SAIDA / f"{nome}.json").write_text(json.dumps(resultados, default=str), encoding="utf-8")
    print("salvo", SAIDA / f"{nome}.json", flush=True)


if __name__ == "__main__":
    main()
