"""Estado ATUAL da estrategia semanal v4 para cada papel, injetado na pagina da grade.

v4 (ver VERSOES_SEMANAL.md): grande (mediana do financeiro dos 63 pregoes
>= R$100 mi) + forca (razao papel/IBOV semanal acima da MME21 dela) +
estrutura (ZigZag de 3 ATR semanais, 2 ultimos topos e fundos ascendentes);
sinal = recuo a MME9 com as tres MMEs semanais subindo, na ultima semana
fechada.

Le o diario do MT5 ate o ultimo pregao, que fica no conjunto de VALIDACAO:
leitura de estado para acompanhar, sem decisao de pesquisa, com o motivo no
log da trava.

Uso:
  .venv/Scripts/python.exe scripts/swing_lab/semanal_v4_estado.py --dados <medicoes.json | pagina.html> [--saida X.html]
`--dados` aceita o medicoes.json da grade ou uma pagina ja gerada (o bloco
`const D = ...`), porque o medicoes.json depende do arquivo .prt do Profit.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base_mt5 as base  # noqa: E402
import semanal_mmes_video_2026_10_08 as setup  # noqa: E402
from semanal_estrutura_2026_10_08 import zigzag  # noqa: E402

MOTIVO = "estado atual da v4 para a pagina da grade semanal (acompanhamento, sem decisao de pesquisa)"
TEMPLATE = Path(__file__).with_name("semanal_mmes_video_template.html")


def semanal_fechada(d: pd.DataFrame) -> pd.DataFrame:
    w = setup.semanal(d)
    return w.iloc[:-1] if w.index[-1] > d.index[-1] else w


def estado_v4() -> tuple[str, dict[str, dict]]:
    ib = semanal_fechada(pd.read_parquet(base.PASTA / "IBOV.parquet")).close
    out, semana = {}, None
    for tk, _ in base.universo():
        d = base.carregar(tk, "validacao", autorizacao=MOTIVO)
        if len(d) < 300:
            continue
        w = semanal_fechada(d)
        e = setup.ema
        sig = setup.sinais(w)
        ratio = w.close / ib.reindex(w.index, method="ffill")
        fin = float((d.close * d.volume).iloc[-63:].median())
        v = dict(grande=fin >= 100e6, forca=bool(ratio.iloc[-1] > e(ratio, 21).iloc[-1]),
                 estrutura=bool(zigzag(w, setup.atr(w, 14), 3).iloc[-1]), sinal=bool(sig.recuo_media.iloc[-1]),
                 fin_mediana=fin)
        v["apta"] = v["grande"] and v["forca"] and v["estrutura"]
        out[tk] = v
        semana = str(w.index[-1].date())
    return semana, out


def carregar_dados(p: Path) -> dict:
    if p.suffix == ".json":
        m = json.loads(p.read_text(encoding="utf-8"))
        return {k: m[k] for k in ("gerado", "premissas", "ativos", "agregados")}
    linha = next(x for x in p.read_text(encoding="utf-8").splitlines() if x.startswith("const D = "))
    return json.loads(linha[len("const D = "):].rstrip().rstrip(";"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", type=Path, required=True)
    ap.add_argument("--saida", type=Path, default=Path(__file__).with_name("semanal_mmes_video") / "grade_semanal_b3.html")
    a = ap.parse_args()
    D = carregar_dados(a.dados)
    semana, est = estado_v4()
    for at in D["ativos"]:
        at["v4"] = est.get(at["ticker"])
    D["v4"] = {"semana": semana}
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DADOS__*/null", json.dumps(D, ensure_ascii=False))
    a.saida.parent.mkdir(parents=True, exist_ok=True)
    a.saida.write_text(html, encoding="utf-8")
    aptas = sorted(t for t, v in est.items() if v["apta"])
    print(f"semana {semana}: {len(aptas)} aptas, {sum(est[t]['sinal'] for t in aptas)} com sinal -> {a.saida}")


if __name__ == "__main__":
    main()
