"""Fonte sintetica usada para desenvolver e testar sem hardware."""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from math import sin
from threading import Event, Thread
from time import monotonic, sleep

import cv2
import numpy as np

from obr_oficial.dispositivos.buffer_ultimo_quadro import BufferUltimoQuadro
from obr_oficial.dispositivos.camera_base import EstadoCamera, QuadroCamera
from obr_oficial.dispositivos.metricas_imagem import calcular_metricas_imagem


class CameraSimulada:
    """Gera uma pista clara com linha escura e movimento controlado."""

    def __init__(self, largura: int = 640, altura: int = 480, fps: float = 25.0) -> None:
        self._largura = largura
        self._altura = altura
        self._fps = fps
        self._buffer = BufferUltimoQuadro()
        self._parar = Event()
        self._thread: Thread | None = None
        self._inicio_s = monotonic()
        self._total_quadros = 0
        self._instantes: deque[float] = deque(maxlen=90)

    def iniciar(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._parar.clear()
        self._inicio_s = monotonic()
        self._thread = Thread(target=self._executar, name="camera-simulada", daemon=True)
        self._thread.start()
        if self._buffer.obter(timeout_s=2.0) is None:
            raise RuntimeError("Camera simulada nao gerou o primeiro quadro")

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
            saudavel=ativa and idade is not None and idade < 1000.0,
            nome_perfil="simulacao",
            nome_dispositivo="Camera sintetica OBR",
            origem="simulacao",
            backend="numpy/opencv",
            largura=self._largura,
            altura=self._altura,
            quadros_por_segundo_configurado=self._fps,
            quadros_por_segundo_medido=fps_medido,
            total_quadros=self._total_quadros,
            total_falhas=0,
            ultimo_erro="",
            idade_ultimo_quadro_ms=idade,
            propriedades={"simulada": True},
        )

    def _executar(self) -> None:
        periodo = 1.0 / self._fps
        proximo = monotonic()
        while not self._parar.is_set():
            agora = monotonic()
            if agora < proximo:
                sleep(proximo - agora)
            instante = monotonic()
            proximo = instante + periodo
            self._total_quadros += 1
            self._instantes.append(instante)
            imagem = self._gerar_imagem(instante - self._inicio_s)
            quadro = QuadroCamera(
                id_quadro=self._total_quadros,
                instante_monotonico_s=instante,
                instante_utc=datetime.now(UTC).isoformat(),
                imagem_bgr=imagem,
                metricas=calcular_metricas_imagem(imagem),
            )
            self._buffer.publicar(quadro)

    def _gerar_imagem(self, tempo_s: float):
        gradiente = np.linspace(225, 250, self._altura, dtype=np.uint8)[:, None]
        cinza = np.repeat(gradiente, self._largura, axis=1)
        imagem = cv2.cvtColor(cinza, cv2.COLOR_GRAY2BGR)
        deslocamento = int(sin(tempo_s * 0.7) * self._largura * 0.16)
        pontos = []
        for y in range(self._altura, -1, -8):
            progresso = 1.0 - y / self._altura
            x = int(self._largura / 2 + deslocamento * progresso * progresso)
            pontos.append((x, y))
        cv2.polylines(imagem, [np.array(pontos, dtype=np.int32)], False, (15, 15, 15), 34)
        return imagem
