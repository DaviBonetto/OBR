"""CLI de avaliacao da geometria neural sem abrir o teste."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obr_oficial.nucleo.configuracao import raiz_projeto
from obr_oficial.percepcao.linha import (
    DetectorNeuralLinha,
    carregar_configuracao_detector_neural,
)
from obr_oficial.percepcao.linha.avaliacao_geometria import (
    avaliar_geometria_validacao,
    gerar_montagem_diagnostico,
    salvar_relatorio,
)


def main(argumentos: list[str] | None = None) -> int:
    raiz = raiz_projeto()
    analisador = argparse.ArgumentParser(
        description="Avalia centro e trajetoria somente na validacao congelada"
    )
    analisador.add_argument(
        "--configuracao",
        type=Path,
        default=raiz / "configuracoes" / "percepcao_linha_neural.toml",
    )
    analisador.add_argument(
        "--dataset",
        type=Path,
        default=raiz / "artefatos" / "fase3_dataset_v2",
    )
    analisador.add_argument(
        "--saida",
        type=Path,
        default=raiz / "artefatos" / "fase4_avaliacao_geometria_validacao.json",
    )
    analisador.add_argument(
        "--montagem",
        type=Path,
        default=raiz / "artefatos" / "fase4_piores_erros_geometria.jpg",
    )
    opcoes = analisador.parse_args(argumentos)
    configuracao = carregar_configuracao_detector_neural(opcoes.configuracao, raiz=raiz)
    detector = DetectorNeuralLinha(configuracao)
    relatorio = avaliar_geometria_validacao(
        detector,
        opcoes.dataset,
    )
    salvar_relatorio(relatorio, opcoes.saida)
    gerar_montagem_diagnostico(
        detector,
        opcoes.dataset,
        relatorio,
        opcoes.montagem,
    )
    print(json.dumps(relatorio, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
