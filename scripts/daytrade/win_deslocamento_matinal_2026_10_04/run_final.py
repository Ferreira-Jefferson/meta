"""OOS do WIN (UMA vez) e replicacao no WDO (IS e OOS, UMA vez), com a configuracao CONGELADA (CONGELADO.md).
Corrida NOMINAL (diagnostico de edge); a conferencia com capital real e' `confere_motor_real.py OOS`."""
from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import comum as c  # noqa: E402

CONGELADA = dict(desloc_min_atr=0.3, stop_atr=None, alvo_atr=None)
SAIDA = HERE / "saidas"


def main() -> None:
    SAIDA.mkdir(exist_ok=True)
    ini_o, fim_o = str(c.OOS_INI.date()), str(c.OOS_FIM.date())
    ini_i, fim_i = str(c.IS_INI.date()), str(c.IS_FIM.date())
    tarefas = [("WIN@", ini_o, fim_o, q) for q in ("P0", "P1", "P2")]
    tarefas += [("WDO@", ini_i, fim_i, q) for q in ("P0", "CAL", "P1", "P2")]
    tarefas += [("WDO@", ini_o, fim_o, q) for q in ("P0", "CAL", "P1", "P2")]
    print(f"config CONGELADA {c.nome_celula(CONGELADA)} | {len(tarefas)} unidades | capital NOMINAL", flush=True)
    res = []
    cab = False
    with ProcessPoolExecutor(max_workers=3) as ex:
        fut = {ex.submit(c.unidade, s, i, f, CONGELADA, q, True): (s, i, q) for s, i, f, q in tarefas}
        for f in as_completed(fut):
            r = f.result()
            s, i, q = fut[f]
            if not cab:
                print(r["cab"], flush=True)
                cab = True
            print(r["texto"].replace(c.nome_celula(CONGELADA), f"{s} {i[:4]}"), flush=True)
            r["janela_ini"] = i
            res.append(r)
    (SAIDA / "final.json").write_text(json.dumps(res, default=str), encoding="utf-8")
    print("salvo", SAIDA / "final.json", flush=True)


if __name__ == "__main__":
    main()
