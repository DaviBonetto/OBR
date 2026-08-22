"""Processamento continuo da linha consumindo sempre o quadro mais recente."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from threading import Condition, Event, Lock, Thread
from time import monotonic

import cv2
import numpy as np

from obr_oficial.dispositivos.camera_base import FonteCamera, QuadroCamera
from obr_oficial.nucleo.contratos import EstimativaLinha, PontoNormalizado
from obr_oficial.percepcao.linha.detector_neural import (
    ConfiguracaoDetectorNeural,
    DetectorNeuralLinha,
    DiagnosticoGeometria,
    ResultadoDetectorNeural,
)
from obr_oficial.percepcao.linha.rastreamento import RastreadorLinha


@dataclass(frozen=True, slots=True)
class ResultadoQuadroLinha:
    """Quadro pronto para observabilidade, separado do caminho de controle."""

    id_quadro: int
    instante_monotonico_s: float
    imagem_sobreposta: np.ndarray
    mascara: np.ndarray
    estimativa: EstimativaLinha
    diagnostico: DiagnosticoGeometria


@dataclass(frozen=True, slots=True)
class EstadoProcessadorLinha:
    """Saude e desempenho serializaveis do processamento continuo."""

    ativo: bool
    saudavel: bool
    total_processados: int
    total_falhas: int
    quadros_por_segundo: float
    ultimo_id_quadro: int | None
    idade_ultimo_resultado_ms: float | None
    ultimo_erro: str

    def como_dict(self) -> dict[str, object]:
        return asdict(self)


def estimativa_como_dict(estimativa: EstimativaLinha) -> dict[str, object]:
    """Serializa o contrato sem expor tensores ou objetos internos do modelo."""

    def ponto(valor: PontoNormalizado | None) -> dict[str, float] | None:
        return None if valor is None else {"x": valor.x, "y": valor.y}

    return {
        "id_quadro": estimativa.id_quadro,
        "instante_monotonico_s": estimativa.instante_monotonico_s,
        "estado": estimativa.estado.value,
        "confianca": estimativa.confianca,
        "centro_linha": [ponto(item) for item in estimativa.centro_linha],
        "ponto_atual": ponto(estimativa.ponto_atual),
        "ponto_objetivo": ponto(estimativa.ponto_objetivo),
        "erro_lateral_normalizado": estimativa.erro_lateral_normalizado,
        "erro_angular_graus": estimativa.erro_angular_graus,
        "curvatura_normalizada": estimativa.curvatura_normalizada,
        "tipo_curva": estimativa.tipo_curva.value,
        "fonte": estimativa.fonte.value,
        "idade_observacao_ms": estimativa.idade_observacao_ms,
        "motivo": estimativa.motivo,
        "tempos": {
            "pre_processamento_ms": estimativa.tempos.pre_processamento_ms,
            "inferencia_ms": estimativa.tempos.inferencia_ms,
            "geometria_ms": estimativa.tempos.geometria_ms,
            "rastreamento_ms": estimativa.tempos.rastreamento_ms,
            "total_ms": estimativa.tempos.total_ms,
        },
    }


def desenhar_sobreposicao(
    quadro_bgr: np.ndarray,
    resultado: ResultadoDetectorNeural,
    estimativa: EstimativaLinha,
    configuracao: ConfiguracaoDetectorNeural,
) -> np.ndarray:
    """Desenha mascara, centro, posicao atual ciano e objetivo azul-escuro."""

    imagem = quadro_bgr.copy()
    altura, largura = imagem.shape[:2]
    y0 = round(altura * configuracao.roi_y)
    altura_roi = altura - y0
    mascara = cv2.resize(
        resultado.mascara,
        (largura, altura_roi),
        interpolation=cv2.INTER_NEAREST,
    )
    regiao = imagem[y0:]
    camada = np.zeros_like(regiao)
    camada[mascara > 0] = (125, 45, 0)
    cv2.addWeighted(camada, 0.38, regiao, 1.0, 0.0, dst=regiao)
    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(regiao, contornos, -1, (255, 105, 15), 2, cv2.LINE_AA)

    def pixel(ponto: PontoNormalizado) -> tuple[int, int]:
        return (
            round(ponto.x * (largura - 1)),
            round(y0 + ponto.y * max(1, altura_roi - 1)),
        )

    if len(estimativa.centro_linha) >= 2:
        centro = np.array([pixel(ponto) for ponto in estimativa.centro_linha], dtype=np.int32)
        cv2.polylines(imagem, [centro], False, (35, 55, 245), 3, cv2.LINE_AA)
    if estimativa.ponto_atual is not None and estimativa.ponto_objetivo is not None:
        atual = pixel(estimativa.ponto_atual)
        objetivo = pixel(estimativa.ponto_objetivo)
        cv2.line(imagem, atual, objetivo, (210, 80, 10), 3, cv2.LINE_AA)
        cv2.circle(imagem, objetivo, 9, (170, 55, 0), -1, cv2.LINE_AA)
        cv2.circle(imagem, objetivo, 12, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.circle(imagem, atual, 9, (255, 255, 0), -1, cv2.LINE_AA)
        cv2.circle(imagem, atual, 12, (255, 255, 255), 2, cv2.LINE_AA)
    return imagem


class ProcessadorContinuoLinha:
    """Thread independente que descarta quadros antigos e publica o ultimo resultado."""

    def __init__(
        self,
        fonte_camera: FonteCamera,
        detector: DetectorNeuralLinha,
        rastreador: RastreadorLinha,
    ) -> None:
        self._fonte = fonte_camera
        self._detector = detector
        self._rastreador = rastreador
        self._condicao = Condition()
        self._lock_estado = Lock()
        self._parar = Event()
        self._thread: Thread | None = None
        self._ultimo: ResultadoQuadroLinha | None = None
        self._total_processados = 0
        self._total_falhas = 0
        self._ultimo_erro = ""
        self._instantes: deque[float] = deque(maxlen=90)

    def iniciar(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._parar.clear()
        self._rastreador.reiniciar()
        self._thread = Thread(target=self._executar, name="percepcao-linha", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        self._thread = None

    def obter_ultimo_resultado(
        self,
        *,
        depois_de: int | None = None,
        timeout_s: float = 0.0,
    ) -> ResultadoQuadroLinha | None:
        limite = monotonic() + max(0.0, timeout_s)
        with self._condicao:
            while self._ultimo is None or (
                depois_de is not None and self._ultimo.id_quadro <= depois_de
            ):
                restante = limite - monotonic()
                if restante <= 0.0:
                    return None
                self._condicao.wait(restante)
            return self._ultimo

    def obter_estado(self) -> EstadoProcessadorLinha:
        with self._lock_estado:
            ativo = self._thread is not None and self._thread.is_alive()
            idade = None
            ultimo_id = None
            if self._ultimo is not None:
                idade = (monotonic() - self._ultimo.instante_monotonico_s) * 1000.0
                ultimo_id = self._ultimo.id_quadro
            fps = 0.0
            if len(self._instantes) >= 2:
                duracao = self._instantes[-1] - self._instantes[0]
                if duracao > 0.0:
                    fps = (len(self._instantes) - 1) / duracao
            saudavel = ativo and idade is not None and idade < 1000.0 and not self._ultimo_erro
            return EstadoProcessadorLinha(
                ativo=ativo,
                saudavel=saudavel,
                total_processados=self._total_processados,
                total_falhas=self._total_falhas,
                quadros_por_segundo=fps,
                ultimo_id_quadro=ultimo_id,
                idade_ultimo_resultado_ms=idade,
                ultimo_erro=self._ultimo_erro,
            )

    def _executar(self) -> None:
        ultimo_id: int | None = None
        while not self._parar.is_set():
            quadro = self._fonte.obter_ultimo_quadro(depois_de=ultimo_id, timeout_s=0.5)
            if quadro is None:
                continue
            ultimo_id = quadro.id_quadro
            try:
                self._processar_quadro(quadro)
            except Exception as erro:
                with self._lock_estado:
                    self._total_falhas += 1
                    self._ultimo_erro = str(erro)

    def _processar_quadro(self, quadro: QuadroCamera) -> None:
        resultado = self._detector.processar(
            quadro.imagem_bgr,
            id_quadro=quadro.id_quadro,
            instante_monotonico_s=quadro.instante_monotonico_s,
        )
        estimativa = self._rastreador.atualizar(resultado.estimativa)
        sobreposta = desenhar_sobreposicao(
            quadro.imagem_bgr,
            resultado,
            estimativa,
            self._detector.configuracao,
        )
        publicado = ResultadoQuadroLinha(
            id_quadro=quadro.id_quadro,
            instante_monotonico_s=quadro.instante_monotonico_s,
            imagem_sobreposta=sobreposta,
            mascara=resultado.mascara,
            estimativa=estimativa,
            diagnostico=resultado.diagnostico,
        )
        with self._condicao:
            self._ultimo = publicado
            self._condicao.notify_all()
        with self._lock_estado:
            self._total_processados += 1
            self._ultimo_erro = ""
            self._instantes.append(monotonic())
