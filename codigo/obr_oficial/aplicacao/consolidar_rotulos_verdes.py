"""CLI para consolidar as mascaras verdes apos a auditoria visual."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obr_oficial.dados.consolidacao_verde import (
    ConfiguracaoConsolidacaoVerde,
    ConsolidadorRotulosVerdes,
)
from obr_oficial.nucleo.configuracao import raiz_projeto


def main(argumentos: list[str] | None = None) -> int:
    raiz = raiz_projeto()
    parser = argparse.ArgumentParser(description="Consolida somente rotulos verdes seguros")
    parser.add_argument(
        "--candidatas",
        type=Path,
        default=raiz / "dados" / "rotulados" / "verde_v1_candidatas",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=raiz / "dados" / "rotulados" / "verde_v1_rotulos_iniciais",
    )
    opcoes = parser.parse_args(argumentos)
    manifesto = ConsolidadorRotulosVerdes(
        ConfiguracaoConsolidacaoVerde(
            pasta_candidatas=opcoes.candidatas.resolve(),
            saida=opcoes.saida.resolve(),
        )
    ).consolidar()
    print(json.dumps(manifesto, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
