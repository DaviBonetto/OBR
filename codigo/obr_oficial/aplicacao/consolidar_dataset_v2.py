"""Consolida a revisao humana e empacota o dataset da Fase 3 V2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obr_oficial.nucleo.configuracao import raiz_projeto
from obr_oficial.treinamento.dataset_v2 import consolidar_dataset_v2


def main(argumentos: list[str] | None = None) -> int:
    raiz = raiz_projeto()
    parser = argparse.ArgumentParser(description="Gera dataset V2 sem abrir o teste")
    parser.add_argument("--dataset-v1", type=Path, default=raiz / "artefatos/fase3_dataset_inicial")
    parser.add_argument(
        "--auditoria",
        type=Path,
        default=raiz / "dados/rotulados/fase3_v1_auditoria_desacordos",
    )
    parser.add_argument("--saida", type=Path, default=raiz / "artefatos/fase3_dataset_v2")
    parser.add_argument("--zip", type=Path, default=raiz / "artefatos/fase3_dataset_v2.zip")
    parser.add_argument(
        "--manifesto-publico",
        type=Path,
        default=raiz / "dados/manifestos/fase3_dataset_v2.json",
    )
    opcoes = parser.parse_args(argumentos)
    manifesto = consolidar_dataset_v2(
        opcoes.dataset_v1,
        opcoes.auditoria,
        opcoes.saida,
        opcoes.zip,
        opcoes.manifesto_publico,
    )
    print(json.dumps(manifesto, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
