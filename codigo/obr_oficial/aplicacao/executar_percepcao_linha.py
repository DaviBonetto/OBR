"""Executa camera, detector neural e dashboard somente leitura."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from waitress import serve

from obr_oficial.dispositivos import (
    CameraReproducaoImagens,
    CameraSimulada,
    CameraUSB,
    ConfiguracaoCameraUSB,
    carregar_imagens_dataset,
)
from obr_oficial.nucleo.configuracao import carregar_configuracao, exigir_secao, raiz_projeto
from obr_oficial.painel import criar_painel_percepcao_linha
from obr_oficial.percepcao.linha import (
    DetectorNeuralLinha,
    ProcessadorContinuoLinha,
    RastreadorLinha,
    carregar_configuracao_detector_neural,
)


def main(argumentos: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(
        description="Dashboard da percepcao neural; nao controla atuadores"
    )
    fontes = analisador.add_mutually_exclusive_group()
    fontes.add_argument("--simulacao", action="store_true", help="usa pista sintetica")
    fontes.add_argument(
        "--reproduzir-capturas",
        type=Path,
        metavar="PASTA_DATASET",
        help="reproduz capturas reais de um dataset local sem abrir o teste",
    )
    analisador.add_argument(
        "--divisao-reproducao",
        choices=("treino", "validacao"),
        default="validacao",
    )
    analisador.add_argument("--fps-reproducao", type=float, default=5.0)
    analisador.add_argument("--configuracao-camera", default="camera_usb.toml")
    analisador.add_argument(
        "--configuracao-percepcao",
        default="percepcao_linha_neural.toml",
    )
    analisador.add_argument("--origem", help="indice ou /dev/videoX da camera")
    analisador.add_argument("--host")
    analisador.add_argument("--porta", type=int)
    opcoes = analisador.parse_args(argumentos)

    raiz = raiz_projeto()
    configuracao_camera = carregar_configuracao(opcoes.configuracao_camera)
    configuracao_painel = carregar_configuracao("painel_percepcao.toml")
    caminho_percepcao = raiz / "configuracoes" / opcoes.configuracao_percepcao
    configuracao_percepcao = carregar_configuracao_detector_neural(
        caminho_percepcao,
        raiz=raiz,
    )
    dispositivo = exigir_secao(configuracao_camera, "dispositivo")
    perfil = exigir_secao(configuracao_camera, "perfil")
    qualidade = exigir_secao(configuracao_camera, "qualidade")
    servidor = exigir_secao(configuracao_painel, "servidor")
    video = exigir_secao(configuracao_painel, "video")

    if opcoes.reproduzir_capturas is not None:
        caminho_dataset = opcoes.reproduzir_capturas
        if not caminho_dataset.is_absolute():
            caminho_dataset = raiz / caminho_dataset
        imagens = carregar_imagens_dataset(caminho_dataset, opcoes.divisao_reproducao)
        fonte = CameraReproducaoImagens(
            imagens,
            fps=opcoes.fps_reproducao,
            nome_perfil=f"capturas-reais-{opcoes.divisao_reproducao}",
        )
    elif opcoes.simulacao:
        fonte = CameraSimulada(
            largura=int(dispositivo["largura"]),
            altura=int(dispositivo["altura"]),
            fps=float(dispositivo["quadros_por_segundo"]),
        )
    else:
        origem = _converter_origem(opcoes.origem, dispositivo["origem"])
        fonte = CameraUSB(
            ConfiguracaoCameraUSB(
                nome_perfil=str(perfil["nome"]),
                origem=origem,
                largura=int(dispositivo["largura"]),
                altura=int(dispositivo["altura"]),
                quadros_por_segundo=float(dispositivo["quadros_por_segundo"]),
                formato=str(dispositivo["formato"]),
                rotacao_graus=int(dispositivo["rotacao_graus"]),
                tamanho_buffer=int(dispositivo["tamanho_buffer"]),
                tempo_primeiro_quadro_s=float(dispositivo["tempo_primeiro_quadro_s"]),
                limiar_escuro=int(qualidade["limiar_escuro"]),
                limiar_claro=int(qualidade["limiar_claro"]),
            )
        )

    detector = DetectorNeuralLinha(configuracao_percepcao)
    rastreador = RastreadorLinha(configuracao_percepcao)
    processador = ProcessadorContinuoLinha(fonte, detector, rastreador)
    painel = criar_painel_percepcao_linha(
        fonte,
        processador,
        quadros_video_por_segundo=float(video["quadros_por_segundo_maximo"]),
        qualidade_jpeg=int(video["qualidade_jpeg"]),
    )
    host = opcoes.host or str(servidor["endereco"])
    porta = opcoes.porta or int(servidor["porta"])

    fonte.iniciar()
    processador.iniciar()
    print("ATUADORES: DESABILITADOS", flush=True)
    print(f"Modelo: {configuracao_percepcao.arquivo_modelo.name}", flush=True)
    print(f"Fonte: {fonte.obter_estado().origem}", flush=True)
    print(f"Painel de percepcao: http://{host}:{porta}", flush=True)
    try:
        serve(painel, host=host, port=porta, threads=6, channel_timeout=30)
    finally:
        processador.parar()
        fonte.parar()
    return 0


def _converter_origem(valor_cli: str | None, valor_configuracao: Any) -> int | str:
    valor = valor_configuracao if valor_cli is None else valor_cli
    if isinstance(valor, int):
        return valor
    texto = str(valor).strip()
    if texto.isdigit():
        return int(texto)
    return texto


if __name__ == "__main__":
    raise SystemExit(main())
