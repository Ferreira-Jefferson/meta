"""Servidor local do replay de ticks reais do WinDeslocamentoMatinal.mq5. Serve o HTML de prints e executa o replay quando o botao da
pagina e' clicado.

Uso (na raiz do projeto):   .\\.venv\\Scripts\\python.exe scripts/daytrade/win_deslocamento_replay_server.py
Depois abra http://127.0.0.1:8766/   (a porta pode mudar com --porta)

Precisa do terminal do MetaTrader 5 aberto (baixa os ticks dos dias que ainda nao estao em data/cache_win_ticks).
Escuta so' em 127.0.0.1. Um replay por vez.
"""
import argparse, json, sys, threading, time, traceback, uuid
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import win_deslocamento_replay_ticks as rp

ROOT = Path(__file__).resolve().parents[2]
PASTA = ROOT / ".claude" / "artifacts" / "win_deslocamento_matinal"
JOBS: dict = {}
LOCK = threading.Lock()


def _tipar(k, v):
    """Converte o valor recebido para o tipo do padrao; bool aceita true/false/1/0/'sim'/'nao'."""
    t = type(rp.PARAMS_PADRAO[k])
    if t is bool:
        if isinstance(v, str):
            x = v.strip().lower()
            if x in ("true", "1", "sim", "on"): return True
            if x in ("false", "0", "nao", "não", "off", ""): return False
            raise ValueError(f"valor booleano invalido para {k}: {v!r}")
        return bool(v)
    return t(v)


def _executar(jid, req):
    job = JOBS[jid]
    try:
        ini, fim = date.fromisoformat(req["inicio"]), date.fromisoformat(req["fim"])
        if fim < ini:
            raise ValueError("periodo invalido (fim deve ser >= inicio)")
        params = {k: _tipar(k, v) for k, v in (req.get("params") or {}).items() if k in rp.PARAMS_PADRAO}
        def prog(k, n, msg):
            job.update(progresso=k / max(n, 1), mensagem=msg)
        job["resultado"] = rp.replay(ini, fim, float(req.get("latencia_s", 0)), req.get("modo", "fixa"), params, req.get("ativo", "WINV26"), prog)
        job["estado"] = "pronto"
    except Exception as e:  # o erro vai para a pagina
        job.update(estado="erro", erro=f"{type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        job["fim_ts"] = time.time()


class H(BaseHTTPRequestHandler):
    def _cab(self, code=200, tipo="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", tipo)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _json(self, obj, code=200):
        corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._cab(code); self.wfile.write(corpo)

    def do_OPTIONS(self):
        self._cab(204)

    def do_GET(self):
        rota = self.path.split("?")[0]
        if rota == "/api/ping":
            return self._json({"ok": True, "padrao": rp.PARAMS_PADRAO})
        if rota.startswith("/api/replay/"):
            job = JOBS.get(rota.rsplit("/", 1)[1])
            if job is None:
                return self._json({"erro": "job desconhecido"}, 404)
            return self._json({k: v for k, v in job.items() if k != "fim_ts"})
        alvo = PASTA / ("index.html" if rota in ("/", "") else rota.lstrip("/"))
        if alvo.is_file() and PASTA in alvo.resolve().parents:
            tipo = "text/html; charset=utf-8" if alvo.suffix == ".html" else "application/javascript" if alvo.suffix == ".js" else "application/json"
            self._cab(200, tipo); self.wfile.write(alvo.read_bytes())
        else:
            self._json({"erro": "nao encontrado"}, 404)

    def do_POST(self):
        if self.path != "/api/replay":
            return self._json({"erro": "nao encontrado"}, 404)
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except ValueError:
            return self._json({"erro": "JSON invalido"}, 400)
        with LOCK:
            if any(j["estado"] == "rodando" for j in JOBS.values()):
                return self._json({"erro": "ja' ha um replay rodando; espere terminar"}, 409)
            jid = uuid.uuid4().hex[:8]
            JOBS[jid] = dict(estado="rodando", progresso=0.0, mensagem="iniciando")
        threading.Thread(target=_executar, args=(jid, req), daemon=True).start()
        self._json({"id": jid})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--porta", type=int, default=8766)
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.porta), H)
    print(f"Replay de ticks reais pronto: http://127.0.0.1:{a.porta}/   (Ctrl+C para parar)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
