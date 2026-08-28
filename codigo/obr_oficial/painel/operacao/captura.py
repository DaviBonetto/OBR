"""Captura rapida de fotos, videos e sequencias de frames para analise.

Tudo que e salvo vai para ``capturas_operacao/`` na raiz do checkout (fora do
Git). A captura usa sempre o quadro bruto da fonte, sem overlay de percepcao,
e nunca toca em atuadores.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic, sleep

from obr_oficial.dispositivos.camera_base import FonteCamera


class ErroCapturaOperacao(RuntimeError):
    """Indica que a captura nao pode ser iniciada ou concluida."""


def _pasta_do_dia(raiz: Path) -> Path:
    pasta = raiz / datetime.now().strftime("%Y-%m-%d")
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _nome_arquivo(prefixo: str, sufixo: str) -> str:
    return f"{prefixo}_{datetime.now().strftime('%H%M%S_%f')[:-3]}{sufixo}"


class CapturadorOperacao:
    """Coordena foto unica, gravacao de video e sequencia de frames."""

    def __init__(self, fonte_camera: FonteCamera, raiz: Path) -> None:
        self._fonte = fonte_camera
        self._raiz = raiz
        self._lock = Lock()
        self._parar_video = Event()
        self._parar_sequencia = Event()
        self._thread_video: Thread | None = None
        self._thread_sequencia: Thread | None = None
        self._video_ativo = False
        self._sequencia_ativa = False
        self._video_inicio: float | None = None
        self._video_arquivo: Path | None = None
        self._sequencia_alvo = 0
        self._sequencia_capturados = 0
        self._sequencia_intervalo_ms = 250
        self._sequencia_pasta: Path | None = None
        self._total_fotos = 0
        self._ultimo_arquivo: str = ""

    # ----- foto -----

    def capturar_foto(self) -> Path:
        """Salva um PNG do quadro mais recente e retorna o caminho."""

        quadro = self._fonte.obter_ultimo_quadro(timeout_s=1.5)
        if quadro is None:
            raise ErroCapturaOperacao("sem quadro disponivel na camera")
        pasta = _pasta_do_dia(self._raiz)
        caminho = pasta / _nome_arquivo("foto", ".png")
        import cv2

        if not cv2.imwrite(str(caminho), quadro.imagem_bgr):
            raise ErroCapturaOperacao(f"falha ao gravar {caminho.name}")
        with self._lock:
            self._total_fotos += 1
            self._ultimo_arquivo = str(caminho.relative_to(self._raiz))
        return caminho

    # ----- video -----

    def alternar_video(self) -> dict[str, object]:
        """Inicia ou interrompe a gravacao de video do quadro bruto."""

        with self._lock:
            if self._video_ativo:
                self._parar_video.set()
                return {
                    "video_ativo": False,
                    "mensagem": "gravacao encerrando…",
                    "arquivo": self._ultimo_arquivo,
                }
            quadro = self._fonte.obter_ultimo_quadro(timeout_s=1.5)
            if quadro is None:
                raise ErroCapturaOperacao("sem quadro disponivel na camera")
            pasta = _pasta_do_dia(self._raiz)
            caminho = pasta / _nome_arquivo("video", ".mp4")
            fps = quadro_fps(self._fonte, quadro)
            escritor = _abrir_escritor(caminho, quadro.largura, quadro.altura, fps)
            if escritor is None:
                caminho = caminho.with_suffix(".avi")
                escritor = _abrir_escritor(caminho, quadro.largura, quadro.altura, fps, "MJPG")
            if escritor is None:
                raise ErroCapturaOperacao("nenhum codificador de video disponivel")
            self._video_arquivo = caminho
            self._video_inicio = monotonic()
            self._video_ativo = True
            self._parar_video.clear()
            self._thread_video = Thread(
                target=self._gravar_video,
                args=(escritor,),
                name="captura-video",
                daemon=True,
            )
            self._thread_video.start()
            return {
                "video_ativo": True,
                "mensagem": "gravando vídeo…",
                "arquivo": str(caminho.relative_to(self._raiz)),
            }

    def _gravar_video(self, escritor) -> None:
        ultimo_id: int | None = None
        while not self._parar_video.is_set():
            quadro = self._fonte.obter_ultimo_quadro(depois_de=ultimo_id, timeout_s=0.5)
            if quadro is None:
                continue
            ultimo_id = quadro.id_quadro
            escritor.write(quadro.imagem_bgr)
        escritor.release()
        with self._lock:
            self._video_ativo = False
            self._video_inicio = None
            if self._video_arquivo is not None:
                self._ultimo_arquivo = str(self._video_arquivo.relative_to(self._raiz))
                self._video_arquivo = None

    # ----- sequencia -----

    def alternar_sequencia(self, intervalo_ms: int = 250, maximo: int = 0) -> dict[str, object]:
        """Inicia ou interrompe uma sequencia de frames espaçados."""

        intervalo = max(50, int(intervalo_ms))
        with self._lock:
            if self._sequencia_ativa:
                self._parar_sequencia.set()
                return {
                    "sequencia_ativa": False,
                    "mensagem": "sequência encerrando…",
                    "capturados": self._sequencia_capturados,
                }
            quadro = self._fonte.obter_ultimo_quadro(timeout_s=1.5)
            if quadro is None:
                raise ErroCapturaOperacao("sem quadro disponivel na camera")
            pasta = _pasta_do_dia(self._raiz) / _nome_arquivo("sequencia", "")
            pasta.mkdir(parents=True, exist_ok=True)
            self._sequencia_pasta = pasta
            self._sequencia_intervalo_ms = intervalo
            self._sequencia_alvo = max(0, int(maximo))
            self._sequencia_capturados = 0
            self._sequencia_ativa = True
            self._parar_sequencia.clear()
            self._thread_sequencia = Thread(
                target=self._capturar_sequencia,
                name="captura-sequencia",
                daemon=True,
            )
            self._thread_sequencia.start()
            return {
                "sequencia_ativa": True,
                "mensagem": "sequência em andamento…",
                "capturados": 0,
            }

    def _capturar_sequencia(self) -> None:
        import cv2

        pasta = self._sequencia_pasta
        ultimo_id: int | None = None
        while not self._parar_sequencia.is_set():
            if self._sequencia_alvo > 0 and self._sequencia_capturados >= self._sequencia_alvo:
                break
            quadro = self._fonte.obter_ultimo_quadro(depois_de=ultimo_id, timeout_s=0.5)
            if quadro is None:
                continue
            ultimo_id = quadro.id_quadro
            indice = self._sequencia_capturados + 1
            caminho = pasta / f"frame_{indice:04d}.png"
            if cv2.imwrite(str(caminho), quadro.imagem_bgr):
                with self._lock:
                    self._sequencia_capturados += 1
                    self._ultimo_arquivo = str(caminho.relative_to(self._raiz))
            sleep(self._sequencia_intervalo_ms / 1000.0)
        with self._lock:
            self._sequencia_ativa = False

    # ----- estado -----

    def estado(self) -> dict[str, object]:
        with self._lock:
            duracao_video = None
            if self._video_ativo and self._video_inicio is not None:
                duracao_video = round(monotonic() - self._video_inicio, 1)
            return {
                "video_ativo": self._video_ativo,
                "video_duracao_s": duracao_video,
                "sequencia_ativa": self._sequencia_ativa,
                "sequencia_capturados": self._sequencia_capturados,
                "sequencia_alvo": self._sequencia_alvo,
                "sequencia_intervalo_ms": self._sequencia_intervalo_ms,
                "total_fotos": self._total_fotos,
                "ultimo_arquivo": self._ultimo_arquivo,
                "pasta_raiz": self._raiz.name,
            }


def quadro_fps(fonte_camera: FonteCamera, quadro) -> float:
    """FPS para o escritor de video: medido, com fallback para o configurado."""

    estado_fonte = fonte_camera.obter_estado()
    medido = float(estado_fonte.quadros_por_segundo_medido or 0.0)
    if medido >= 1.0:
        return min(medido, 60.0)
    return max(float(estado_fonte.quadros_por_segundo_configurado or 10.0), 1.0)


def _abrir_escritor(caminho: Path, largura: int, altura: int, fps: float, fourcc: str = "mp4v"):
    import cv2

    escritor = cv2.VideoWriter(
        str(caminho),
        cv2.VideoWriter_fourcc(*fourcc),
        fps,
        (largura, altura),
    )
    if escritor.isOpened():
        return escritor
    escritor.release()
    return None
