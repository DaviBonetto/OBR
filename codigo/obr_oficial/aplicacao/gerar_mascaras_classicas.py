"""CLI da pre-anotacao classica da Fase 2."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from obr_oficial.dados.mascaras_classicas import (
    ConfiguracaoGeracaoMascaras,
    GeradorMascarasClassicas,
)
from obr_oficial.nucleo.configuracao import raiz_projeto
from obr_oficial.percepcao.linha import (
    DetectorClassicoLinha,
    carregar_configuracao_detector_classico,
)


def criar_parser() -> argparse.ArgumentParser:
    raiz = raiz_projeto()
    parser = argparse.ArgumentParser(
        description="Gera mascaras candidatas somente para treino e validacao.",
    )
    parser.add_argument("--brutos", type=Path, default=raiz / "dados" / "brutos")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=raiz / "dados" / "processados" / "fase2_v1",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=raiz / "dados" / "rotulados" / "fase2_v1_classico_candidatas",
    )
    parser.add_argument(
        "--configuracao",
        type=Path,
        default=raiz / "configuracoes" / "detector_classico.toml",
    )
    parser.add_argument("--intervalo-sobreposicao", type=int, default=40)
    return parser


def main() -> int:
    argumentos = criar_parser().parse_args()
    conteudo_configuracao = argumentos.configuracao.read_bytes()
    detector = DetectorClassicoLinha(
        carregar_configuracao_detector_classico(argumentos.configuracao)
    )
    manifesto = GeradorMascarasClassicas(
        ConfiguracaoGeracaoMascaras(
            raiz_brutos=argumentos.brutos.resolve(),
            dataset_processado=argumentos.dataset.resolve(),
            saida=argumentos.saida.resolve(),
            intervalo_sobreposicao=argumentos.intervalo_sobreposicao,
        ),
        detector,
        hash_configuracao_detector=hashlib.sha256(conteudo_configuracao).hexdigest(),
    ).gerar()
    print(json.dumps(manifesto, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
