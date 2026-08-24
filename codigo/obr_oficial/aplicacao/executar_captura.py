"""Executa o painel de captura com camera real ou simulada."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from waitress import serve

from obr_oficial.captura import GerenciadorSessoesCaptura
from obr_oficial.dispositivos import CameraSimulada, CameraUSB, ConfiguracaoCameraUSB
from obr_oficial.nucleo.configuracao import carregar_configuracao, exigir_secao, raiz_projeto
from obr_oficial.painel import criar_painel_captura


def main(argumentos: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(description="Painel OBR para captura de dataset")
    analisador.add_argument("--simulacao", action="store_true", help="usa imagem sintetica")
    analisador.add_argument(
        "--modo",
        choices=("linha", "verde"),
        default="linha",
        help="protocolo de rotulagem exibido no painel",
    )
    analisador.add_argument(
        "--configuracao-camera",
        default="camera_usb.toml",
        help="perfil TOML dentro de configuracoes",
    )
    analisador.add_argument("--origem", help="indice ou /dev/videoX da camera")
    analisador.add_argument("--host", help="endereco do servidor")
    analisador.add_argument("--porta", type=int, help="porta do servidor")
    analisador.add_argument("--dados", type=Path, help="pasta de sessoes brutas")
    opcoes = analisador.parse_args(argumentos)

    configuracao_camera = carregar_configuracao(opcoes.configuracao_camera)
    configuracao_painel = carregar_configuracao("painel.toml")
    dispositivo = exigir_secao(configuracao_camera, "dispositivo")
    perfil = exigir_secao(configuracao_camera, "perfil")
    qualidade = exigir_secao(configuracao_camera, "qualidade")
    captura_config = exigir_secao(configuracao_camera, "captura")
    servidor = exigir_secao(configuracao_painel, "servidor")
    video = exigir_secao(configuracao_painel, "video")

    if opcoes.simulacao:
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

    pasta_padrao = raiz_projeto() / "dados" / "brutos"
    if opcoes.modo == "verde":
        pasta_padrao /= "verde"
    pasta_dados = (opcoes.dados or pasta_padrao).resolve()
    sessoes = GerenciadorSessoesCaptura(
        pasta_dados,
        compressao_png=int(captura_config["compressao_png"]),
    )
    painel = criar_painel_captura(
        fonte,
        sessoes,
        quadros_video_por_segundo=float(video["quadros_por_segundo_maximo"]),
        qualidade_jpeg=int(video["qualidade_jpeg"]),
        modo=opcoes.modo,
    )
    host = opcoes.host or str(servidor["endereco"])
    porta = opcoes.porta or int(servidor["porta"])

    fonte.iniciar()
    estado = fonte.obter_estado()
    print(f"Camera: {estado.nome_dispositivo} ({estado.largura}x{estado.altura})", flush=True)
    print(f"Captura: {opcoes.modo} -> {pasta_dados}", flush=True)
    print(f"Painel: http://{host}:{porta}", flush=True)
    try:
        serve(painel, host=host, port=porta, threads=6, channel_timeout=30)
    finally:
        sessoes.finalizar_se_ativa()
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
