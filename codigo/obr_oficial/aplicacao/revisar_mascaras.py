"""Executa o painel local de revisao das mascaras candidatas."""

from __future__ import annotations

import argparse
from pathlib import Path

from waitress import serve

from obr_oficial.nucleo.configuracao import raiz_projeto
from obr_oficial.painel.revisao_mascaras import (
    RepositorioRevisaoMascaras,
    criar_painel_revisao,
)


def main(argumentos: list[str] | None = None) -> int:
    raiz = raiz_projeto()
    parser = argparse.ArgumentParser(description="Revisao humana das pre-anotacoes da Fase 2")
    parser.add_argument("--brutos", type=Path, default=raiz / "dados" / "brutos")
    parser.add_argument(
        "--candidatas",
        type=Path,
        default=raiz / "dados" / "rotulados" / "fase2_v1_classico_candidatas",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--porta", type=int, default=8091)
    opcoes = parser.parse_args(argumentos)
    repositorio = RepositorioRevisaoMascaras(opcoes.brutos, opcoes.candidatas)
    painel = criar_painel_revisao(repositorio)
    print(f"Revisao: http://{opcoes.host}:{opcoes.porta}", flush=True)
    serve(painel, host=opcoes.host, port=opcoes.porta, threads=4)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
