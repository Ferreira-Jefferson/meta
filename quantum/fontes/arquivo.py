"""Guarda de arquivos brutos: download com cache + manifesto.

Todo arquivo que entra no Quantum passa por aqui e fica em
`dados/brutos/<fonte>/<grupo>/<nome>`, sem edição. O `manifesto.csv` registra de
onde veio, quando foi coletado, tamanho e sha256 — é o que permite responder
"este número saiu de qual arquivo, baixado quando?" e reprocessar tudo do zero.
"""
from __future__ import annotations

import csv
import hashlib
import threading
import time
from datetime import datetime
from pathlib import Path

import requests

from .. import config

UA = {"User-Agent": "quantum-research/0.1 (uso pessoal; dados publicos)"}
_trava = threading.Lock()
CAMPOS = ("caminho", "fonte", "url", "coletado_em", "bytes", "sha256")


def caminho(fonte: str, grupo: str, nome: str) -> Path:
    p = config.BRUTOS / fonte / grupo / nome
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def registrar(p: Path, fonte: str, url: str) -> None:
    """Acrescenta (ou atualiza) a linha do arquivo no manifesto."""
    rel = p.relative_to(config.DADOS).as_posix()
    linha = {"caminho": rel, "fonte": fonte, "url": url,
             "coletado_em": datetime.now().isoformat(timespec="seconds"),
             "bytes": p.stat().st_size, "sha256": _sha256(p)}
    with _trava:
        linhas = []
        if config.MANIFESTO.exists():
            with open(config.MANIFESTO, newline="", encoding="utf-8") as f:
                linhas = [r for r in csv.DictReader(f) if r["caminho"] != rel]
        linhas.append(linha)
        linhas.sort(key=lambda r: r["caminho"])
        with open(config.MANIFESTO, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CAMPOS)
            w.writeheader()
            w.writerows(linhas)


def baixar(url: str, destino: Path, fonte: str, max_idade_h: float | None = None) -> Path | None:
    """Baixa `url` para `destino` (se não existir ou estiver velho). None se 404.

    `max_idade_h=None` congela o arquivo: período fechado não muda mais.
    Em falha de rede, fica com a cópia que já existe em vez de quebrar a rodada.
    """
    if destino.exists() and destino.stat().st_size > 0:
        idade_h = (time.time() - destino.stat().st_mtime) / 3600
        if max_idade_h is None or idade_h < max_idade_h:
            return destino
    for tentativa in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=180)
            if r.status_code == 404:
                return destino if destino.exists() else None
            r.raise_for_status()
            tmp = destino.with_suffix(destino.suffix + ".tmp")
            tmp.write_bytes(r.content)
            tmp.replace(destino)
            registrar(destino, fonte, url)
            return destino
        except requests.RequestException:
            if tentativa == 2:
                if destino.exists():
                    return destino
                raise
            time.sleep(3 * (tentativa + 1))
    return None


def salvar_bytes(conteudo: bytes, destino: Path, fonte: str, url: str) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    tmp.write_bytes(conteudo)
    tmp.replace(destino)
    registrar(destino, fonte, url)
    return destino


def registrar_existentes(fonte: str, base_url_por_arquivo) -> int:
    """Registra no manifesto arquivos já presentes em brutos/<fonte> (ex.: migração)."""
    n = 0
    conhecidos = set()
    if config.MANIFESTO.exists():
        with open(config.MANIFESTO, newline="", encoding="utf-8") as f:
            conhecidos = {r["caminho"] for r in csv.DictReader(f)}
    for p in sorted((config.BRUTOS / fonte).rglob("*")):
        if p.is_file() and not p.name.endswith(".tmp"):
            if p.relative_to(config.DADOS).as_posix() not in conhecidos:
                registrar(p, fonte, base_url_por_arquivo(p))
                n += 1
    return n
