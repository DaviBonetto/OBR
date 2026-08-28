"""CLI da auditoria e curadoria reproduzivel do dataset verde."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obr_oficial.dados.auditoria_verde import (
    CuradorDatasetVerde,
    carregar_plano_curadoria_verde,
)
from obr_oficial.nucleo.configuracao import raiz_projeto


def main(argumentos: list[str] | None = None) -> int:
    raiz = raiz_projeto()
    parser = argparse.ArgumentParser(description="Audita e cura o dataset bruto de verde")
    parser.add_argument("--brutos", type=Path, default=raiz / "dados" / "brutos" / "verde")
    parser.add_argument(
        "--plano",
        type=Path,
        default=raiz / "dados" / "manifestos" / "curadoria_verde_v1.json",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=raiz / "dados" / "processados" / "verde_v1",
    )
    opcoes = parser.parse_args(argumentos)

    plano = carregar_plano_curadoria_verde(opcoes.plano)
    manifesto = CuradorDatasetVerde(opcoes.brutos, opcoes.saida, plano).preparar()
    print(json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
