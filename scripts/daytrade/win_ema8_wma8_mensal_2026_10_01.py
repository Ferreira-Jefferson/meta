"""Uma rodada mensal da estrategia WIN (WMA 34 + SMMA 34) (WIN, execucao em M1) -> acrescenta linhas na tabela do HTML.

Fluxo de trabalho do dono: AJUSTAR num mes, TESTAR em outro, repetir. Cada chamada
mede UM mes com UMA combinacao stop/alvo e grava a linha em
.claude/artifacts/win_ema8_wma8_2026-09/dados_mensal.js (mesma mes+combo+papel = substitui).
So' o mes pedido e' simulado; o historico anterior entra apenas como aquecimento
das medias.

Uso: python scripts/daytrade/win_ema8_wma8_mensal_2026_10_01.py AAAA-MM ajuste|teste STOP ALVO [troca] [limpa|roxa] [pN] [cruz=N] [folga=F] [gap=G]   (pN = periodo das medias, ex.: p34; padrao 34)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import win_ema8_wma8_sim_m1 as sim  # noqa: E402

MES, PAPEL = sys.argv[1], sys.argv[2]
STOP, ALVO = float(sys.argv[3]), float(sys.argv[4])
TROCA = "troca" in sys.argv[5:]
PERIODO = next((int(a[1:]) for a in sys.argv[5:] if a[0] == "p" and a[1:].isdigit()), sim.PERIODO)
ROXA = "roxa" in sys.argv[5:]  # so a WMA (roxa), vela inteira fora dela
FILTROS = {a.split("=")[0]: float(a.split("=")[1]) for a in sys.argv[5:] if "=" in a}  # cruz (velas), folga e gap (pontos)
FILTRO_TXT = " ".join(f"{k}≤{v:g}" for k, v in FILTROS.items())
LIMPA = "limpa" in sys.argv[5:] or ROXA  # vela inteira fora das medias, sem tocar nelas
N_CONTROLE = 5
OUT = sim.ROOT / ".claude" / "artifacts" / "win_ema8_wma8_2026-09"
OUT.mkdir(parents=True, exist_ok=True)


def metricas(df: pd.DataFrame) -> dict:
    rs = df.rs.to_numpy()
    eq = np.cumsum(rs)
    dd = float((eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min())
    dia = df.groupby("dia").rs.sum()
    gm, pm = rs[rs > 0].mean(), -rs[rs <= 0].mean()
    return {"trades": len(rs), "liquido": round(float(rs.sum()), 2), "maxdd": round(dd, 2),
            "acerto": round(float((rs > 0).mean() * 100), 1), "breakeven": round(float(pm / (gm + pm) * 100), 1),
            "rs_trade": round(float(rs.mean()), 2), "rs_dia": round(float(dia.mean()), 2),
            "dias": int(len(dia)), "dias_neg": int((dia < 0).sum()), "pior_dia": round(float(dia.min()), 2),
            "saidas": {k: int(v) for k, v in df.mot.value_counts().items()}}


def main() -> None:
    m1 = sim.preparar(MES, limpa=LIMPA, periodo=PERIODO, so_roxa=ROXA,
                      cruz=int(FILTROS["cruz"]) if "cruz" in FILTROS else None,
                      folga=FILTROS.get("folga"), gap=FILTROS.get("gap"))
    if m1.empty:
        raise SystemExit(f"sem dados M1 em {MES}")
    df = sim.simular(m1, STOP, ALVO, troca=TROCA)
    mt = metricas(df)
    # controle: mesma saida, direcao sorteada. Se o sinal nao bate o sorteio, nao ha informacao nele.
    rng = np.random.default_rng(12345)
    ctrl = []
    for _ in range(N_CONTROLE):
        r = sim.simular(m1, STOP, ALVO, troca=False, sinal_override=rng.choice([-1, 1], size=len(m1)))
        ctrl.append(float(r.rs.mean()))
    mt["controle_rs_trade_min"], mt["controle_rs_trade_max"] = round(min(ctrl), 2), round(max(ctrl), 2)
    mt["controle_rs_trade_med"] = round(float(np.mean(ctrl)), 2)

    linha = {"mes": MES, "papel": PAPEL, "stop": STOP, "alvo": ALVO, "entrada": "troca" if TROCA else "sempre", "regra": "roxa" if ROXA else ("limpa" if LIMPA else "fechamento"), "periodo": PERIODO, "filtro": FILTRO_TXT,
             "rodada": datetime.now().strftime("%d/%m %H:%M"), **mt}
    arq = OUT / "dados.json"
    linhas = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else []
    chave = lambda x: (x["mes"], x["papel"], x["stop"], x["alvo"], x["entrada"], x.get("regra", "fechamento"), x.get("periodo", 8), x.get("filtro", ""))  # noqa: E731
    linhas = [x for x in linhas if chave(x) != chave(linha)] + [linha]
    arq.write_text(json.dumps(linhas, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "dados_mensal.js").write_text("const LINHAS = " + json.dumps(linhas, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(json.dumps(linha, indent=1), flush=True)


if __name__ == "__main__":
    main()
