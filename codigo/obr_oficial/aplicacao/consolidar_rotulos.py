"""CLI para consolidar as decisoes humanas da Fase 2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obr_oficial.dados.consolidacao_rotulos import (
    ConfiguracaoConsolidacaoRotulos,
    ConsolidadorRotulos,
)
from obr_oficial.nucleo.configuracao import raiz_projeto


def main(argumentos: list[str] | None = None) -> int:
    raiz = raiz_projeto()
    parser = argparse.ArgumentParser(description="Consolida aprovacoes e fila de correcao")
    parser.add_argument(
        "--candidatas",
        type=Path,
        default=raiz / "dados" / "rotulados" / "fase2_v1_classico_candidatas",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=raiz / "dados" / "rotulados" / "fase2_v1_rotulos_parciais",
    )
    opcoes = parser.parse_args(argumentos)
    manifesto = ConsolidadorRotulos(
        ConfiguracaoConsolidacaoRotulos(
            pasta_candidatas=opcoes.candidatas.resolve(),
            saida=opcoes.saida.resolve(),
        )
    ).consolidar()
    print(json.dumps(manifesto, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
