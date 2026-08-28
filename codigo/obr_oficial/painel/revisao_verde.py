"""Painel local da revisao das mascaras verdes, sem carregar o teste."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

import cv2
import numpy as np
from flask import Flask, Response, jsonify, request, send_from_directory


class ErroRevisaoVerde(ValueError):
    """Indica entrada invalida ou quebra do isolamento do painel verde."""


DECISOES_VERDE = frozenset({"aprovada", "mascara_vazia", "reprocessar"})


class RepositorioRevisaoVerde:
    """Mantem candidatas imutaveis e decisoes humanas em um log anexado."""

    def __init__(self, raiz_brutos: Path, pasta_candidatas: Path) -> None:
        self.raiz_brutos = raiz_brutos.resolve()
        self.pasta_candidatas = pasta_candidatas.resolve()
        self.caminho_revisoes = self.pasta_candidatas / "revisoes.jsonl"
        self._trava = Lock()
        self._amostras = self._carregar_candidatas()
        self._ids = {str(item["id_amostra"]) for item in self._amostras}
        self._revisoes = self._carregar_revisoes()

    def _carregar_candidatas(self) -> list[dict[str, Any]]:
        caminho = self.pasta_candidatas / "candidatas.jsonl"
        if not caminho.is_file():
            raise ErroRevisaoVerde(f"Candidatas verdes nao encontradas: {caminho}")
        amostras: list[dict[str, Any]] = []
        for numero, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1):
            if not linha.strip():
                continue
            amostra = json.loads(linha)
            if amostra.get("divisao") == "teste":
                raise ErroRevisaoVerde("Painel recusou candidata da divisao de teste")
            if amostra.get("divisao") not in {"treino", "validacao"}:
                raise ErroRevisaoVerde(f"Divisao invalida na candidata {numero}")
            amostras.append(amostra)
        if not amostras:
            raise ErroRevisaoVerde("Nenhuma candidata verde disponivel")
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

    def _estado_revisao(self, amostra: dict[str, Any]) -> str:
        revisao = self._revisoes.get(str(amostra["id_amostra"]))
        return (
            str(amostra.get("revisao_inicial", "pendente"))
            if revisao is None
            else str(revisao["decisao"])
        )

    def consultar(
        self,
        *,
        indice: int,
        divisao: str = "todas",
        categoria: str = "todas",
        prioridade: str = "fila",
        revisao: str = "pendente",
    ) -> dict[str, Any]:
        filtradas: list[tuple[int, dict[str, Any]]] = []
        for indice_original, amostra in enumerate(self._amostras):
            estado = self._estado_revisao(amostra)
            if divisao != "todas" and amostra["divisao"] != divisao:
                continue
            if categoria != "todas" and amostra["categoria_verde"] != categoria:
                continue
            if prioridade == "fila" and not bool(amostra.get("fila_revisao_essencial", False)):
                continue
            if prioridade == "prioritarias" and amostra["prioridade"] != "prioritaria":
                continue
            if (
                prioridade not in {"todas", "fila", "prioritarias"}
                and amostra["prioridade"] != prioridade
            ):
                continue
            if revisao != "todas" and estado != revisao:
                continue
            filtradas.append((indice_original, amostra))
        if not filtradas:
            return {"total": 0, "indice": 0, "amostra": None, "resumo": self.resumo()}
        indice = max(0, min(indice, len(filtradas) - 1))
        indice_original, amostra = filtradas[indice]
        item = dict(amostra)
        item["indice_original"] = indice_original
        item["estado_revisao"] = self._estado_revisao(amostra)
        item["revisao_atual"] = self._revisoes.get(str(amostra["id_amostra"]))
        return {
            "total": len(filtradas),
            "indice": indice,
            "amostra": item,
            "resumo": self.resumo(),
        }

    def resumo(self) -> dict[str, int]:
        contagens: CounterLike = {"total": len(self._amostras)}
        for amostra in self._amostras:
            estado = self._estado_revisao(amostra)
            contagens[estado] = contagens.get(estado, 0) + 1
            prioridade = str(amostra["prioridade"])
            contagens[f"prioridade_{prioridade}"] = contagens.get(f"prioridade_{prioridade}", 0) + 1
            if bool(amostra.get("fila_revisao_essencial", False)):
                contagens["fila_revisao_essencial"] = contagens.get("fila_revisao_essencial", 0) + 1
        contagens.setdefault("pendente", 0)
        contagens.setdefault("fila_revisao_essencial", 0)
        return contagens

    def registrar(self, id_amostra: str, decisao: str, observacao: str) -> dict[str, Any]:
        if decisao not in DECISOES_VERDE:
            raise ErroRevisaoVerde("Decisao de revisao verde invalida")
        if id_amostra not in self._ids:
            raise ErroRevisaoVerde("Amostra verde desconhecida")
        if len(observacao) > 500:
            raise ErroRevisaoVerde("Observacao excede 500 caracteres")
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
            raise ErroRevisaoVerde("Indice de imagem invalido")
        amostra = self._amostras[indice_original]
        origem = _resolver_interno(self.raiz_brutos, str(amostra["origem"]))
        caminho_mascara = _resolver_interno(
            self.pasta_candidatas,
            str(amostra["mascara_candidata"]),
        )
        imagem = _decodificar(origem, cv2.IMREAD_COLOR)
        mascara = _decodificar(caminho_mascara, cv2.IMREAD_GRAYSCALE)
        if imagem is None or mascara is None or imagem.shape[:2] != mascara.shape:
            raise ErroRevisaoVerde("Imagem ou mascara verde indisponivel")
        if modo == "origem":
            visual = imagem
        elif modo == "mascara":
            visual = mascara
        elif modo == "sobreposicao":
            visual = imagem.copy()
            visual[mascara > 0] = (
                0.35 * visual[mascara > 0] + 0.65 * np.array([0, 220, 255])
            ).astype(np.uint8)
            contornos, _ = cv2.findContours(
                mascara,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE,
            )
            cv2.drawContours(visual, contornos, -1, (0, 255, 255), 2, cv2.LINE_AA)
        else:
            raise ErroRevisaoVerde("Modo de imagem invalido")
        extensao = ".jpg" if visual.ndim == 3 else ".png"
        sucesso, codificada = cv2.imencode(extensao, visual)
        if not sucesso:
            raise ErroRevisaoVerde("Falha ao codificar visualizacao verde")
        mimetype = "image/jpeg" if extensao == ".jpg" else "image/png"
        return codificada.tobytes(), mimetype


CounterLike = dict[str, int]


def _resolver_interno(raiz: Path, relativo: str) -> Path:
    caminho = (raiz / Path(relativo)).resolve()
    if not caminho.is_relative_to(raiz):
        raise ErroRevisaoVerde("Caminho fora da raiz permitida")
    return caminho


def _decodificar(caminho: Path, modo: int) -> np.ndarray | None:
    try:
        conteudo = caminho.read_bytes()
    except OSError:
        return None
    return cv2.imdecode(np.frombuffer(conteudo, dtype=np.uint8), modo)


def criar_painel_revisao_verde(
    repositorio: RepositorioRevisaoVerde,
    *,
    pasta_web: Path | None = None,
) -> Flask:
    """Cria o app Flask; a CLI continua responsavel pelo servidor."""

    pasta_web = (pasta_web or Path(__file__).resolve().parent / "web").resolve()
    app = Flask(__name__, static_folder=None)
    app.json.ensure_ascii = False

    @app.errorhandler(ErroRevisaoVerde)
    def tratar_erro(erro: ErroRevisaoVerde):
        return jsonify({"ok": False, "erro": str(erro)}), 400

    @app.after_request
    def impedir_cache(resposta):
        resposta.headers["Cache-Control"] = "no-store"
        return resposta

    @app.get("/")
    def pagina():
        return send_from_directory(pasta_web, "revisao_verde.html")

    @app.get("/revisao_verde.css")
    def estilo():
        return send_from_directory(pasta_web, "revisao_verde.css")

    @app.get("/revisao_verde.js")
    def javascript():
        return send_from_directory(pasta_web, "revisao_verde.js")

    @app.get("/api/amostra")
    def amostra():
        return jsonify(
            {
                "ok": True,
                **repositorio.consultar(
                    indice=request.args.get("indice", 0, type=int),
                    divisao=request.args.get("divisao", "todas", type=str),
                    categoria=request.args.get("categoria", "todas", type=str),
                    prioridade=request.args.get("prioridade", "fila", type=str),
                    revisao=request.args.get("revisao", "pendente", type=str),
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
            raise ErroRevisaoVerde("Corpo JSON obrigatorio")
        registro = repositorio.registrar(
            str(dados.get("id_amostra", "")),
            str(dados.get("decisao", "")),
            str(dados.get("observacao", "")),
        )
        return jsonify({"ok": True, "revisao": registro}), 201

    return app
