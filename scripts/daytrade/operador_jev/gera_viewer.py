"""Gera viewer.html autocontido a partir de sessoes/*.json (abre com duplo clique, sem servidor).

Uso: python gera_viewer.py [--sessoes sessoes] [--saida viewer.html] [--com-pacotes]
"""
import argparse
import json
from pathlib import Path

AQUI = Path(__file__).resolve().parent


def limpa(x):
    """NaN/inf viram null (JSON valido)."""
    if isinstance(x, float):
        return x if x == x and x not in (float("inf"), float("-inf")) else None
    if isinstance(x, dict):
        return {k: limpa(v) for k, v in x.items()}
    if isinstance(x, list):
        return [limpa(v) for v in x]
    return x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessoes", default=str(AQUI / "sessoes"))
    ap.add_argument("--saida", default=str(AQUI / "viewer.html"))
    ap.add_argument("--com-pacotes", action="store_true", help="embute o texto do pacote de cada decisao (arquivo maior)")
    a = ap.parse_args()
    pasta = Path(a.sessoes)
    sessoes = []
    for f in sorted(pasta.glob("2*.json")):
        s = json.loads(f.read_text(encoding="utf-8"))
        if not a.com_pacotes:
            for p in s["pontos"]:
                p.pop("pacote", None)
        sessoes.append(s)
    if not sessoes:
        raise SystemExit(f"nenhuma sessao em {pasta}")
    resumo = None
    rf = pasta / "_resumo.json"
    if rf.exists():
        resumo = json.loads(rf.read_text(encoding="utf-8"))
        resumo.get("nulo_aleatorio", {}).pop("amostra", None)
    dados = json.dumps(limpa(dict(sessoes=sessoes, resumo=resumo)), ensure_ascii=False, separators=(",", ":"), allow_nan=False, default=float)
    dados = dados.replace("</", "<\\/").replace("<!--", "<\\!--")
    html = (AQUI / "viewer_template.html").read_text(encoding="utf-8").replace("__DADOS__", dados)
    Path(a.saida).write_text(html, encoding="utf-8")
    print(f"{a.saida}: {len(sessoes)} dia(s), {len(html) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
