"""Migra o diario ao vivo da conta UNICA ("principal") para uma conta por
SLOT (`core.config.SLOTS`).

Por que existe
-------------
Ate 2026-08-21 a operacao ao vivo tinha uma conta so, chamada "principal",
com o nome fixado em `scripts/run_live.py`. Com dois robos simultaneos (day
trade e swing), o nome da conta passou a SER o id do slot — e' isso que da a
cada robo um caixa proprio, que era o pedido. A linha "principal" nao tem
mais quem a leia: nenhum runtime a monta, nenhuma rota a mostra.

O que faz
---------
1. Renomeia `principal` -> `swing` (o slot diario), PRESERVANDO tudo que
   aponta para ela por `account_id` (posicoes, intencoes, ordens, fills,
   patrimonio, eventos, saques, depositos) — o rename e' no campo `name`, a
   chave estrangeira nao muda. Se `swing` ja existir, nao mexe em nada e
   avisa: fundir duas contas nao e' migracao, e' invencao de contabilidade.
2. Zera o `cash`/`initial_capital` de conta de slot SEM NENHUM historico
   financeiro (zero fills, zero depositos, zero patrimonio gravado). O caixa
   passou a ser um LEDGER MANUAL digitado pelo dono (ver
   `dashboard/app.py::operacao_caixa`) porque o saldo do terminal MT5 nao
   acompanha o da corretora; um numero herdado de um `--capital` de linha de
   comando antigo nao e' o caixa de ninguem, e deixa-lo la faria o robo
   iniciar (piso de R$50) sobre dinheiro que nao existe. Conta COM historico
   nunca e' tocada.
3. Reporta o que encontrou e nao entendeu, em vez de adivinhar.

Uso:
    python scripts/migrate_live_slots.py            # so mostra o plano
    python scripts/migrate_live_slots.py --apply    # executa
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core.config import LIVE_DB_PATH, SLOTS  # noqa: E402
from journal import live_store as store  # noqa: E402

LEGACY_NAME = "principal"
LEGACY_TARGET_SLOT = "swing"


def _has_history(conn, account_id: int) -> dict[str, int]:
    """Quantas linhas financeiras existem por tabela. Um dicionario todo zero
    significa "conta nunca operou" — e' o que autoriza zerar o ledger."""
    contagens = {}
    for tabela in ("live_fills", "live_deposits", "live_equity", "live_withdrawals",
                   "live_positions", "live_orders", "live_intents"):
        if tabela == "live_fills":
            # `live_fills` nao tem `account_id` -- pendura em `live_orders`.
            sql = ("SELECT COUNT(*) FROM live_fills f JOIN live_orders o "
                   "ON o.id = f.order_id WHERE o.account_id = ?")
        else:
            sql = f"SELECT COUNT(*) FROM {tabela} WHERE account_id = ?"
        try:
            contagens[tabela] = int(conn.execute(sql, (account_id,)).fetchone()[0])
        except Exception:
            contagens[tabela] = 0
    return contagens


def migrate(db_path: Path, apply: bool) -> int:
    slot_ids = {s.id for s in SLOTS}
    acoes: list[str] = []

    with store.live_journal(db_path) as conn:
        contas = {r["name"]: dict(r) for r in
                  conn.execute("SELECT * FROM live_accounts").fetchall()}

        print(f"diario ao vivo: {db_path}")
        if not contas:
            print("  nenhuma conta — nada a migrar.")
            return 0
        for nome, c in contas.items():
            hist = _has_history(conn, c["id"])
            total = sum(hist.values())
            print(f"  conta {nome!r}: caixa R$ {c['cash']:.2f}, robo "
                  f"{c['investment_robot'] or '(nenhum)'}, "
                  f"{total} linha(s) de historico {hist if total else ''}")

        # (1) rename da conta legada
        if LEGACY_NAME in contas:
            if LEGACY_TARGET_SLOT in contas:
                print(f"\n  ATENCAO: existem AS DUAS contas ({LEGACY_NAME!r} e "
                      f"{LEGACY_TARGET_SLOT!r}). Nao renomeio: fundir duas contas nao e "
                      "migracao, e invencao de contabilidade. Decida qual fica e apague "
                      "a outra a mao, olhando o historico impresso acima.")
            else:
                acoes.append(f"renomear conta {LEGACY_NAME!r} -> {LEGACY_TARGET_SLOT!r}")
                if apply:
                    conn.execute("UPDATE live_accounts SET name = ? WHERE name = ?",
                                 (LEGACY_TARGET_SLOT, LEGACY_NAME))

        # (2) zerar ledger e robo de conta de slot sem historico
        for nome, c in contas.items():
            alvo = LEGACY_TARGET_SLOT if nome == LEGACY_NAME else nome
            if alvo not in slot_ids:
                continue
            hist = _has_history(conn, c["id"])
            if sum(hist.values()) > 0:
                continue  # conta com historico nunca e tocada
            if c["cash"] or c["initial_capital"]:
                acoes.append(
                    f"zerar ledger da conta {alvo!r} (caixa R$ {c['cash']:.2f} -> R$ 0,00) "
                    "— sem historico financeiro nenhum; o caixa real passa a ser digitado "
                    "no painel"
                )
                if apply:
                    conn.execute(
                        "UPDATE live_accounts SET cash = 0, initial_capital = 0 WHERE id = ?",
                        (c["id"],),
                    )
            # `investment_robot` de conta que nunca operou tambem e' lixo: o
            # painel trata robo gravado como "conta em operacao" e NUNCA troca
            # de robo sozinho (regra do dono, 2026-08-19) -- entao um robo
            # herdado de um teste antigo (ou ja aposentado do podio) ficaria
            # travado la para sempre, sem nenhuma decisao humana por tras.
            # Limpar devolve a escolha para o clique em "Iniciar operacao".
            if c["investment_robot"]:
                acoes.append(
                    f"limpar o robo gravado da conta {alvo!r} "
                    f"({c['investment_robot']!r}) — sem historico, a escolha volta "
                    "para o clique em 'Iniciar operacao'"
                )
                if apply:
                    conn.execute(
                        "UPDATE live_accounts SET investment_robot = '', "
                        "withdrawal_robot = '' WHERE id = ?",
                        (c["id"],),
                    )

        # (3) contas que nao sao slot nenhum
        for nome in contas:
            if nome != LEGACY_NAME and nome not in slot_ids:
                print(f"\n  conta {nome!r} nao corresponde a slot nenhum "
                      f"({', '.join(sorted(slot_ids))}) — deixada intacta, decida a mao.")

    print()
    if not acoes:
        print("nada a fazer: o diario ja esta no formato de slots.")
        return 0
    for a in acoes:
        print(("APLICADO: " if apply else "PLANEJADO: ") + a)
    if not apply:
        print("\nnada foi alterado. rode de novo com --apply para executar.")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=str(LIVE_DB_PATH), help="caminho do diario ao vivo")
    p.add_argument("--apply", action="store_true",
                   help="executa de verdade (sem isto, so mostra o plano)")
    args = p.parse_args()
    sys.exit(migrate(Path(args.db), apply=args.apply))


if __name__ == "__main__":
    main()
