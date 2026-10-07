"""Servidor do replay para a pagina win_c1 (mesmo motor de win_replay_server.py, serve .claude/artifacts/win_c1).
Uso (raiz do projeto):  .\\.venv\\Scripts\\python.exe scripts/daytrade/win_c1_server.py     ->  http://127.0.0.1:8765/
Precisa do terminal do MetaTrader 5 aberto. Nao rodar junto com win_replay_server.py (mesma porta)."""
import argparse, sys
from http.server import ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import win_replay_server as s

s.PASTA = s.ROOT / ".claude" / "artifacts" / "win_c1"
ap = argparse.ArgumentParser()
ap.add_argument("--porta", type=int, default=8765)
a = ap.parse_args()
srv = ThreadingHTTPServer(("127.0.0.1", a.porta), s.H)
print(f"Replay C1 pronto: http://127.0.0.1:{a.porta}/   (Ctrl+C para parar)", flush=True)
try:
    srv.serve_forever()
except KeyboardInterrupt:
    pass
