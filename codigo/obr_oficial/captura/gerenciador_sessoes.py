"""Sessoes atomicas de captura de imagens para treinamento e regressao."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

import cv2

from obr_oficial.dispositivos.camera_base import QuadroCamera


class ErroCaptura(RuntimeError):
    """Erro de uso ou persistencia de uma sessao de captura."""


class GerenciadorSessoesCaptura:
    """Cria sessoes isoladas e salva cada foto com sua proveniencia."""

    VERSAO_MANIFESTO = 1

    def __init__(self, raiz_dados: Path, *, compressao_png: int = 3) -> None:
        self._raiz_dados = raiz_dados.resolve()
        self._raiz_dados.mkdir(parents=True, exist_ok=True)
        self._compressao_png = max(0, min(int(compressao_png), 9))
        self._lock = Lock()
        self._pasta_sessao: Path | None = None
        self._manifesto: dict[str, Any] | None = None

    def iniciar(self, contexto: dict[str, Any], camera: dict[str, Any]) -> dict[str, Any]:
        """Inicia uma sessao; nunca sobrescreve uma sessao existente."""

        with self._lock:
            if self._manifesto is not None:
                raise ErroCaptura("Ja existe uma sessao ativa")

            contexto_limpo = self._normalizar_contexto(contexto)
            agora = datetime.now(UTC)
            nome = contexto_limpo.get("nome") or "captura"
            identificador = f"{agora:%Y%m%dT%H%M%SZ}_{_slug(nome)}_{uuid4().hex[:6]}"
            pasta = self._raiz_dados / identificador
            quadros = pasta / "quadros"
            quadros.mkdir(parents=True, exist_ok=False)

            self._pasta_sessao = pasta
            self._manifesto = {
                "versao_manifesto": self.VERSAO_MANIFESTO,
                "id_sessao": identificador,
                "estado": "ativa",
                "inicio_utc": agora.isoformat(),
                "fim_utc": None,
                "contexto": contexto_limpo,
                "camera": camera,
                "capturas": 0,
                "contagens_por_categoria": {},
            }
            self._salvar_manifesto()
            return self.obter_estado_sem_lock()

    def capturar(
        self,
        quadro: QuadroCamera,
        contexto: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Salva um PNG sem perdas e registra hash, metricas e origem do quadro."""

        with self._lock:
            if self._manifesto is None or self._pasta_sessao is None:
                raise ErroCaptura("Inicie uma sessao antes de capturar")

            numero = int(self._manifesto["capturas"]) + 1
            nome_arquivo = f"quadro_{numero:06d}.png"
            caminho_relativo = Path("quadros") / nome_arquivo
            caminho = self._pasta_sessao / caminho_relativo

            sucesso, codificada = cv2.imencode(
                ".png",
                quadro.imagem_bgr,
                [cv2.IMWRITE_PNG_COMPRESSION, self._compressao_png],
            )
            if not sucesso:
                raise ErroCaptura("OpenCV nao conseguiu codificar o quadro como PNG")

            conteudo = codificada.tobytes()
            temporario = caminho.with_suffix(".png.tmp")
            temporario.write_bytes(conteudo)
            temporario.replace(caminho)

            contexto_limpo = self._normalizar_contexto(contexto or {})
            registro = {
                "versao_registro": 1,
                "numero": numero,
                "arquivo": caminho_relativo.as_posix(),
                "sha256": hashlib.sha256(conteudo).hexdigest(),
                "captura_utc": datetime.now(UTC).isoformat(),
                "quadro": {
                    "id": quadro.id_quadro,
                    "instante_utc": quadro.instante_utc,
                    "instante_monotonico_s": quadro.instante_monotonico_s,
                    "largura": quadro.largura,
                    "altura": quadro.altura,
                },
                "metricas": quadro.metricas.como_dict(),
                "contexto": contexto_limpo,
            }
            with (self._pasta_sessao / "capturas.jsonl").open("a", encoding="utf-8") as arquivo:
                arquivo.write(json.dumps(registro, ensure_ascii=False, sort_keys=True) + "\n")

            self._manifesto["capturas"] = numero
            categoria = contexto_limpo.get("categoria_verde")
            if isinstance(categoria, str) and categoria:
                contagens = self._manifesto["contagens_por_categoria"]
                contagens[categoria] = int(contagens.get(categoria, 0)) + 1
            self._manifesto["ultima_captura_utc"] = registro["captura_utc"]
            self._salvar_manifesto()
            return registro

    def finalizar(self) -> dict[str, Any]:
        """Fecha a sessao atual e preserva o ultimo estado no manifesto."""

        with self._lock:
            if self._manifesto is None:
                raise ErroCaptura("Nao existe sessao ativa")

            self._manifesto["estado"] = "finalizada"
            self._manifesto["fim_utc"] = datetime.now(UTC).isoformat()
            estado = dict(self._manifesto)
            self._salvar_manifesto()
            self._manifesto = None
            self._pasta_sessao = None
            return {"ativa": False, "ultima_sessao": estado}

    def finalizar_se_ativa(self) -> None:
        with self._lock:
            if self._manifesto is None:
                return
            self._manifesto["estado"] = "interrompida"
            self._manifesto["fim_utc"] = datetime.now(UTC).isoformat()
            self._salvar_manifesto()
            self._manifesto = None
            self._pasta_sessao = None

    def obter_estado(self) -> dict[str, Any]:
        with self._lock:
            return self.obter_estado_sem_lock()

    def obter_armazenamento(self) -> dict[str, int]:
        uso = shutil.disk_usage(self._raiz_dados)
        return {"total_bytes": uso.total, "livre_bytes": uso.free, "usado_bytes": uso.used}

    def obter_estado_sem_lock(self) -> dict[str, Any]:
        if self._manifesto is None or self._pasta_sessao is None:
            return {"ativa": False, "sessao": None}
        return {
            "ativa": True,
            "sessao": dict(self._manifesto),
            "pasta": str(self._pasta_sessao),
        }

    def _salvar_manifesto(self) -> None:
        if self._manifesto is None or self._pasta_sessao is None:
            return
        caminho = self._pasta_sessao / "manifesto.json"
        temporario = self._pasta_sessao / "manifesto.json.tmp"
        texto = json.dumps(self._manifesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        temporario.write_text(texto, encoding="utf-8")
        temporario.replace(caminho)

    @staticmethod
    def _normalizar_contexto(contexto: dict[str, Any]) -> dict[str, str | bool | float | int]:
        if not isinstance(contexto, dict):
            raise ErroCaptura("Contexto deve ser um objeto JSON")

        resultado: dict[str, str | bool | float | int] = {}
        for chave, valor in contexto.items():
            chave_limpa = _slug(str(chave))[:48]
            if not chave_limpa:
                continue
            if isinstance(valor, bool | int | float):
                resultado[chave_limpa] = valor
            elif valor is not None:
                resultado[chave_limpa] = str(valor).strip()[:500]
        return resultado


def _slug(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", texto)
    ascii_texto = normalizado.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_texto).strip("_")
    return slug[:64] or "sem_nome"
