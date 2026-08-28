"""Executa o painel local de revisao das mascaras verdes."""

from __future__ import annotations

import argparse
from pathlib import Path

from waitress import serve

from obr_oficial.nucleo.configuracao import raiz_projeto
from obr_oficial.painel.revisao_verde import (
    RepositorioRevisaoVerde,
    criar_painel_revisao_verde,
)


def main(argumentos: list[str] | None = None) -> int:
    raiz = raiz_projeto()
    parser = argparse.ArgumentParser(description="Revisao humana das mascaras verdes")
    parser.add_argument(
        "--brutos",
        type=Path,
        default=raiz / "dados" / "brutos" / "verde",
    )
    parser.add_argument(
        "--candidatas",
        type=Path,
        default=raiz / "dados" / "rotulados" / "verde_v1_candidatas",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--porta", type=int, default=8094)
    opcoes = parser.parse_args(argumentos)
    repositorio = RepositorioRevisaoVerde(opcoes.brutos, opcoes.candidatas)
    painel = criar_painel_revisao_verde(repositorio)
    print(f"Revisao verde: http://{opcoes.host}:{opcoes.porta}", flush=True)
    serve(painel, host=opcoes.host, port=opcoes.porta, threads=4)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
