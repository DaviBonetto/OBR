"""Dashboard somente leitura da percepcao neural da linha."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from time import sleep

import cv2
from flask import Flask, Response, jsonify, request, send_from_directory

from obr_oficial.dispositivos.camera_base import FonteCamera
from obr_oficial.percepcao.linha.execucao_continua import (
    ProcessadorContinuoLinha,
    estimativa_como_dict,
)


def criar_painel_percepcao_linha(
    fonte_camera: FonteCamera,
    processador: ProcessadorContinuoLinha,
    *,
    pasta_web: Path | None = None,
    quadros_video_por_segundo: float = 20.0,
    qualidade_jpeg: int = 82,
) -> Flask:
    """Monta o painel observador sem iniciar camera, thread ou servidor."""

    if pasta_web is None:
        pasta_web = Path(__file__).resolve().parent / "web"
    pasta_web = pasta_web.resolve()
    qualidade_jpeg = max(30, min(int(qualidade_jpeg), 95))
    periodo_video_s = 1.0 / max(float(quadros_video_por_segundo), 1.0)
    app = Flask(__name__, static_folder=None)
    app.json.ensure_ascii = False

    @app.after_request
    def impedir_cache(resposta):
        if request.path.startswith("/api/") or request.path == "/video-linha.mjpg":
            resposta.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return resposta

    @app.get("/")
    def pagina_inicial():
        return send_from_directory(pasta_web, "percepcao.html")

    @app.get("/percepcao.css")
    def folha_estilo():
        return send_from_directory(pasta_web, "percepcao.css")

    @app.get("/percepcao.js")
    def codigo_painel():
        return send_from_directory(pasta_web, "percepcao.js")

    @app.get("/api/estado")
    def estado():
        resultado = processador.obter_ultimo_resultado()
        percepcao = None
        if resultado is not None:
            percepcao = {
                "estimativa": estimativa_como_dict(resultado.estimativa),
                "diagnostico": asdict(resultado.diagnostico),
            }
        return jsonify(
            {
                "ok": True,
                "somente_leitura": True,
                "atuadores_habilitados": False,
                "camera": fonte_camera.obter_estado().como_dict(),
                "processador": processador.obter_estado().como_dict(),
                "percepcao": percepcao,
            }
        )

    @app.get("/video-linha.mjpg")
    def video():
        def gerar():
            ultimo_id: int | None = None
            while True:
                resultado = processador.obter_ultimo_resultado(
                    depois_de=ultimo_id,
                    timeout_s=1.0,
                )
                if resultado is None:
                    continue
                sucesso, jpeg = cv2.imencode(
                    ".jpg",
                    resultado.imagem_sobreposta,
                    [cv2.IMWRITE_JPEG_QUALITY, qualidade_jpeg],
                )
                if not sucesso:
                    continue
                ultimo_id = resultado.id_quadro
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
