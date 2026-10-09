"""Cliente do endpoint de DECISOES do Jev (TypeSafe) no OpenRouter: POST /api/alpha/decisions.

Corpo: {"model", "state" (texto | objeto | array), "questions": {id: {type: noul|choice|score, instructions, criteria}}}.
Resposta: answers[id] = noul{noul} | choice{choice, probabilities, confidence} | score{score, legend, probabilities, confidence}.
A chave vem de .env e nunca e impressa nem gravada.
"""
from __future__ import annotations
import json
import random
import threading
import time
from pathlib import Path
import requests

RAIZ = Path(__file__).resolve().parents[3]
URL = "https://openrouter.ai/api/alpha/decisions"
MODELO_FIXO = "typesafe/jev-1.13-20260917"   # versao fixa (reprodutibilidade); "~typesafe/jev-latest" = ultima


def _chave():
    from dotenv import dotenv_values
    k = dotenv_values(RAIZ / ".env").get("OPENROUTER_API_KEY")
    if not k:
        raise RuntimeError("OPENROUTER_API_KEY ausente em .env")
    return k


def parse_resposta(j: dict) -> dict:
    """Resposta crua da API -> formato compacto {qid: valor}. Funcao pura (testavel sem rede).

    noul   -> float (P(sim))
    choice -> {"c": escolha, "p": {categoria: prob}, "k": confianca}
    score  -> {"s": valor esperado do nivel, "p": {nivel: prob}, "k": confianca}
    Respostas malformadas sao descartadas (a chave nao aparece).
    """
    out = {}
    for qid, a in ((j or {}).get("answers") or {}).items():
        try:
            t = a["type"]
            if t == "noul":
                out[qid] = float(a["noul"])
            elif t == "choice":
                pr = {str(c): float(p) for c, p in (a.get("probabilities") or {}).items()}
                out[qid] = {"c": str(a["choice"]), "p": pr, "k": float(a.get("confidence", 0.0))}
            elif t == "score":
                out[qid] = {"s": float(a["score"]), "p": {str(c): float(p) for c, p in (a.get("probabilities") or {}).items()},
                            "k": float(a.get("confidence", 0.0))}
        except Exception:
            continue
    return out


class CustoExcedido(Exception):
    pass


class Cliente:
    def __init__(self, modelo=MODELO_FIXO, max_custo=20.0, timeout=60, max_tentativas=8, max_simultaneas=16):
        self.modelo = modelo
        self.max_custo = max_custo
        self.timeout = timeout
        self.max_tentativas = max_tentativas
        self.custo = 0.0
        self.chamadas = 0
        self.falhas = 0
        self.rate_limit = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.modelos: dict[str, int] = {}
        self.lock = threading.Lock()
        self._k = _chave()
        self._s = threading.local()
        self.sem = threading.BoundedSemaphore(max_simultaneas)

    def _sessao(self):
        s = getattr(self._s, "s", None)
        if s is None:
            s = self._s.s = requests.Session()
        return s

    def decidir(self, estado, questions: dict):
        """Retorna (respostas_compactas|None, meta). Retry com backoff exponencial + jitter em 429/5xx/rede."""
        if self.custo >= self.max_custo:
            raise CustoExcedido(f"custo acumulado US$ {self.custo:.3f} >= teto {self.max_custo}")
        corpo = {"model": self.modelo, "state": estado, "questions": questions}
        meta = dict(modelo=None, custo=0.0, tempo=0.0, tokens_in=0, tokens_out=0, tentativas=0, falha=None)
        t0 = time.time()
        for tent in range(self.max_tentativas):
            meta["tentativas"] = tent + 1
            try:
                with self.sem:
                    r = self._sessao().post(URL, headers={"Authorization": "Bearer " + self._k}, json=corpo, timeout=self.timeout)
                if r.status_code == 429 or r.status_code >= 500:
                    with self.lock:
                        self.rate_limit += (r.status_code == 429)
                    raise RuntimeError(f"HTTP {r.status_code}")
                if r.status_code >= 400:
                    meta["falha"] = f"HTTP {r.status_code}: {r.content[:200].decode('utf-8', 'replace')}"
                    break  # erro de validacao/limite de tokens: repetir nao adianta
                j = json.loads(r.content.decode("utf-8"))
                u = j.get("usage") or {}
                resp = parse_resposta(j)
                with self.lock:
                    self.chamadas += 1
                    self.custo += float(u.get("cost") or 0)
                    self.tokens_in += u.get("input_tokens") or 0
                    self.tokens_out += u.get("output_tokens") or 0
                    m = j.get("model") or "?"
                    self.modelos[m] = self.modelos.get(m, 0) + 1
                meta.update(modelo=j.get("model"), custo=float(u.get("cost") or 0), tokens_in=u.get("input_tokens") or 0,
                            tokens_out=u.get("output_tokens") or 0, falha=None, tempo=time.time() - t0)
                if not resp:
                    meta["falha"] = "resposta sem answers validas"
                    return None, meta
                return resp, meta
            except Exception as e:
                meta["falha"] = f"{type(e).__name__}: {str(e)[:150]}"
                time.sleep(min(30.0, (2 ** tent) * 0.5) * (0.5 + random.random()))
        with self.lock:
            self.falhas += 1
        meta["tempo"] = time.time() - t0
        return None, meta
