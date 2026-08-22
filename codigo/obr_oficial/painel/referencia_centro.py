"""Painel local para desenhar a referencia humana do centro da linha."""

from __future__ import annotations

from pathlib import Path
from threading import Lock

import cv2
import numpy as np
from flask import Flask, Response, jsonify, request, send_from_directory

from obr_oficial.dados.referencia_centro import (
    ErroReferenciaCentro,
    RepositorioReferenciaCentro,
)
from obr_oficial.percepcao.linha.detector_neural import DetectorNeuralLinha
from obr_oficial.percepcao.linha.execucao_continua import estimativa_como_dict


def _decodificar(caminho: Path) -> np.ndarray:
    try:
        conteudo = caminho.read_bytes()
    except OSError as erro:
        raise ErroReferenciaCentro(f"Falha ao ler imagem: {caminho}") from erro
    imagem = cv2.imdecode(np.frombuffer(conteudo, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagem is None:
        raise ErroReferenciaCentro(f"Imagem invalida: {caminho}")
    return imagem


def criar_painel_referencia_centro(
    repositorio: RepositorioReferenciaCentro,
    detector: DetectorNeuralLinha,
    *,
    pasta_web: Path | None = None,
) -> Flask:
    """Cria o painel; a previsao fica escondida ate o humano decidir revela-la."""

    pasta_web = (pasta_web or Path(__file__).resolve().parent / "web").resolve()
    app = Flask(__name__, static_folder=None)
    app.json.ensure_ascii = False
    cache_previsoes: dict[int, dict[str, object]] = {}
    trava_cache = Lock()

    @app.errorhandler(ErroReferenciaCentro)
    def tratar_erro(erro: ErroReferenciaCentro):
        return jsonify({"ok": False, "erro": str(erro)}), 400

    @app.after_request
    def impedir_cache(resposta):
        resposta.headers["Cache-Control"] = "no-store"
        return resposta

    @app.get("/")
    def pagina():
        return send_from_directory(pasta_web, "referencia_centro.html")

    @app.get("/referencia_centro.css")
    def estilo():
        return send_from_directory(pasta_web, "referencia_centro.css")

    @app.get("/referencia_centro.js")
    def javascript():
        return send_from_directory(pasta_web, "referencia_centro.js")

    @app.get("/api/amostra")
    def amostra():
        return jsonify(
            {
                "ok": True,
                **repositorio.consultar(
                    indice=request.args.get("indice", 0, type=int),
                    tipo=request.args.get("tipo", "todos", type=str),
                    estado=request.args.get("estado", "pendentes", type=str),
                ),
            }
        )

    @app.get("/api/imagem/<int:indice_original>")
    def imagem(indice_original: int):
        original = _decodificar(repositorio.caminho_imagem(indice_original))
        y0 = round(original.shape[0] * detector.configuracao.roi_y)
        roi = cv2.resize(
            original[y0:],
            (detector.configuracao.largura, detector.configuracao.altura),
            interpolation=cv2.INTER_AREA,
        )
        sucesso, codificada = cv2.imencode(".jpg", roi, [cv2.IMWRITE_JPEG_QUALITY, 94])
        if not sucesso:
            raise ErroReferenciaCentro("Falha ao codificar imagem da referencia")
        return Response(codificada.tobytes(), mimetype="image/jpeg")

    @app.get("/api/previsao/<int:indice_original>")
    def previsao(indice_original: int):
        with trava_cache:
            armazenada = cache_previsoes.get(indice_original)
        if armazenada is None:
            original = _decodificar(repositorio.caminho_imagem(indice_original))
            resultado = detector.processar(original, id_quadro=indice_original)
            armazenada = estimativa_como_dict(resultado.estimativa)
            with trava_cache:
                cache_previsoes[indice_original] = armazenada
        return jsonify({"ok": True, "estimativa": armazenada})

    @app.post("/api/anotacoes")
    def anotar():
        dados = request.get_json(silent=True)
        if not isinstance(dados, dict):
            raise ErroReferenciaCentro("Corpo JSON obrigatorio")
        registro = repositorio.registrar(
            str(dados.get("id_amostra", "")),
            dados.get("pontos"),
            str(dados.get("observacao", "")),
        )
        return jsonify({"ok": True, "anotacao": registro}), 201

    return app
