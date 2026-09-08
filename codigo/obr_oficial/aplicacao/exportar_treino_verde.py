"""Exporta o pacote auditado da Fase Verde 3 para CPU ou Colab."""

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
    parser = argparse.ArgumentParser(description="Exporta dataset auditado da Fase Verde 3")
    parser.add_argument("--brutos", type=Path, default=raiz / "dados" / "brutos" / "verde")
    parser.add_argument(
        "--rotulos",
        type=Path,
        default=raiz / "dados" / "rotulados" / "verde_v1_rotulos_iniciais",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=raiz / "artefatos" / "fase_verde_3_dataset_v1.zip",
    )
    parser.add_argument(
        "--manifesto-publico",
        type=Path,
        default=raiz / "dados" / "manifestos" / "fase_verde_3_dataset_v1.json",
    )
    opcoes = parser.parse_args(argumentos)
    resultado = ExportadorDatasetTreinamento(
        ConfiguracaoExportacaoTreinamento(
            raiz_brutos=opcoes.brutos.resolve(),
            rotulos_consolidados=opcoes.rotulos.resolve(),
            arquivo_saida=opcoes.saida.resolve(),
        )
    ).exportar()
    manifesto = {
        **resultado,
        "fase": "verde_3",
        "tarefa": "segmentacao_binaria_de_marcadores_verdes",
        "casos_active_learning_fora_do_pacote": 271,
    }
    opcoes.manifesto_publico.parent.mkdir(parents=True, exist_ok=True)
    opcoes.manifesto_publico.write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifesto, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
