"""Abre o painel humano que fecha o gate geometrico da Fase 4."""

from __future__ import annotations

import argparse
from pathlib import Path

from waitress import serve

from obr_oficial.dados.referencia_centro import (
    RepositorioReferenciaCentro,
    preparar_selecao_referencia,
)
from obr_oficial.nucleo.configuracao import raiz_projeto
from obr_oficial.painel.referencia_centro import criar_painel_referencia_centro
from obr_oficial.percepcao.linha import (
    DetectorNeuralLinha,
    carregar_configuracao_detector_neural,
)


def main(argumentos: list[str] | None = None) -> int:
    raiz = raiz_projeto()
    analisador = argparse.ArgumentParser(
        description="Anota a referencia humana do centro sem abrir o teste"
    )
    analisador.add_argument(
        "--dataset",
        type=Path,
        default=raiz / "artefatos" / "fase3_dataset_v2",
    )
    analisador.add_argument(
        "--referencia",
        type=Path,
        default=raiz / "dados" / "referencia_centro_fase4",
    )
    analisador.add_argument(
        "--configuracao",
        type=Path,
        default=raiz / "configuracoes" / "percepcao_linha_neural.toml",
    )
    analisador.add_argument("--quantidade-por-tipo", type=int, default=12)
    analisador.add_argument("--host", default="127.0.0.1")
    analisador.add_argument("--porta", type=int, default=8093)
    opcoes = analisador.parse_args(argumentos)

    preparar_selecao_referencia(
        opcoes.dataset,
        opcoes.referencia,
        quantidade_por_tipo=opcoes.quantidade_por_tipo,
    )
    repositorio = RepositorioReferenciaCentro(opcoes.dataset, opcoes.referencia)
    configuracao = carregar_configuracao_detector_neural(opcoes.configuracao, raiz=raiz)
    detector = DetectorNeuralLinha(configuracao)
    painel = criar_painel_referencia_centro(repositorio, detector)
    print("ATUADORES: DESABILITADOS", flush=True)
    print("Divisao de teste: FECHADA", flush=True)
    print(f"Referencia humana: http://{opcoes.host}:{opcoes.porta}", flush=True)
    serve(painel, host=opcoes.host, port=opcoes.porta, threads=4, channel_timeout=30)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
