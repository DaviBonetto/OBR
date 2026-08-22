"""CLI de treinamento inicial da segmentacao neural."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from obr_oficial.nucleo.configuracao import raiz_projeto
from obr_oficial.treinamento.segmentacao import carregar_configuracao_treinamento, treinar


def main(argumentos: list[str] | None = None) -> int:
    raiz = raiz_projeto()
    parser = argparse.ArgumentParser(description="Treina segmentacao neural sem abrir o teste")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument(
        "--configuracao",
        type=Path,
        default=raiz / "configuracoes" / "treinamento_fase3.toml",
    )
    parser.add_argument("--sem-pretreino", action="store_true")
    parser.add_argument(
        "--arquitetura",
        choices=("linhanet", "lraspp_mobilenet_v3_large"),
        default="linhanet",
    )
    parser.add_argument("--epocas", type=int, help="sobrescreve epocas do TOML")
    parser.add_argument("--lote", type=int, help="sobrescreve lote do TOML")
    parser.add_argument("--trabalhadores", type=int, help="sobrescreve workers do TOML")
    parser.add_argument("--paciencia", type=int, help="sobrescreve early stopping do TOML")
    parser.add_argument("--taxa-aprendizado", type=float, help="sobrescreve learning rate")
    parser.add_argument("--checkpoint-inicial", type=Path, help="pesos para ajuste fino")
    opcoes = parser.parse_args(argumentos)
    configuracao = carregar_configuracao_treinamento(opcoes.configuracao)
    substituicoes = {
        nome: valor
        for nome, valor in (
            ("epocas", opcoes.epocas),
            ("lote", opcoes.lote),
            ("trabalhadores", opcoes.trabalhadores),
            ("paciencia", opcoes.paciencia),
            ("taxa_aprendizado", opcoes.taxa_aprendizado),
        )
        if valor is not None
    }
    configuracao = replace(configuracao, **substituicoes)
    manifesto = treinar(
        opcoes.dataset.resolve(),
        opcoes.saida.resolve(),
        configuracao,
        arquitetura=opcoes.arquitetura,
        pretreinado=not opcoes.sem_pretreino,
        checkpoint_inicial=opcoes.checkpoint_inicial,
    )
    print(json.dumps(manifesto, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
