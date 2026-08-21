"""Painel local para revisar pre-anotacoes sem expor o conjunto de teste."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

import cv2
import numpy as np
from flask import Flask, Response, jsonify, request, send_from_directory


class ErroRevisaoMascaras(ValueError):
    """Indica entrada invalida ou tentativa de quebrar o isolamento do painel."""


DECISOES = frozenset({"aprovada", "mascara_vazia", "reprocessar"})


class RepositorioRevisaoMascaras:
    """Mantem candidatas imutaveis e decisoes humanas em log anexado."""

    def __init__(self, raiz_brutos: Path, pasta_candidatas: Path) -> None:
        self.raiz_brutos = raiz_brutos.resolve()
        self.pasta_candidatas = pasta_candidatas.resolve()
        self.caminho_revisoes = self.pasta_candidatas / "revisoes.jsonl"
        self._trava = Lock()
        self._amostras = self._carregar_candidatas()
        self._revisoes = self._carregar_revisoes()

    def _carregar_candidatas(self) -> list[dict[str, Any]]:
        caminho = self.pasta_candidatas / "candidatas.jsonl"
        if not caminho.is_file():
            raise ErroRevisaoMascaras(f"Candidatas nao encontradas: {caminho}")
        amostras: list[dict[str, Any]] = []
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            if not linha.strip():
                continue
            amostra = json.loads(linha)
            if amostra.get("divisao") == "teste":
                raise ErroRevisaoMascaras("Painel recusou candidata da divisao de teste")
            amostras.append(amostra)
        if not amostras:
            raise ErroRevisaoMascaras("Nenhuma candidata disponivel")
        return amostras

    def _carregar_revisoes(self) -> dict[str, dict[str, Any]]:
        revisoes: dict[str, dict[str, Any]] = {}
        if not self.caminho_revisoes.is_file():
            return revisoes
        for linha in self.caminho_revisoes.read_text(encoding="utf-8").splitlines():
            if linha.strip():
                revisao = json.loads(linha)
                revisoes[str(revisao["id_amostra"])] = revisao
        return revisoes

    def consultar(
        self,
        *,
        indice: int,
        divisao: str = "todas",
        tipo: str = "todos",
        revisao: str = "todas",
    ) -> dict[str, Any]:
        filtradas: list[tuple[int, dict[str, Any]]] = []
        for indice_original, amostra in enumerate(self._amostras):
            atual = self._revisoes.get(str(amostra["id_amostra"]))
            estado_revisao = "pendente" if atual is None else str(atual["decisao"])
            if divisao != "todas" and amostra["divisao"] != divisao:
                continue
            if tipo != "todos" and amostra["tipo_quadro"] != tipo:
                continue
            if revisao != "todas" and estado_revisao != revisao:
                continue
            filtradas.append((indice_original, amostra))
        if not filtradas:
            return {"total": 0, "indice": 0, "amostra": None, "resumo": self.resumo()}
        indice = max(0, min(indice, len(filtradas) - 1))
        indice_original, amostra = filtradas[indice]
        item = dict(amostra)
        item["indice_original"] = indice_original
        item["revisao_atual"] = self._revisoes.get(str(amostra["id_amostra"]))
        return {
            "total": len(filtradas),
            "indice": indice,
            "amostra": item,
            "resumo": self.resumo(),
        }

    def resumo(self) -> dict[str, int]:
        contagens = {"total": len(self._amostras), "pendente": 0}
        for amostra in self._amostras:
            revisao = self._revisoes.get(str(amostra["id_amostra"]))
            chave = "pendente" if revisao is None else str(revisao["decisao"])
            contagens[chave] = contagens.get(chave, 0) + 1
        return contagens

    def registrar(self, id_amostra: str, decisao: str, observacao: str) -> dict[str, Any]:
        if decisao not in DECISOES:
            raise ErroRevisaoMascaras("Decisao de revisao invalida")
        if len(observacao) > 500:
            raise ErroRevisaoMascaras("Observacao excede 500 caracteres")
        if id_amostra not in {str(item["id_amostra"]) for item in self._amostras}:
            raise ErroRevisaoMascaras("Amostra desconhecida")
        registro = {
            "versao": 1,
            "id_amostra": id_amostra,
            "decisao": decisao,
            "observacao": observacao.strip(),
            "revisado_utc": datetime.now(UTC).isoformat(),
        }
        linha = json.dumps(registro, ensure_ascii=False, sort_keys=True) + "\n"
        with self._trava:
            with self.caminho_revisoes.open("a", encoding="utf-8") as arquivo:
                arquivo.write(linha)
                arquivo.flush()
            self._revisoes[id_amostra] = registro
        return registro

    def renderizar(self, indice_original: int, modo: str) -> tuple[bytes, str]:
        if not 0 <= indice_original < len(self._amostras):
            raise ErroRevisaoMascaras("Indice de imagem invalido")
        amostra = self._amostras[indice_original]
        origem = self.raiz_brutos / Path(str(amostra["origem"]))
        mascara_path = self.pasta_candidatas / Path(str(amostra["mascara_candidata"]))
        imagem = _decodificar(origem, cv2.IMREAD_COLOR)
        mascara = _decodificar(mascara_path, cv2.IMREAD_GRAYSCALE)
        if imagem is None or mascara is None:
            raise ErroRevisaoMascaras("Imagem ou mascara candidata indisponivel")
        if modo == "origem":
            visual = imagem
        elif modo == "mascara":
            visual = mascara
        elif modo == "sobreposicao":
            altura_mascara, largura_mascara = mascara.shape
            roi_y = round(imagem.shape[0] * 0.30)
            roi = imagem[roi_y:]
            visual = cv2.resize(
                roi,
                (largura_mascara, altura_mascara),
                interpolation=cv2.INTER_AREA,
            )
            visual = visual.copy()
            visual[mascara > 0] = (
                0.45 * visual[mascara > 0] + 0.55 * np.array([255, 220, 0])
            ).astype(np.uint8)
        else:
            raise ErroRevisaoMascaras("Modo de imagem invalido")
        extensao = ".jpg" if visual.ndim == 3 else ".png"
        sucesso, codificada = cv2.imencode(extensao, visual)
        if not sucesso:
            raise ErroRevisaoMascaras("Falha ao codificar visualizacao")
        mimetype = "image/jpeg" if extensao == ".jpg" else "image/png"
        return codificada.tobytes(), mimetype


def _decodificar(caminho: Path, modo: int) -> np.ndarray | None:
    try:
        conteudo = caminho.read_bytes()
    except OSError:
        return None
    return cv2.imdecode(np.frombuffer(conteudo, dtype=np.uint8), modo)


def criar_painel_revisao(
    repositorio: RepositorioRevisaoMascaras,
    *,
    pasta_web: Path | None = None,
) -> Flask:
    """Cria o app Flask; iniciar o servidor permanece responsabilidade da CLI."""

    pasta_web = (pasta_web or Path(__file__).resolve().parent / "web").resolve()
    app = Flask(__name__, static_folder=None)
    app.json.ensure_ascii = False

    @app.errorhandler(ErroRevisaoMascaras)
    def tratar_erro(erro: ErroRevisaoMascaras):
        return jsonify({"ok": False, "erro": str(erro)}), 400

    @app.after_request
    def impedir_cache(resposta):
        resposta.headers["Cache-Control"] = "no-store"
        return resposta

    @app.get("/")
    def pagina():
        return send_from_directory(pasta_web, "revisao.html")

    @app.get("/revisao.css")
    def estilo():
        return send_from_directory(pasta_web, "revisao.css")

    @app.get("/revisao.js")
    def javascript():
        return send_from_directory(pasta_web, "revisao.js")

    @app.get("/api/amostra")
    def amostra():
        return jsonify(
            {
                "ok": True,
                **repositorio.consultar(
                    indice=request.args.get("indice", 0, type=int),
                    divisao=request.args.get("divisao", "todas", type=str),
                    tipo=request.args.get("tipo", "todos", type=str),
                    revisao=request.args.get("revisao", "todas", type=str),
                ),
            }
        )

    @app.get("/api/imagem/<int:indice_original>/<modo>")
    def imagem(indice_original: int, modo: str):
        conteudo, mimetype = repositorio.renderizar(indice_original, modo)
        return Response(conteudo, mimetype=mimetype)

    @app.post("/api/revisoes")
    def revisar():
        dados = request.get_json(silent=True)
        if not isinstance(dados, dict):
            raise ErroRevisaoMascaras("Corpo JSON obrigatorio")
        registro = repositorio.registrar(
            str(dados.get("id_amostra", "")),
            str(dados.get("decisao", "")),
            str(dados.get("observacao", "")),
        )
        return jsonify({"ok": True, "revisao": registro}), 201

    return app
