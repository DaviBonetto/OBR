"""Gera as pre-anotacoes cromaticas da Fase Verde 2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obr_oficial.dados.mascaras_verdes import (
    ConfiguracaoGeracaoMascarasVerdes,
    DetectorCromaticoVerde,
    GeradorMascarasVerdes,
    carregar_configuracao_mascaras_verdes,
)
from obr_oficial.nucleo.configuracao import raiz_projeto


def main(argumentos: list[str] | None = None) -> int:
    raiz = raiz_projeto()
    parser = argparse.ArgumentParser(
        description="Gera mascaras verdes candidatas sem abrir o conjunto de teste"
    )
    parser.add_argument(
        "--brutos",
        type=Path,
        default=raiz / "dados" / "brutos" / "verde",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=raiz / "dados" / "processados" / "verde_v1",
    )
    parser.add_argument(
        "--configuracao",
        type=Path,
        default=raiz / "configuracoes" / "mascaras_verdes_v1.toml",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=raiz / "dados" / "rotulados" / "verde_v1_candidatas",
    )
    opcoes = parser.parse_args(argumentos)
    detector = DetectorCromaticoVerde(carregar_configuracao_mascaras_verdes(opcoes.configuracao))
    manifesto = GeradorMascarasVerdes(
        ConfiguracaoGeracaoMascarasVerdes(
            raiz_brutos=opcoes.brutos.resolve(),
            dataset_curado=opcoes.dataset.resolve(),
            saida=opcoes.saida.resolve(),
        ),
        detector,
    ).gerar()
    print(json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
