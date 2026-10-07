"""Coloca (ou atualiza) o painel 'Replay com ticks reais' no index.html de prints do Win, sem criar teste novo.
Idempotente: o painel fica entre <!--REPLAY--> e <!--/REPLAY-->.
Uso: python win_replay_painel_injetar.py   (o gerador de prints tambem chama injetar() ao terminar)"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAINEL = Path(__file__).with_name("win_replay_painel.html")
INDEX = ROOT / ".claude" / "artifacts" / "win_setembro" / "index.html"


def injetar(index: Path = INDEX) -> bool:
    html = index.read_text(encoding="utf-8")
    html = re.sub(r"<!--REPLAY-->.*?<!--/REPLAY-->\n?", "", html, flags=re.S)
    if "</h1>" not in html:
        return False
    html = html.replace("</h1>", "</h1>\n" + PAINEL.read_text(encoding="utf-8"), 1)
    index.write_text(html, encoding="utf-8")
    return True


if __name__ == "__main__":
    print("painel", "injetado em" if injetar() else "NAO injetado (sem </h1>) em", INDEX)
