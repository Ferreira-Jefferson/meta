# -*- coding: utf-8 -*-
"""Runner: `python roda.py <script_antigo.py>` com ORB_MODO=antes|depois.
Importa o script antigo como modulo (nome = stem) e chama `main()`. O patch roda no
topo, entao os workers do spawn (que reexecutam este arquivo como __mp_main__) o herdam."""
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import patch_semleilao  # noqa: E402
patch_semleilao.aplica()


def _importa(caminho: Path):
    sys.path.insert(0, str(caminho.parent))
    spec = importlib.util.spec_from_file_location(caminho.stem, caminho)
    m = importlib.util.module_from_spec(spec)
    sys.modules[caminho.stem] = m
    spec.loader.exec_module(m)
    return m


if __name__ == "__main__":
    alvo = Path(sys.argv[1]).resolve()
    _importa(alvo).main()
