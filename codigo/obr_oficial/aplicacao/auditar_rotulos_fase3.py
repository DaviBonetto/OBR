"""Gera a fila de revisao humana dos desacordos encontrados na Fase 3."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from obr_oficial.nucleo.configuracao import raiz_projeto
from obr_oficial.treinamento.auditoria_rotulos import (
    ConfiguracaoAuditoriaRotulos,
    gerar_fila_auditoria_rotulos,
)


def main(argumentos: list[str] | None = None) -> int:
    raiz = raiz_projeto()
    parser = argparse.ArgumentParser(description="Audita rotulos vazios usando o modelo da Fase 3")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument(
        "--saida",
        type=Path,
        default=raiz / "dados" / "rotulados" / "fase3_v1_auditoria_desacordos",
    )
    parser.add_argument("--limiar", type=float, default=0.50)
    parser.add_argument("--confianca-minima", type=float, default=0.90)
    parser.add_argument("--area-minima", type=float, default=0.01)
    opcoes = parser.parse_args(argumentos)
    manifesto = gerar_fila_auditoria_rotulos(
        opcoes.dataset,
        opcoes.checkpoint,
        opcoes.saida,
        ConfiguracaoAuditoriaRotulos(
            limiar_segmentacao=opcoes.limiar,
            confianca_minima=opcoes.confianca_minima,
            area_minima_normalizada=opcoes.area_minima,
        ),
    )
    print(json.dumps(manifesto, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
