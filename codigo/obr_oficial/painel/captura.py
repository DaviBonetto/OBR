"""API e transmissao MJPEG do painel de captura de dataset."""

from __future__ import annotations

from pathlib import Path
from time import sleep
from typing import Any

import cv2
from flask import Flask, Response, jsonify, request, send_from_directory

from obr_oficial.captura import ErroCaptura, GerenciadorSessoesCaptura
from obr_oficial.dispositivos.camera_base import FonteCamera


def criar_painel_captura(
    fonte_camera: FonteCamera,
    sessoes: GerenciadorSessoesCaptura,
    *,
    pasta_web: Path | None = None,
    quadros_video_por_segundo: float = 15.0,
    qualidade_jpeg: int = 80,
) -> Flask:
    """Monta o painel sem iniciar servidor ou camera implicitamente."""

    if pasta_web is None:
        pasta_web = Path(__file__).resolve().parent / "web"
    pasta_web = pasta_web.resolve()
    qualidade_jpeg = max(30, min(int(qualidade_jpeg), 95))
    periodo_video_s = 1.0 / max(float(quadros_video_por_segundo), 1.0)

    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
    app.json.ensure_ascii = False

    @app.after_request
    def impedir_cache(resposta):
        if request.path.startswith("/api/") or request.path == "/video.mjpg":
            resposta.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return resposta

    @app.errorhandler(ErroCaptura)
    def tratar_erro_captura(erro: ErroCaptura):
        return jsonify({"ok": False, "erro": str(erro)}), 400

    @app.get("/")
    def pagina_inicial():
        return send_from_directory(pasta_web, "index.html")

    @app.get("/painel.css")
    def folha_estilo():
        return send_from_directory(pasta_web, "painel.css")

    @app.get("/painel.js")
    def codigo_painel():
        return send_from_directory(pasta_web, "painel.js")

    @app.get("/api/estado")
    def estado():
        quadro = fonte_camera.obter_ultimo_quadro()
        estado_quadro: dict[str, Any] | None = None
        if quadro is not None:
            estado_quadro = {
                "id": quadro.id_quadro,
                "instante_utc": quadro.instante_utc,
                "largura": quadro.largura,
                "altura": quadro.altura,
                "metricas": quadro.metricas.como_dict(),
            }
        return jsonify(
            {
                "ok": True,
                "camera": fonte_camera.obter_estado().como_dict(),
                "quadro": estado_quadro,
                "captura": sessoes.obter_estado(),
                "armazenamento": sessoes.obter_armazenamento(),
            }
        )

    @app.post("/api/sessoes")
    def iniciar_sessao():
        dados = _obter_json()
        contexto = dados.get("contexto", dados)
        if not isinstance(contexto, dict):
            raise ErroCaptura("contexto deve ser um objeto")
        resultado = sessoes.iniciar(contexto, fonte_camera.obter_estado().como_dict())
        return jsonify({"ok": True, "captura": resultado}), 201

    @app.post("/api/capturas")
    def capturar():
        dados = _obter_json()
        quadro = fonte_camera.obter_ultimo_quadro()
        if quadro is None:
            raise ErroCaptura("A camera ainda nao entregou um quadro")
        resultado = sessoes.capturar(quadro, dados.get("contexto", dados))
        return jsonify({"ok": True, "registro": resultado}), 201

    @app.post("/api/sessoes/atual/finalizar")
    def finalizar_sessao():
        return jsonify({"ok": True, "captura": sessoes.finalizar()})

    @app.get("/video.mjpg")
    def video():
        def gerar():
            ultimo_id: int | None = None
            while True:
                quadro = fonte_camera.obter_ultimo_quadro(
                    depois_de=ultimo_id,
                    timeout_s=1.0,
                )
                if quadro is None:
                    continue
                sucesso, jpeg = cv2.imencode(
                    ".jpg",
                    quadro.imagem_bgr,
                    [cv2.IMWRITE_JPEG_QUALITY, qualidade_jpeg],
                )
                if not sucesso:
                    continue
                ultimo_id = quadro.id_quadro
                yield (
                    b"--quadro\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: "
                    + str(len(jpeg)).encode("ascii")
                    + b"\r\n\r\n"
                    + jpeg.tobytes()
                    + b"\r\n"
                )
                sleep(periodo_video_s)

        return Response(gerar(), mimetype="multipart/x-mixed-replace; boundary=quadro")

    return app


def _obter_json() -> dict[str, Any]:
    dados = request.get_json(silent=True)
    if dados is None:
        return {}
    if not isinstance(dados, dict):
        raise ErroCaptura("O corpo da requisicao deve ser um objeto JSON")
    return dados
