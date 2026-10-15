"""Linha de comando do Quantum.

  python -m quantum atualizar                 # todas as fontes + rodada de estudos
  python -m quantum atualizar --sem-estudos   # só os dados
  python -m quantum fonte yahoo               # baixa novos arquivos de UMA fonte
  python -m quantum estudar [--estrategias dy3a,momento] [--sorteios 200] [--n 100]
  python -m quantum servir [--porta 8100]     # painel web
"""
from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="quantum")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("atualizar")
    a.add_argument("--sem-estudos", action="store_true")
    f = sub.add_parser("fonte")
    f.add_argument("chave")
    e = sub.add_parser("estudar")
    e.add_argument("--estrategias", default="")
    e.add_argument("--sorteios", type=int, default=None)
    e.add_argument("--n", default="", help="fixa o nº de ações (ex.: 100 ou 50,100); padrão = grade 5..30")
    s = sub.add_parser("servir")
    s.add_argument("--porta", type=int, default=8100)
    s.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args(argv)

    def p(msg):
        print(msg, flush=True)

    if args.cmd == "atualizar":
        from . import pipeline
        pipeline.atualizar_tudo(estudar=not args.sem_estudos, progresso=p)
    elif args.cmd == "fonte":
        from . import pipeline
        if args.chave not in pipeline.ETAPAS:
            p(f"fonte desconhecida; use uma de: {', '.join(pipeline.ETAPAS)}")
            return 2
        return 0 if pipeline.atualizar_fonte(args.chave, p) == "ok" else 1
    elif args.cmd == "estudar":
        from . import estudos
        chaves = [c for c in args.estrategias.split(",") if c] or None
        grade_n = tuple(int(x) for x in args.n.split(",") if x) or None
        estudos.rodada(chaves=chaves, sorteios=args.sorteios, progresso=p, grade_n=grade_n)
    elif args.cmd == "servir":
        import uvicorn
        uvicorn.run("quantum.web.app:app", host=args.host, port=args.porta, reload=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
