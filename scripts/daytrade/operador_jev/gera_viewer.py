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
    ap.add_argument("--max-dias", type=int, default=60, help="maximo de dias embutidos (amostra espacada entre os dias com operacao + alguns sem)")
    ap.add_argument("--modulo-perguntas", default="perguntas_jev", help="modulo com MERCADO/GESTAO (ex.: perguntas_v2, em experimento_dia_positivo/)")
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
    if len(sessoes) > a.max_dias:
        com = [s for s in sessoes if s["trades"]]
        sem = [s for s in sessoes if not s["trades"]]
        pega = lambda L, n: [L[int(i * len(L) / n)] for i in range(n)] if n < len(L) else L
        sessoes = sorted(pega(com, int(a.max_dias * 0.85)) + pega(sem, a.max_dias - int(a.max_dias * 0.85)), key=lambda s: s["data"])
    perguntas = {}
    try:
        import sys
        sys.path.insert(0, str(AQUI))
        sys.path.insert(0, str(AQUI / "experimento_dia_positivo"))
        import importlib
        mod = importlib.import_module(a.modulo_perguntas)
        MERCADO, GESTAO = mod.MERCADO, mod.GESTAO
        perguntas = {q[0]: dict(ref=q[2], tx=q[3]) for q in MERCADO + GESTAO}
    except Exception:
        pass
    for s in sessoes:
        s.pop("estado_exemplo", None)
    resumo = None
    rf = pasta / "_resumo.json"
    if rf.exists():
        resumo = json.loads(rf.read_text(encoding="utf-8"))
        resumo.get("nulo_aleatorio", {}).pop("amostra", None)
        resumo["modelos"] = resumo.get("modelos") or {}
    dados = json.dumps(limpa(dict(sessoes=sessoes, resumo=resumo, perguntas=perguntas)), ensure_ascii=False, separators=(",", ":"), allow_nan=False, default=float)
    dados = dados.replace("</", "<\\/").replace("<!--", "<\\!--")
    html = (AQUI / "viewer_template.html").read_text(encoding="utf-8").replace("__DADOS__", dados)
    Path(a.saida).write_text(html, encoding="utf-8")
    print(f"{a.saida}: {len(sessoes)} dia(s), {len(html) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
