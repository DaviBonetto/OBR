"""Selecao e persistencia da referencia humana do centro da linha."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from threading import Lock
from typing import Any

TIPOS_REFERENCIA = ("reta", "curva_aberta", "curva_fechada", "intersecao")


class ErroReferenciaCentro(ValueError):
    """Indica uma referencia invalida ou tentativa de acessar o teste fechado."""


def preparar_selecao_referencia(
    raiz_dataset: Path,
    pasta_referencia: Path,
    *,
    quantidade_por_tipo: int = 12,
) -> Path:
    """Cria uma selecao estratificada e deterministica somente da validacao."""

    if quantidade_por_tipo < 1:
        raise ErroReferenciaCentro("quantidade_por_tipo deve ser positiva")
    raiz = raiz_dataset.resolve()
    indice = raiz / "indice.jsonl"
    try:
        linhas = indice.read_text(encoding="utf-8").splitlines()
    except OSError as erro:
        raise ErroReferenciaCentro(f"Indice do dataset ausente: {indice}") from erro

    por_tipo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for numero, linha in enumerate(linhas, start=1):
        if not linha.strip():
            continue
        try:
            item = json.loads(linha)
        except json.JSONDecodeError as erro:
            raise ErroReferenciaCentro(f"JSON invalido no indice, linha {numero}") from erro
        if item.get("divisao") == "teste":
            raise ErroReferenciaCentro("Indice contaminado pela divisao de teste")
        tipo = str(item.get("tipo_quadro", ""))
        if item.get("divisao") == "validacao" and tipo in TIPOS_REFERENCIA:
            por_tipo[tipo].append(item)

    selecao: list[dict[str, Any]] = []
    for tipo in TIPOS_REFERENCIA:
        candidatas = sorted(por_tipo[tipo], key=lambda item: str(item["id_amostra"]))
        if len(candidatas) < quantidade_por_tipo:
            raise ErroReferenciaCentro(
                f"Tipo {tipo} possui {len(candidatas)} amostras; "
                f"sao necessarias {quantidade_por_tipo}"
            )
        indices = _indices_distribuidos(len(candidatas), quantidade_por_tipo)
        for indice_original in indices:
            item = candidatas[indice_original]
            caminho_imagem = _resolver_dentro_da_raiz(raiz, str(item["imagem"]))
            if not caminho_imagem.is_file():
                raise ErroReferenciaCentro(f"Imagem selecionada ausente: {caminho_imagem}")
            selecao.append(
                {
                    "versao": 1,
                    "id_amostra": str(item["id_amostra"]),
                    "divisao": "validacao",
                    "tipo_quadro": tipo,
                    "imagem": str(item["imagem"]),
                    "sha256_imagem": str(item["sha256_imagem"]),
                }
            )

    pasta = pasta_referencia.resolve()
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / "selecao.jsonl"
    conteudo = "".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in selecao
    )
    if destino.is_file() and destino.read_text(encoding="utf-8") != conteudo:
        raise ErroReferenciaCentro(
            "A selecao existente diverge da selecao deterministica; preserve as anotacoes"
        )
    destino.write_text(conteudo, encoding="utf-8")
    return destino


def _indices_distribuidos(total: int, quantidade: int) -> tuple[int, ...]:
    if quantidade == 1:
        return (total // 2,)
    return tuple(round(indice * (total - 1) / (quantidade - 1)) for indice in range(quantidade))


def _resolver_dentro_da_raiz(raiz: Path, caminho_relativo: str) -> Path:
    caminho = (raiz / caminho_relativo).resolve()
    if not caminho.is_relative_to(raiz):
        raise ErroReferenciaCentro("Caminho de imagem fora da raiz do dataset")
    return caminho


class RepositorioReferenciaCentro:
    """Mantem a selecao congelada e um log anexado de anotacoes humanas."""

    def __init__(self, raiz_dataset: Path, pasta_referencia: Path) -> None:
        self.raiz_dataset = raiz_dataset.resolve()
        self.pasta_referencia = pasta_referencia.resolve()
        self.caminho_anotacoes = self.pasta_referencia / "anotacoes.jsonl"
        self._trava = Lock()
        self._amostras = self._carregar_selecao()
        self._por_id = {str(item["id_amostra"]): item for item in self._amostras}
        self._anotacoes = self._carregar_anotacoes()

    @property
    def amostras(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(item) for item in self._amostras)

    @property
    def anotacoes(self) -> dict[str, dict[str, Any]]:
        return {chave: dict(valor) for chave, valor in self._anotacoes.items()}

    def _carregar_selecao(self) -> list[dict[str, Any]]:
        caminho = self.pasta_referencia / "selecao.jsonl"
        if not caminho.is_file():
            raise ErroReferenciaCentro(f"Selecao humana ausente: {caminho}")
        amostras: list[dict[str, Any]] = []
        ids: set[str] = set()
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            if not linha.strip():
                continue
            item = json.loads(linha)
            if item.get("divisao") != "validacao":
                raise ErroReferenciaCentro("A referencia aceita somente a divisao de validacao")
            if item.get("tipo_quadro") not in TIPOS_REFERENCIA:
                raise ErroReferenciaCentro("Tipo inesperado na selecao humana")
            id_amostra = str(item.get("id_amostra", ""))
            if not id_amostra or id_amostra in ids:
                raise ErroReferenciaCentro("ID ausente ou duplicado na selecao humana")
            ids.add(id_amostra)
            caminho_imagem = _resolver_dentro_da_raiz(
                self.raiz_dataset,
                str(item.get("imagem", "")),
            )
            if not caminho_imagem.is_file():
                raise ErroReferenciaCentro(f"Imagem selecionada ausente: {caminho_imagem}")
            amostras.append(item)
        if not amostras:
            raise ErroReferenciaCentro("Selecao humana vazia")
        return amostras

    def _carregar_anotacoes(self) -> dict[str, dict[str, Any]]:
        anotacoes: dict[str, dict[str, Any]] = {}
        if not self.caminho_anotacoes.is_file():
            return anotacoes
        for linha in self.caminho_anotacoes.read_text(encoding="utf-8").splitlines():
            if not linha.strip():
                continue
            item = json.loads(linha)
            id_amostra = str(item.get("id_amostra", ""))
            if id_amostra not in self._por_id:
                raise ErroReferenciaCentro("Anotacao aponta para amostra fora da selecao")
            self._validar_pontos(item.get("pontos"))
            anotacoes[id_amostra] = item
        return anotacoes

    def consultar(
        self,
        *,
        indice: int,
        tipo: str = "todos",
        estado: str = "pendentes",
    ) -> dict[str, Any]:
        if tipo != "todos" and tipo not in TIPOS_REFERENCIA:
            raise ErroReferenciaCentro("Filtro de tipo invalido")
        if estado not in {"pendentes", "anotadas", "todas"}:
            raise ErroReferenciaCentro("Filtro de estado invalido")
        filtradas: list[tuple[int, dict[str, Any]]] = []
        for indice_original, amostra in enumerate(self._amostras):
            anotada = str(amostra["id_amostra"]) in self._anotacoes
            if tipo != "todos" and amostra["tipo_quadro"] != tipo:
                continue
            if estado == "pendentes" and anotada:
                continue
            if estado == "anotadas" and not anotada:
                continue
            filtradas.append((indice_original, amostra))
        if not filtradas:
            return {"total": 0, "indice": 0, "amostra": None, "resumo": self.resumo()}
        indice = max(0, min(indice, len(filtradas) - 1))
        indice_original, amostra = filtradas[indice]
        item = dict(amostra)
        item["indice_original"] = indice_original
        item["anotacao_atual"] = self._anotacoes.get(str(amostra["id_amostra"]))
        return {
            "total": len(filtradas),
            "indice": indice,
            "amostra": item,
            "resumo": self.resumo(),
        }

    def resumo(self) -> dict[str, Any]:
        por_tipo: dict[str, dict[str, int]] = {}
        for tipo in TIPOS_REFERENCIA:
            ids = [
                str(item["id_amostra"])
                for item in self._amostras
                if item["tipo_quadro"] == tipo
            ]
            anotadas = sum(id_amostra in self._anotacoes for id_amostra in ids)
            por_tipo[tipo] = {
                "total": len(ids),
                "anotadas": anotadas,
                "pendentes": len(ids) - anotadas,
            }
        total = len(self._amostras)
        anotadas = len(self._anotacoes)
        return {
            "total": total,
            "anotadas": anotadas,
            "pendentes": total - anotadas,
            "completa": anotadas == total,
            "por_tipo": por_tipo,
        }

    def registrar(
        self,
        id_amostra: str,
        pontos: Any,
        observacao: str = "",
    ) -> dict[str, Any]:
        if id_amostra not in self._por_id:
            raise ErroReferenciaCentro("Amostra desconhecida")
        if not isinstance(observacao, str) or len(observacao) > 500:
            raise ErroReferenciaCentro("Observacao excede 500 caracteres")
        pontos_validados = self._validar_pontos(pontos)
        amostra = self._por_id[id_amostra]
        registro = {
            "versao": 1,
            "id_amostra": id_amostra,
            "pontos": pontos_validados,
            "observacao": observacao.strip(),
            "sha256_imagem": str(amostra["sha256_imagem"]),
            "anotado_utc": datetime.now(UTC).isoformat(),
            "origem": "humana_manual",
        }
        linha = json.dumps(registro, ensure_ascii=False, sort_keys=True) + "\n"
        with self._trava:
            with self.caminho_anotacoes.open("a", encoding="utf-8") as arquivo:
                arquivo.write(linha)
                arquivo.flush()
            self._anotacoes[id_amostra] = registro
        return registro

    @staticmethod
    def _validar_pontos(pontos: Any) -> list[dict[str, float]]:
        if not isinstance(pontos, list) or not 4 <= len(pontos) <= 64:
            raise ErroReferenciaCentro("Marque entre 4 e 64 pontos no centro da linha")
        validados: list[dict[str, float]] = []
        for ponto in pontos:
            if not isinstance(ponto, dict):
                raise ErroReferenciaCentro("Ponto humano invalido")
            x = ponto.get("x")
            y = ponto.get("y")
            if isinstance(x, bool) or isinstance(y, bool):
                raise ErroReferenciaCentro("Coordenada humana invalida")
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                raise ErroReferenciaCentro("Coordenada humana invalida")
            if not 0.0 <= float(x) <= 1.0 or not 0.0 <= float(y) <= 1.0:
                raise ErroReferenciaCentro("Coordenada humana fora da imagem")
            validados.append({"x": round(float(x), 7), "y": round(float(y), 7)})
        comprimento = sum(
            ((atual["x"] - anterior["x"]) ** 2 + (atual["y"] - anterior["y"]) ** 2)
            ** 0.5
            for anterior, atual in pairwise(validados)
        )
        if comprimento < 0.25:
            raise ErroReferenciaCentro("A linha humana ficou curta demais")
        return validados

    def caminho_imagem(self, indice_original: int) -> Path:
        if not 0 <= indice_original < len(self._amostras):
            raise ErroReferenciaCentro("Indice de imagem invalido")
        return _resolver_dentro_da_raiz(
            self.raiz_dataset,
            str(self._amostras[indice_original]["imagem"]),
        )
