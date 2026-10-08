"""Gera o HTML da grade semanal a partir de medicoes.json.

Uso: .venv/Scripts/python.exe scripts/swing_lab/semanal_mmes_video_html.py
Saida: scripts/swing_lab/semanal_mmes_video/grade_semanal_b3.html
"""
from __future__ import annotations

import json
from pathlib import Path

PASTA = Path(__file__).resolve().parent / "semanal_mmes_video"


def main() -> None:
    m = json.loads((PASTA / "medicoes.json").read_text(encoding="utf-8"))
    dados = {k: m[k] for k in ("gerado", "premissas", "ativos", "agregados")}  # sem "erros": a pagina so mostra o que a Rico negocia
    from semanal_mmes_video_2026_10_08 import LIQ_MIN_MT5  # medicoes.json antigo nao gravava o piso
    dados["premissas"].setdefault("liq_min_mt5", LIQ_MIN_MT5)
    html = TEMPLATE.replace("/*__DADOS__*/null", json.dumps(dados, ensure_ascii=False))
    out = PASTA / "grade_semanal_b3.html"
    out.write_text(html, encoding="utf-8")
    print(out, f"{len(html) / 1e6:.2f} MB")


TEMPLATE = (Path(__file__).with_name("semanal_mmes_video_template.html")).read_text(encoding="utf-8")

if __name__ == "__main__":
    main()
