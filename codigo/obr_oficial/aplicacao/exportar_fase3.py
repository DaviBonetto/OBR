"""CLI para gerar o pacote transportavel do treino inicial da Fase 3."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obr_oficial.nucleo.configuracao import raiz_projeto
from obr_oficial.treinamento.exportacao_dataset import (
    ConfiguracaoExportacaoTreinamento,
    ExportadorDatasetTreinamento,
)


def main(argumentos: list[str] | None = None) -> int:
    raiz = raiz_projeto()
    parser = argparse.ArgumentParser(description="Exporta dataset inicial da Fase 3")
    parser.add_argument("--brutos", type=Path, default=raiz / "dados" / "brutos")
    parser.add_argument(
        "--rotulos",
        type=Path,
        default=raiz / "dados" / "rotulados" / "fase2_v1_rotulos_parciais",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=raiz / "artefatos" / "fase3_dataset_inicial.zip",
    )
    opcoes = parser.parse_args(argumentos)
    resultado = ExportadorDatasetTreinamento(
        ConfiguracaoExportacaoTreinamento(
            raiz_brutos=opcoes.brutos.resolve(),
            rotulos_consolidados=opcoes.rotulos.resolve(),
            arquivo_saida=opcoes.saida.resolve(),
        )
    ).exportar()
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
