"""Cliente OpenRouter para o operador (Jev). A chave vem de .env e nunca e impressa/gravada."""
from __future__ import annotations
import json
import re
import threading
import time
from pathlib import Path
import requests

RAIZ = Path(__file__).resolve().parents[3]
URL = "https://openrouter.ai/api/v1/chat/completions"
PERGUNTAS = RAIZ / "PERGUNTAS_DE_OPERACAO.md"

INSTRUCOES = """# VOCE E UM OPERADOR DE WIN (mini-indice Bovespa)

Voce opera o mini-indice (WIN) sozinho, vela a vela. A cada vela M15 que fecha voce recebe um PACOTE DE MERCADO
(velas fechadas, contexto diario/H1, sua posicao, suas ordens e suas decisoes anteriores do dia) e devolve UMA decisao em JSON.
Um motor deterministico executa o que voce decide. Voce nao ve o futuro; as datas sao anonimas, mas os precos sao reais.

Regras do jogo (inegociaveis):
- Voce decide sozinho. Nao ha ninguem para consultar: nao responda com perguntas ao dono, decida.
- O documento acima (perguntas de operacao) e o seu cerebro. As perguntas sao ABERTAS de proposito. Varra o grafico, escolha as que
  importam NESTE momento e responda com evidencia que se aponta nos dados do pacote. "nao" e "indefinido" sao respostas validas. "Sem dado" e resposta valida.
- Ficar de fora e uma decisao valida e muitas vezes a melhor. Nao opere por obrigacao. Raciocine por conta propria, desconfie da primeira explicacao.
- NUNCA entre a mercado. Entrada = ordem LIMITADA (comprar_limite abaixo/igual ao ultimo fechamento; vender_limite acima/igual). Alvo = sempre ordem limitada.
- Todo trade TEM stop (obrigatorio). O stop sai a mercado no nivel. 'zerar' tambem sai a mercado e so existe como saida.
- Maximo 2 contratos, 1 posicao por vez. Tick = 5 pontos. Custo: 10 pts por contrato por operacao (ida+volta). 1 ponto = R$ 0,20 por contrato.
- A ordem limitada so enche se o preco passar 10 pts alem do seu preco (compra: minima <= preco-10; venda: maxima >= preco+10) numa vela M1 de uma vela M15 SEGUINTE,
  dentro da validade (1 a 4 velas M15). Ordem que nao enche expira; o preco pode nao voltar. Considere isso ao escolher o preco.
- Stop e alvo na mesma vela: o motor assume o stop. O motor zera tudo 5 min antes do fim do pregao.
- mover_stop so a favor da posicao (compra: sobe; venda: desce) e dentro do mercado (abaixo/acima do ultimo fechamento).
- Voce so ve velas FECHADAS. A decisao vale a partir da proxima vela.

Acoes (campo "acao"):
- ficar_fora: nenhuma ordem nova (cancela ordem pendente, se houver).
- manter: nao mexe em nada (posicao e/ou ordem pendente continuam como estao).
- comprar_limite / vender_limite: exigem preco, stop; alvo opcional (null = sem alvo); contratos 1 ou 2; validade_velas 1-4.
- mover_stop: exige novo_stop.
- zerar: sai a mercado da posicao aberta.
- cancelar_ordem: cancela a ordem pendente.

Formato da resposta: SOMENTE um objeto JSON, sem texto fora dele, com os campos:
{"acao": "...", "preco": numero|null, "stop": numero|null, "alvo": numero|null, "contratos": 1|2|null, "validade_velas": 1-4|null,
 "novo_stop": numero|null,
 "respostas": [{"id": "D2" ou "37" (numero da pergunta no documento), "tema": "2-4 palavras", "resposta": "sim"|"nao"|"indefinido", "porque": "1 linha com evidencia"}],
 "raciocinio": "ate ~5 linhas", "confianca": 0-100}
Em "respostas" inclua so as perguntas que voce considerou relevantes agora (tipicamente 3 a 8).
"""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "acao": {"type": "string", "enum": ["ficar_fora", "manter", "comprar_limite", "vender_limite", "mover_stop", "zerar", "cancelar_ordem"]},
        "preco": {"type": ["number", "null"]},
        "stop": {"type": ["number", "null"]},
        "alvo": {"type": ["number", "null"]},
        "contratos": {"type": ["integer", "null"]},
        "validade_velas": {"type": ["integer", "null"]},
        "novo_stop": {"type": ["number", "null"]},
        "respostas": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"id": {"type": "string"}, "tema": {"type": "string"},
                           "resposta": {"type": "string", "enum": ["sim", "nao", "indefinido"]},
                           "porque": {"type": "string"}},
            "required": ["id", "tema", "resposta", "porque"]}},
        "raciocinio": {"type": "string"},
        "confianca": {"type": "integer"},
    },
    "required": ["acao", "preco", "stop", "alvo", "contratos", "validade_velas", "novo_stop", "respostas", "raciocinio", "confianca"],
}
ACOES = SCHEMA["properties"]["acao"]["enum"]


def prompt_sistema() -> str:
    """Identico entre chamadas (cache do provedor)."""
    return PERGUNTAS.read_text(encoding="utf-8") + "\n\n---\n\n" + INSTRUCOES


def _chave():
    from dotenv import dotenv_values
    k = dotenv_values(RAIZ / ".env").get("OPENROUTER_API_KEY")
    if not k:
        raise RuntimeError("OPENROUTER_API_KEY ausente em .env")
    return k


def extrai_json(txt: str):
    txt = (txt or "").strip()
    try:
        return json.loads(txt)
    except Exception:
        pass
    txt2 = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip()
    try:
        return json.loads(txt2)
    except Exception:
        pass
    a, b = txt.find("{"), txt.rfind("}")
    if a >= 0 and b > a:
        try:
            return json.loads(txt[a:b + 1])
        except Exception:
            return None
    return None


def normaliza(j) -> dict | None:
    """Valida/repara. Devolve None se inutilizavel."""
    if not isinstance(j, dict):
        return None
    a = j.get("acao")
    if isinstance(a, str):
        a = a.strip().lower().replace(" ", "_")
    if a not in ACOES:
        return None
    out = dict(acao=a)
    for c in ("preco", "stop", "alvo", "novo_stop"):
        v = j.get(c)
        try:
            out[c] = float(v) if v is not None else None
        except Exception:
            out[c] = None
    for c in ("contratos", "validade_velas"):
        try:
            out[c] = int(j.get(c)) if j.get(c) is not None else None
        except Exception:
            out[c] = None
    rs = []
    for r in (j.get("respostas") or []):
        if isinstance(r, dict):
            resp = str(r.get("resposta", "indefinido")).lower().replace("ã", "a")
            resp = resp if resp in ("sim", "nao", "indefinido") else "indefinido"
            rs.append(dict(id=str(r.get("id", "?")), tema=str(r.get("tema", ""))[:60], resposta=resp, porque=str(r.get("porque", ""))[:300]))
    out["respostas"] = rs
    out["raciocinio"] = str(j.get("raciocinio", ""))[:1200]
    try:
        out["confianca"] = max(0, min(100, int(j.get("confianca", 0))))
    except Exception:
        out["confianca"] = 0
    return out


class CustoExcedido(Exception):
    pass


class Cliente:
    def __init__(self, modelo="typesafe/jev-router", max_custo=5.0, timeout=240):
        self.modelo = modelo
        self.max_custo = max_custo
        self.timeout = timeout
        self.custo = 0.0
        self.chamadas = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.tokens_cache = 0
        self.modelos: dict[str, int] = {}
        self.lock = threading.Lock()
        self.sistema = prompt_sistema()
        self.modo = "json_schema"  # degrada para json_object / texto se o provedor recusar
        self._k = _chave()

    def _post(self, msgs, modo):
        corpo = dict(model=self.modelo, messages=msgs)
        if modo == "json_schema":
            corpo["response_format"] = {"type": "json_schema", "json_schema": {"name": "decisao", "strict": True, "schema": SCHEMA}}
        elif modo == "json_object":
            corpo["response_format"] = {"type": "json_object"}
        return requests.post(URL, headers={"Authorization": "Bearer " + self._k}, json=corpo, timeout=self.timeout)

    def decidir(self, pacote: str):
        """Retorna (decisao|None, meta). Ate 2 tentativas de JSON valido; retry com backoff em erro de rede/HTTP."""
        if self.custo >= self.max_custo:
            raise CustoExcedido(f"custo acumulado US$ {self.custo:.3f} >= --max-custo-usd {self.max_custo}")
        msgs = [{"role": "system", "content": self.sistema}, {"role": "user", "content": pacote}]
        meta = dict(modelo=None, custo=0.0, tempo=0.0, tokens_in=0, tokens_out=0, tentativas=0, falha=None)
        t0 = time.time()
        for tent in range(2):
            j = None
            for rede in range(4):
                try:
                    r = self._post(msgs, self.modo)
                    if r.status_code in (400, 422) and self.modo != "texto":
                        self.modo = "json_object" if self.modo == "json_schema" else "texto"
                        continue
                    if r.status_code >= 400:
                        raise RuntimeError(f"HTTP {r.status_code}: {r.content[:200].decode('utf-8', 'replace')}")
                    j = json.loads(r.content.decode("utf-8"))
                    break
                except Exception as e:  # rede/timeout/HTTP
                    meta["falha"] = f"{type(e).__name__}: {str(e)[:200]}"
                    time.sleep(2 ** rede)
            meta["tentativas"] += 1
            if j is None:
                continue
            u = j.get("usage") or {}
            with self.lock:
                self.chamadas += 1
                self.custo += float(u.get("cost") or 0)
                self.tokens_in += u.get("prompt_tokens") or 0
                self.tokens_out += u.get("completion_tokens") or 0
                self.tokens_cache += (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
                m = j.get("model") or "?"
                self.modelos[m] = self.modelos.get(m, 0) + 1
            meta["modelo"] = j.get("model")
            meta["custo"] += float(u.get("cost") or 0)
            meta["tokens_in"] += u.get("prompt_tokens") or 0
            meta["tokens_out"] += u.get("completion_tokens") or 0
            try:
                txt = j["choices"][0]["message"]["content"]
            except Exception:
                txt = ""
            dec = normaliza(extrai_json(txt))
            if dec:
                meta["falha"] = None
                meta["tempo"] = time.time() - t0
                return dec, meta
            meta["falha"] = "resposta nao era JSON valido"
        meta["tempo"] = time.time() - t0
        meta["falha"] = (meta["falha"] or "falha") + " -> ficar_fora"
        return None, meta
