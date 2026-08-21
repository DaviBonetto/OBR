"""CLI da preparacao reproduzivel do dataset da linha."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obr_oficial.dados import PreparadorDataset, carregar_configuracao_dataset


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Valida, filtra e divide sessoes brutas sem alterar imagens.",
    )
    parser.add_argument("--entrada", type=Path, default=Path("dados/brutos"))
    parser.add_argument("--saida", type=Path, default=Path("dados/processados/fase2_v1"))
    parser.add_argument(
        "--configuracao",
        type=Path,
        default=Path("configuracoes/dataset_fase2.toml"),
    )
    return parser


def main() -> None:
    argumentos = criar_parser().parse_args()
    configuracao = carregar_configuracao_dataset(argumentos.configuracao)
    manifesto = PreparadorDataset(
        argumentos.entrada,
        argumentos.saida,
        configuracao,
    ).preparar()
    print(json.dumps(manifesto["quantidades"], ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
