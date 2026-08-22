"""CLI de empacotamento do candidato neural para o Raspberry Pi 5."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obr_oficial.implantacao.exportacao_modelo import preparar_pacote, salvar_manifesto
from obr_oficial.nucleo.configuracao import raiz_projeto


def main(argumentos: list[str] | None = None) -> int:
    raiz = raiz_projeto()
    parser = argparse.ArgumentParser(
        description="Exporta e verifica o modelo de linha sem abrir o conjunto de teste"
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=raiz / "modelos" / "linha" / "lraspp_v2" / "melhor.pt",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=raiz / "artefatos" / "fase3_dataset_v2",
    )
    parser.add_argument(
        "--onnx",
        type=Path,
        default=raiz / "modelos" / "linha" / "lraspp_v2" / "modelo.onnx",
    )
    parser.add_argument(
        "--manifesto",
        type=Path,
        default=raiz / "modelos" / "linha" / "lraspp_v2" / "manifesto.json",
    )
    parser.add_argument("--limiar", type=float, default=0.80)
    parser.add_argument("--sha256-checkpoint-esperado")
    parser.add_argument("--sha256-dataset")
    parser.add_argument("--sha256-pacote-resultados")
    opcoes = parser.parse_args(argumentos)
    if not 0.0 < opcoes.limiar < 1.0:
        parser.error("--limiar deve estar estritamente entre 0 e 1")
    manifesto = preparar_pacote(
        opcoes.checkpoint,
        opcoes.onnx,
        opcoes.dataset,
        limiar=opcoes.limiar,
        sha256_checkpoint_esperado=opcoes.sha256_checkpoint_esperado,
        sha256_dataset=opcoes.sha256_dataset,
        sha256_pacote_resultados=opcoes.sha256_pacote_resultados,
    )
    salvar_manifesto(manifesto, opcoes.manifesto)
    print(json.dumps(manifesto, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
