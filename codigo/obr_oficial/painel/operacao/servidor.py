"""Servidor do painel de operacao: observacao ao vivo e ajuste de viradas.

O painel e somente observador e configurador: nunca comanda atuadores.
Video via MJPEG (sempre o quadro mais recente, sem fila), estado via SSE e
ajustes via POST idempotente com persistencia atomica em TOML.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING, Any

from flask import Flask, Response, jsonify, request, send_from_directory

from obr_oficial.dispositivos.camera_base import FonteCamera
from obr_oficial.nucleo.configuracao import exigir_secao
from obr_oficial.painel.operacao.captura import CapturadorOperacao, ErroCapturaOperacao
from obr_oficial.painel.operacao.estado import EstadoOperacao
from obr_oficial.painel.operacao.persistencia import GerenciadorViradas
from obr_oficial.painel.operacao.viradas import ErroViradas, estrutura_para_web

if TYPE_CHECKING:
    from obr_oficial.percepcao.linha.execucao_continua import ProcessadorContinuoLinha


def criar_painel_operacao(
    fonte_camera: FonteCamera,
    processador: ProcessadorContinuoLinha | None = None,
    gerenciador_viradas: GerenciadorViradas | None = None,
    *,
    pasta_web: Path | None = None,
    raiz_disco: Path | None = None,
    capturador: object | None = None,
    quadros_video_por_segundo: float = 20.0,
    qualidade_jpeg: int = 80,
    intervalo_eventos_s: float = 0.5,
) -> Flask:
    """Monta a aplicacao Flask sem iniciar camera, thread ou servidor."""

    if pasta_web is None:
        pasta_web = Path(__file__).resolve().parent / "web"
    pasta_web = pasta_web.resolve()
    if gerenciador_viradas is None:
        from obr_oficial.nucleo.configuracao import raiz_projeto

        gerenciador = GerenciadorViradas(raiz_projeto() / "configuracoes" / "viradas.toml")
    else:
        gerenciador = gerenciador_viradas
    if raiz_disco is None:
        from obr_oficial.nucleo.configuracao import raiz_projeto

        raiz_disco = raiz_projeto()

    qualidade_jpeg = max(30, min(int(qualidade_jpeg), 95))
    periodo_video_s = 1.0 / max(float(quadros_video_por_segundo), 1.0)
    intervalo_eventos_s = max(0.2, float(intervalo_eventos_s))
    estado = EstadoOperacao(
        fonte_camera,
        processador,
        gerenciador,
        raiz_disco=raiz_disco,
        capturador=capturador,
    )
    app = Flask(__name__, static_folder=None)
    app.json.ensure_ascii = False

    @app.after_request
    def impedir_cache(resposta):
        caminho = request.path
        if (
            caminho.startswith("/api/")
            or caminho == "/video.mjpg"
            or caminho == "/"
            or caminho == "/painel.css"
            or caminho == "/painel.js"
            or caminho.startswith("/fontes/")
        ):
            resposta.headers["Cache-Control"] = "no-store"
        return resposta

    @app.get("/")
    def pagina_inicial():
        return send_from_directory(pasta_web, "index.html")

    @app.get("/painel.css")
    def folha_estilo():
        return send_from_directory(pasta_web, "painel.css")

    @app.get("/painel.js")
    def codigo_painel():
        return send_from_directory(pasta_web, "painel.js")

    @app.get("/logo-equipe.png")
    def logo_equipe():
        return send_from_directory(pasta_web, "logo-equipe.png")

    @app.get("/fontes/<nome_arquivo>")
    def fonte_tipografica(nome_arquivo: str):
        permitidos = {
            "departure-mono-regular.woff2",
            "sora-regular.woff2",
            "sora-semibold.woff2",
            "LICENCAS.md",
        }
        if nome_arquivo not in permitidos:
            from flask import abort

            abort(404)
        return send_from_directory(pasta_web / "fontes", nome_arquivo)

    @app.get("/api/viradas")
    def listar_viradas():
        return jsonify({"ok": True, **estrutura_para_web(gerenciador.como_dict())})

    @app.post("/api/viradas/<grupo>/<campo>")
    def definir_virada(grupo: str, campo: str):
        corpo = request.get_json(silent=True)
        if not isinstance(corpo, dict) or "valor" not in corpo:
            return jsonify({"ok": False, "erro": "Corpo deve conter 'valor'"}), 400
        try:
            canonico = gerenciador.definir(f"{grupo}.{campo}", corpo["valor"])
        except ErroViradas as erro:
            return jsonify({"ok": False, "erro": str(erro)}), 400
        return jsonify({"ok": True, "chave": f"{grupo}.{campo}", "valor_ms": canonico})

    @app.get("/api/estado")
    def retrato_estado():
        return jsonify({"ok": True, **estado.construir()})

    @app.post("/api/captura/foto")
    def capturar_foto():
        if capturador is None:
            return jsonify({"ok": False, "erro": "captura indisponivel"}), 503
        try:
            caminho = capturador.capturar_foto()
        except ErroCapturaOperacao as erro:
            return jsonify({"ok": False, "erro": str(erro)}), 409
        return jsonify({"ok": True, "arquivo": str(caminho)})

    @app.post("/api/captura/video")
    def alternar_video():
        if capturador is None:
            return jsonify({"ok": False, "erro": "captura indisponivel"}), 503
        try:
            return jsonify({"ok": True, **capturador.alternar_video()})
        except ErroCapturaOperacao as erro:
            return jsonify({"ok": False, "erro": str(erro)}), 409

    @app.post("/api/captura/sequencia")
    def alternar_sequencia():
        if capturador is None:
            return jsonify({"ok": False, "erro": "captura indisponivel"}), 503
        corpo = request.get_json(silent=True) or {}
        try:
            return jsonify(
                {
                    "ok": True,
                    **capturador.alternar_sequencia(
                        intervalo_ms=int(corpo.get("intervalo_ms", 250)),
                        maximo=int(corpo.get("maximo", 0)),
                    ),
                }
            )
        except (ErroCapturaOperacao, ValueError) as erro:
            return jsonify({"ok": False, "erro": str(erro)}), 409

    @app.post("/api/controle/<acao>")
    def executar_controle(acao: str):
        acoes_permitidas = {"avancar", "parar", "recuar", "led_on", "led_off"}
        if acao not in acoes_permitidas:
            return jsonify({"ok": False, "erro": f"Comando '{acao}' desconhecido"}), 400
        return jsonify({"ok": True, "comando": acao})

    @app.get("/api/eventos")
    def fluxo_eventos():

        def gerar():
            while True:
                retrato = {"ok": True, **estado.construir()}
                yield (
                    "data: "
                    + json.dumps(retrato, ensure_ascii=False, separators=(",", ":"))
                    + "\n\n"
                )
                sleep(intervalo_eventos_s)

        resposta = Response(gerar(), mimetype="text/event-stream")
        resposta.headers["Cache-Control"] = "no-store"
        resposta.headers["X-Accel-Buffering"] = "no"
        return resposta

    @app.get("/video.mjpg")
    def video():
        if processador is not None:

            def gerar_processado():
                ultimo_id: int | None = None
                while True:
                    resultado = processador.obter_ultimo_resultado(
                        depois_de=ultimo_id,
                        timeout_s=1.0,
                    )
                    if resultado is None:
                        continue
                    sucesso, jpeg = _codificar(resultado.imagem_sobreposta, qualidade_jpeg)
                    if not sucesso:
                        continue
                    ultimo_id = resultado.id_quadro
                    yield _bloco_mjpeg(jpeg)
                    sleep(periodo_video_s)

            return Response(
                gerar_processado(),
                mimetype="multipart/x-mixed-replace; boundary=quadro",
            )

        return _resposta_video_bruto(fonte_camera, qualidade_jpeg, periodo_video_s)

    @app.get("/video-bruto.mjpg")
    def video_bruto():
        return _resposta_video_bruto(fonte_camera, qualidade_jpeg, periodo_video_s)

    return app


def _resposta_video_bruto(
    fonte_camera: FonteCamera,
    qualidade_jpeg: int,
    periodo_video_s: float,
) -> Response:
    """Stream MJPEG sempre bruto, direto da fonte, sem percepcao."""

    def gerar():
        ultimo_id: int | None = None
        while True:
            quadro = fonte_camera.obter_ultimo_quadro(
                depois_de=ultimo_id,
                timeout_s=1.0,
            )
            if quadro is None:
                continue
            sucesso, jpeg = _codificar(quadro.imagem_bgr, qualidade_jpeg)
            if not sucesso:
                continue
            ultimo_id = quadro.id_quadro
            yield _bloco_mjpeg(jpeg)
            sleep(periodo_video_s)

    return Response(gerar(), mimetype="multipart/x-mixed-replace; boundary=quadro")


def _codificar(imagem: Any, qualidade: int) -> tuple[bool, Any]:
    import cv2

    return cv2.imencode(".jpg", imagem, [cv2.IMWRITE_JPEG_QUALITY, qualidade])


def _bloco_mjpeg(jpeg: Any) -> bytes:
    return (
        b"--quadro\r\n"
        b"Content-Type: image/jpeg\r\n"
        b"Content-Length: "
        + str(len(jpeg)).encode("ascii")
        + b"\r\n\r\n"
        + jpeg.tobytes()
        + b"\r\n"
    )


def main(argumentos: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(
        description="Painel de operacao OBR: observacao ao vivo e tempos de virada",
    )
    analisador.add_argument("--simulacao", action="store_true", help="usa pista sintetica")
    analisador.add_argument("--origem", help="indice ou /dev/videoX da camera")
    analisador.add_argument("--host")
    analisador.add_argument("--porta", type=int)
    analisador.add_argument(
        "--sem-percepcao",
        action="store_true",
        help="exibe apenas o video bruto, mesmo com modelo disponivel",
    )
    analisador.add_argument("--configuracao-camera", default="camera_usb.toml")
    opcoes = analisador.parse_args(argumentos)

    from waitress import serve

    from obr_oficial.dispositivos import CameraSimulada, CameraUSB, ConfiguracaoCameraUSB
    from obr_oficial.nucleo.configuracao import carregar_configuracao, raiz_projeto

    raiz = raiz_projeto()
    configuracao_camera = carregar_configuracao(opcoes.configuracao_camera)
    dispositivo = exigir_secao(configuracao_camera, "dispositivo")
    perfil = exigir_secao(configuracao_camera, "perfil")
    qualidade = exigir_secao(configuracao_camera, "qualidade")

    if opcoes.simulacao:
        fonte = CameraSimulada(
            largura=int(dispositivo["largura"]),
            altura=int(dispositivo["altura"]),
            fps=float(dispositivo["quadros_por_segundo"]),
        )
    else:
        origem = opcoes.origem or dispositivo["origem"]
        texto = str(origem).strip()
        fonte = CameraUSB(
            ConfiguracaoCameraUSB(
                nome_perfil=str(perfil["nome"]),
                origem=int(texto) if texto.isdigit() else texto,
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

    processador = _montar_percepcao(raiz, fonte) if not opcoes.sem_percepcao else None
    gerenciador = GerenciadorViradas(raiz / "configuracoes" / "viradas.toml")
    capturador = CapturadorOperacao(fonte, raiz / "capturas_operacao")
    painel = criar_painel_operacao(fonte, processador, gerenciador, capturador=capturador)
    host = opcoes.host or "0.0.0.0"
    porta = opcoes.porta or 8090

    fonte.iniciar()
    if processador is not None:
        processador.iniciar()
    print("ATUADORES: DESABILITADOS", flush=True)
    print(f"Painel de operacao: http://{_endereco_exibivel(host)}:{porta}", flush=True)
    if processador is None:
        print(
            "Percepcao indisponivel (modelo ausente ou --sem-percepcao); exibindo video puro.",
            flush=True,
        )
    try:
        serve(painel, host=host, port=porta, threads=6, channel_timeout=30)
    finally:
        if processador is not None:
            processador.parar()
        fonte.parar()
    return 0


def _montar_percepcao(raiz: Path, fonte_camera: FonteCamera):
    """Tenta montar o pipeline neural; ausencia de modelo nao derruba o painel."""

    try:
        from obr_oficial.percepcao.linha import (
            DetectorNeuralLinha,
            ProcessadorContinuoLinha,
            RastreadorLinha,
            carregar_configuracao_detector_neural,
        )

        configuracao = carregar_configuracao_detector_neural(
            raiz / "configuracoes" / "percepcao_linha_neural.toml",
            raiz=raiz,
        )
        if not configuracao.arquivo_modelo.is_file():
            return None
        detector = DetectorNeuralLinha(configuracao)
        rastreador = RastreadorLinha(configuracao)
        return ProcessadorContinuoLinha(fonte_camera, detector, rastreador)
    except Exception:
        return None


def _endereco_exibivel(host: str) -> str:
    return "127.0.0.1" if host in {"", "0.0.0.0"} else host


if __name__ == "__main__":
    raise SystemExit(main())
