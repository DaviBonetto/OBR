"""Captura USB/UVC com buffer de ultimo quadro e identidade de perfil."""

from __future__ import annotations

import platform
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic, sleep

import cv2

from obr_oficial.dispositivos.buffer_ultimo_quadro import BufferUltimoQuadro
from obr_oficial.dispositivos.camera_base import EstadoCamera, QuadroCamera
from obr_oficial.dispositivos.metricas_imagem import calcular_metricas_imagem


@dataclass(frozen=True, slots=True)
class ConfiguracaoCameraUSB:
    """Parametros que mudam entre cameras sem alterar o restante do sistema."""

    nome_perfil: str
    origem: int | str
    largura: int
    altura: int
    quadros_por_segundo: float
    formato: str = "MJPG"
    rotacao_graus: int = 0
    tamanho_buffer: int = 1
    tempo_primeiro_quadro_s: float = 8.0
    limiar_escuro: int = 10
    limiar_claro: int = 245

    def __post_init__(self) -> None:
        if not self.nome_perfil.strip():
            raise ValueError("nome_perfil nao pode ser vazio")
        if self.largura <= 0 or self.altura <= 0:
            raise ValueError("largura e altura devem ser positivas")
        if self.quadros_por_segundo <= 0:
            raise ValueError("quadros_por_segundo deve ser positivo")
        if len(self.formato) != 4 or not self.formato.isascii():
            raise ValueError("formato deve ser um FOURCC ASCII de quatro caracteres")
        if self.rotacao_graus not in {0, 90, 180, 270}:
            raise ValueError("rotacao_graus deve ser 0, 90, 180 ou 270")


class CameraUSB:
    """Le quadros continuamente em uma thread exclusiva."""

    def __init__(self, configuracao: ConfiguracaoCameraUSB) -> None:
        self._configuracao = configuracao
        self._buffer = BufferUltimoQuadro()
        self._parar = Event()
        self._thread: Thread | None = None
        self._captura: cv2.VideoCapture | None = None
        self._lock_estado = Lock()
        self._ativa = False
        self._total_quadros = 0
        self._total_falhas = 0
        self._ultimo_erro = ""
        self._ultimo_instante_s: float | None = None
        self._instantes_recentes: deque[float] = deque(maxlen=90)
        self._backend = ""
        self._nome_dispositivo = self._descobrir_nome_dispositivo()
        self._largura_real = 0
        self._altura_real = 0

    def iniciar(self) -> None:
        if self._ativa:
            return

        captura = self._abrir_dispositivo()
        if not captura.isOpened():
            captura.release()
            raise RuntimeError(f"Nao foi possivel abrir a camera: {self._configuracao.origem}")

        captura.set(cv2.CAP_PROP_FRAME_WIDTH, self._configuracao.largura)
        captura.set(cv2.CAP_PROP_FRAME_HEIGHT, self._configuracao.altura)
        captura.set(
            cv2.CAP_PROP_FOURCC,
            cv2.VideoWriter_fourcc(*self._configuracao.formato),
        )
        captura.set(cv2.CAP_PROP_FPS, self._configuracao.quadros_por_segundo)
        captura.set(cv2.CAP_PROP_BUFFERSIZE, self._configuracao.tamanho_buffer)

        try:
            self._backend = captura.getBackendName()
        except cv2.error:
            self._backend = "desconhecido"

        self._captura = captura
        self._parar.clear()
        self._ativa = True
        self._thread = Thread(target=self._executar, name="camera-usb", daemon=True)
        self._thread.start()

        primeiro = self._buffer.obter(timeout_s=self._configuracao.tempo_primeiro_quadro_s)
        if primeiro is None:
            erro = self._ultimo_erro or "tempo esgotado aguardando o primeiro quadro"
            self.parar()
            raise RuntimeError(f"Camera abriu, mas nao entregou imagem: {erro}")

    def parar(self) -> None:
        self._parar.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)
        captura = self._captura
        if captura is not None:
            captura.release()
        self._captura = None
        self._thread = None
        self._ativa = False

    def obter_ultimo_quadro(
        self,
        *,
        depois_de: int | None = None,
        timeout_s: float = 0.0,
    ) -> QuadroCamera | None:
        return self._buffer.obter(depois_de=depois_de, timeout_s=timeout_s)

    def obter_estado(self) -> EstadoCamera:
        agora = monotonic()
        with self._lock_estado:
            idade_ms = (
                None
                if self._ultimo_instante_s is None
                else max(0.0, (agora - self._ultimo_instante_s) * 1000.0)
            )
            fps = self._calcular_fps_medido()
            saudavel = self._ativa and idade_ms is not None and idade_ms < 1000.0
            return EstadoCamera(
                ativa=self._ativa,
                saudavel=saudavel,
                nome_perfil=self._configuracao.nome_perfil,
                nome_dispositivo=self._nome_dispositivo,
                origem=str(self._configuracao.origem),
                backend=self._backend,
                largura=self._largura_real,
                altura=self._altura_real,
                quadros_por_segundo_configurado=self._configuracao.quadros_por_segundo,
                quadros_por_segundo_medido=fps,
                total_quadros=self._total_quadros,
                total_falhas=self._total_falhas,
                ultimo_erro=self._ultimo_erro,
                idade_ultimo_quadro_ms=idade_ms,
                propriedades={
                    "rotacao_graus": self._configuracao.rotacao_graus,
                    "formato_solicitado": self._configuracao.formato,
                    "sistema": platform.system(),
                },
            )

    def _abrir_dispositivo(self) -> cv2.VideoCapture:
        origem = self._configuracao.origem
        if platform.system() == "Linux":
            return cv2.VideoCapture(origem, cv2.CAP_V4L2)
        return cv2.VideoCapture(origem)

    def _executar(self) -> None:
        captura = self._captura
        if captura is None:
            return

        while not self._parar.is_set():
            sucesso, imagem = captura.read()
            instante_s = monotonic()
            if not sucesso or imagem is None:
                with self._lock_estado:
                    self._total_falhas += 1
                    self._ultimo_erro = "falha ao ler quadro"
                sleep(0.02)
                continue

            imagem = self._aplicar_rotacao(imagem)
            metricas = calcular_metricas_imagem(
                imagem,
                limiar_escuro=self._configuracao.limiar_escuro,
                limiar_claro=self._configuracao.limiar_claro,
            )

            with self._lock_estado:
                self._total_quadros += 1
                id_quadro = self._total_quadros
                self._ultimo_instante_s = instante_s
                self._instantes_recentes.append(instante_s)
                self._ultimo_erro = ""
                self._largura_real = int(imagem.shape[1])
                self._altura_real = int(imagem.shape[0])

            quadro = QuadroCamera(
                id_quadro=id_quadro,
                instante_monotonico_s=instante_s,
                instante_utc=datetime.now(UTC).isoformat(),
                imagem_bgr=imagem,
                metricas=metricas,
            )
            self._buffer.publicar(quadro)

    def _aplicar_rotacao(self, imagem):
        rotacao = self._configuracao.rotacao_graus
        if rotacao == 90:
            return cv2.rotate(imagem, cv2.ROTATE_90_CLOCKWISE)
        if rotacao == 180:
            return cv2.rotate(imagem, cv2.ROTATE_180)
        if rotacao == 270:
            return cv2.rotate(imagem, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return imagem

    def _calcular_fps_medido(self) -> float:
        if len(self._instantes_recentes) < 2:
            return 0.0
        duracao = self._instantes_recentes[-1] - self._instantes_recentes[0]
        if duracao <= 0.0:
            return 0.0
        return (len(self._instantes_recentes) - 1) / duracao

    def _descobrir_nome_dispositivo(self) -> str:
        origem = self._configuracao.origem
        if platform.system() != "Linux":
            return f"Camera USB {origem}"

        nome_video = Path(str(origem)).name if isinstance(origem, str) else f"video{origem}"
        caminho_nome = Path("/sys/class/video4linux") / nome_video / "name"
        try:
            return caminho_nome.read_text(encoding="utf-8").strip() or nome_video
        except OSError:
            return nome_video
