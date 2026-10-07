"""Compara os relatorios do Testador da bateria do WinMaestro (mt5/testes/resultados/*.htm).

Por robo:
  A_xx     EA avulso (referencia)
  M_xx     WinMaestro com so' ele ligado      -> deve repetir o avulso
  M_TODOS  WinMaestro com os 5, deals filtrados pelo comentario "MAE|<sigla>|..."
           -> cada robo deve repetir o M_xx dele
Resultado por robo = fluxo de caixa dos deals dele (vende - compra) x R$0,20 x contratos,
sem custo (os robos zeram todo dia, entao o fluxo fechado e' o P&L). Em NETTING o "Lucro"
do relatorio e' da posicao liquida, nao do robo -- por isso o fluxo.

Uso: python mt5/testes/compara.py
"""
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RES = AQUI / "resultados"
PONTO = 0.20
SIGLAS = ["GB", "CM", "DM", "RE", "C1"]
NOMES = {"GB": "WinGapBarra1", "CM": "WinCincoMedias", "DM": "WinDeslocamentoMatinal",
         "RE": "WinRetanguloEma34", "C1": "Win_c1"}
# Referencia ja' medida (roteiro, sem custo, 13/08-30/09). GB nao tinha.
ESPERADO = {"C1": (3, 5), "CM": (23, 500), "RE": (5, 221), "DM": (11, 55)}

COLS = {  # nome canonico -> rotulos possiveis (EN / PT-BR)
    "hora": ("time", "horário", "horario", "hora"),
    "tipo": ("type", "tipo"),
    "dir": ("direction", "direção", "direcao", "entrada/saída"),
    "vol": ("volume",),
    "preco": ("price", "preço", "preco"),
    "saldo": ("balance", "saldo"),
    "coment": ("comment", "comentário", "comentario"),
}


class _Linhas(HTMLParser):
    def __init__(self):
        super().__init__()
        self.linhas, self._lin, self._cel, self._em = [], None, None, False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._lin = []
        elif tag in ("td", "th") and self._lin is not None:
            self._cel, self._em = [], True

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._em:
            self._lin.append(" ".join("".join(self._cel).split()))
            self._em = False
        elif tag == "tr" and self._lin is not None:
            self.linhas.append(self._lin)
            self._lin = None

    def handle_data(self, d):
        if self._em:
            self._cel.append(d)


def _ler(p):
    b = p.read_bytes()
    txt = b.decode("utf-16") if b[:2] in (b"\xff\xfe", b"\xfe\xff") else b.decode("utf-8", "replace")
    h = _Linhas()
    h.feed(txt)
    return h.linhas


def _num(s):
    s = s.replace("\xa0", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def deals(p):
    """Lista de dicts dos deals do relatorio (sem a linha de deposito)."""
    linhas = _ler(p)
    for i, lin in enumerate(linhas):
        baixo = [c.lower() for c in lin]
        if any(c in COLS["saldo"] for c in baixo) and any(c in COLS["dir"] for c in baixo):
            idx = {}
            for k, rot in COLS.items():
                for j, c in enumerate(baixo):
                    if c in rot:
                        idx[k] = j
                        break
            out = []
            for l in linhas[i + 1:]:
                if len(l) != len(lin):
                    if out:
                        break
                    continue
                tipo = l[idx["tipo"]].lower()
                if tipo not in ("buy", "sell", "compra", "venda", "comprar", "vender"):
                    continue
                out.append({
                    "hora": l[idx["hora"]],
                    "lado": 1 if tipo in ("buy", "compra", "comprar") else -1,
                    "dir": l[idx["dir"]].lower(),
                    "vol": _num(l[idx["vol"]]) or 0.0,
                    "preco": _num(l[idx["preco"]]) or 0.0,
                    "coment": l[idx["coment"]] if "coment" in idx else "",
                })
            # O relatorio lista por ticket, nao por hora: no Maestro o stop (S) nasce antes
            # da entrada (E) e aparece primeiro. Ordena por hora para reconstruir a posicao.
            return sorted(out, key=lambda d: d["hora"])
    raise ValueError(f"tabela de deals nao encontrada em {p.name}")


def _robo(c):
    m = re.match(r"MAE\|([A-Z0-9]+)\|", c or "")
    return m.group(1) if m else None


def resumo(ds):
    caixa = sum(-d["lado"] * d["vol"] * d["preco"] for d in ds) * PONTO
    pos = maxpos = 0.0
    entradas = []
    for d in ds:
        antes = pos
        pos += d["lado"] * d["vol"]
        maxpos = max(maxpos, abs(pos))
        if abs(pos) > abs(antes):
            entradas.append((d["hora"][:16], d["lado"]))
    return {"ops": len(entradas), "rs": caixa, "maxpos": maxpos, "entradas": entradas, "aberta": pos}


def _coincide(a, b):
    sa, sb = set(a), set(b)
    return len(sa & sb), len(sa - sb), len(sb - sa)


def main():
    if not RES.exists():
        sys.exit("sem resultados: rode rodar_testes.ps1 antes")
    rel = {p.stem: p for p in RES.glob("*.htm")}
    todos = None
    if "M_TODOS" in rel:
        dt = deals(rel["M_TODOS"])
        todos = {s: [d for d in dt if _robo(d["coment"]) == s] for s in SIGLAS}
        sem_dono = [d for d in dt if _robo(d["coment"]) is None]
        rt = resumo(dt)
    print(f"{'robo':24} {'avulso':>14} {'maestro so':>14} {'maestro 5':>14} {'esperado':>10}  entradas iguais")
    for s in SIGLAS:
        r = {}
        for k in ("A", "M"):
            n = f"{k}_{s}"
            if n in rel:
                r[k] = resumo([d for d in deals(rel[n]) if k == "A" or _robo(d["coment"]) in (s, None)])
        if todos is not None:
            r["T"] = resumo(todos[s])
        cel = lambda k: f"{r[k]['ops']:>3} {r[k]['rs']:>+9.0f}" if k in r else f"{'-':>13}"
        esp = ESPERADO.get(s)
        esp = f"{esp[0]:>3} {esp[1]:>+5}" if esp else "-"
        cmp = []
        if "A" in r and "M" in r:
            cmp.append("A×M %d/%d/%d" % _coincide(r["A"]["entradas"], r["M"]["entradas"]))
        if "M" in r and "T" in r:
            cmp.append("M×5 %d/%d/%d" % _coincide(r["M"]["entradas"], r["T"]["entradas"]))
        print(f"{NOMES[s]:24} {cel('A'):>14} {cel('M'):>14} {cel('T'):>14} {esp:>10}  {'  '.join(cmp)}")
        for k in r:
            if r[k]["aberta"]:
                print(f"   ! {k}_{s}: terminou com posicao aberta {r[k]['aberta']:+.0f}")
    print("(ops e R$ sem custo; 'entradas iguais' = em comum / so' na 1a / so' na 2a, por minuto e lado)")
    if todos is not None:
        print(f"\nM_TODOS: posicao liquida maxima {rt['maxpos']:.0f} contratos; resultado da conta {rt['rs']:+.0f}; "
              f"deals sem robo no comentario: {len(sem_dono)}")


if __name__ == "__main__":
    main()
