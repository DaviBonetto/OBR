"""Fonte de camera que reproduz capturas reais de um dataset local."""

from __future__ import annotations

import json
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread
from time import monotonic

import cv2
import numpy as np

from obr_oficial.dispositivos.buffer_ultimo_quadro import BufferUltimoQuadro
from obr_oficial.dispositivos.camera_base import EstadoCamera, QuadroCamera
from obr_oficial.dispositivos.metricas_imagem import calcular_metricas_imagem


class ErroReproducaoCapturas(RuntimeError):
    """Indica um dataset inseguro ou sem imagens reproduziveis."""


def carregar_imagens_dataset(raiz_dataset: Path, divisao: str = "validacao") -> tuple[Path, ...]:
    """Seleciona imagens reais sem permitir acesso ao conjunto de teste."""

    if divisao not in {"treino", "validacao"}:
        raise ErroReproducaoCapturas(f"Divisao proibida na reproducao: {divisao}")

    raiz = raiz_dataset.resolve()
    caminho_indice = raiz / "indice.jsonl"
    try:
        linhas = caminho_indice.read_text(encoding="utf-8").splitlines()
    except OSError as erro:
        raise ErroReproducaoCapturas(f"Indice do dataset ausente: {caminho_indice}") from erro

    imagens: list[Path] = []
    for numero_linha, linha in enumerate(linhas, start=1):
        if not linha.strip():
            continue
        try:
            amostra = json.loads(linha)
        except json.JSONDecodeError as erro:
            raise ErroReproducaoCapturas(
                f"JSON invalido no indice, linha {numero_linha}"
            ) from erro
        if amostra.get("divisao") == "teste":
            raise ErroReproducaoCapturas("Indice contaminado pela divisao de teste")
        if amostra.get("divisao") != divisao:
            continue

        caminho_relativo = amostra.get("imagem")
        if not isinstance(caminho_relativo, str) or not caminho_relativo:
            raise ErroReproducaoCapturas(f"Imagem ausente no indice, linha {numero_linha}")
        caminho_imagem = (raiz / caminho_relativo).resolve()
        if not caminho_imagem.is_relative_to(raiz):
            raise ErroReproducaoCapturas(
                f"Imagem fora da raiz do dataset, linha {numero_linha}"
            )
        if not caminho_imagem.is_file():
            raise ErroReproducaoCapturas(f"Imagem nao encontrada: {caminho_imagem}")
        imagens.append(caminho_imagem)

    if not imagens:
        raise ErroReproducaoCapturas(f"Divisao vazia: {divisao}")
    return tuple(imagens)


class CameraReproducaoImagens:
    """Publica imagens reais em loop como se fossem quadros de camera."""

    def __init__(
        self,
        imagens: tuple[Path, ...],
        *,
        fps: float = 5.0,
        nome_perfil: str = "capturas-reais-validacao",
    ) -> None:
        if not imagens:
            raise ErroReproducaoCapturas("A reproducao precisa de ao menos uma imagem")
        if fps <= 0.0:
            raise ErroReproducaoCapturas("O FPS da reproducao deve ser positivo")
        self._imagens = imagens
        self._fps = fps
        self._nome_perfil = nome_perfil
        self._buffer = BufferUltimoQuadro()
        self._parar = Event()
        self._thread: Thread | None = None
        self._total_quadros = 0
        self._total_falhas = 0
        self._ultimo_erro = ""
        self._indice_atual = 0
        self._largura = 0
        self._altura = 0
        self._instantes: deque[float] = deque(maxlen=90)

    def iniciar(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._parar.clear()
        self._thread = Thread(target=self._executar, name="camera-capturas-reais", daemon=True)
        self._thread.start()
        if self._buffer.obter(timeout_s=3.0) is None:
            self.parar()
            detalhe = f": {self._ultimo_erro}" if self._ultimo_erro else ""
            raise ErroReproducaoCapturas(f"Nenhuma captura real pode ser aberta{detalhe}")

    def parar(self) -> None:
        self._parar.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None

    def obter_ultimo_quadro(
        self,
        *,
        depois_de: int | None = None,
        timeout_s: float = 0.0,
    ) -> QuadroCamera | None:
        return self._buffer.obter(depois_de=depois_de, timeout_s=timeout_s)

    def obter_estado(self) -> EstadoCamera:
        fps_medido = 0.0
        if len(self._instantes) >= 2:
            duracao = self._instantes[-1] - self._instantes[0]
            if duracao > 0.0:
                fps_medido = (len(self._instantes) - 1) / duracao
        idade = None
        if self._instantes:
            idade = (monotonic() - self._instantes[-1]) * 1000.0
        ativa = self._thread is not None and self._thread.is_alive()
        return EstadoCamera(
            ativa=ativa,
            saudavel=ativa and idade is not None and idade < max(1000.0, 3000.0 / self._fps),
            nome_perfil=self._nome_perfil,
            nome_dispositivo="Capturas reais OBR",
            origem="capturas_reais",
            backend="arquivos/png+opencv",
            largura=self._largura,
            altura=self._altura,
            quadros_por_segundo_configurado=self._fps,
            quadros_por_segundo_medido=fps_medido,
            total_quadros=self._total_quadros,
            total_falhas=self._total_falhas,
            ultimo_erro=self._ultimo_erro,
            idade_ultimo_quadro_ms=idade,
            propriedades={
                "reproducao": True,
                "quantidade_imagens": len(self._imagens),
                "indice_atual": self._indice_atual,
            },
        )

    def _executar(self) -> None:
        periodo = 1.0 / self._fps
        proximo = monotonic()
        while not self._parar.is_set():
            espera = proximo - monotonic()
            if espera > 0.0 and self._parar.wait(espera):
                break
            instante = monotonic()
            proximo = instante + periodo
            caminho = self._imagens[self._indice_atual]
            self._indice_atual = (self._indice_atual + 1) % len(self._imagens)
            try:
                imagem = self._ler_imagem(caminho)
            except ErroReproducaoCapturas as erro:
                self._total_falhas += 1
                self._ultimo_erro = str(erro)
                continue

            self._ultimo_erro = ""
            self._altura, self._largura = imagem.shape[:2]
            self._total_quadros += 1
            self._instantes.append(instante)
            self._buffer.publicar(
                QuadroCamera(
                    id_quadro=self._total_quadros,
                    instante_monotonico_s=instante,
                    instante_utc=datetime.now(UTC).isoformat(),
                    imagem_bgr=imagem,
                    metricas=calcular_metricas_imagem(imagem),
                )
            )

    @staticmethod
    def _ler_imagem(caminho: Path) -> np.ndarray:
        try:
            conteudo = caminho.read_bytes()
        except OSError as erro:
            raise ErroReproducaoCapturas(f"Falha ao ler {caminho}") from erro
        imagem = cv2.imdecode(np.frombuffer(conteudo, dtype=np.uint8), cv2.IMREAD_COLOR)
        if imagem is None:
            raise ErroReproducaoCapturas(f"Imagem invalida: {caminho}")
        return imagem
