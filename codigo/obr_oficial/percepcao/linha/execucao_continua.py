"""Processamento continuo da linha consumindo sempre o quadro mais recente."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from itertools import pairwise
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


def _criar_mascara_visual(
    probabilidade: np.ndarray,
    largura: int,
    altura: int,
    limiar: float,
) -> np.ndarray:
    """Suaviza apenas a apresentacao; a mascara logica permanece intocada."""

    ampliada = cv2.resize(
        probabilidade,
        (largura, altura),
        interpolation=cv2.INTER_LINEAR,
    )
    suave = cv2.GaussianBlur(ampliada, (0, 0), sigmaX=1.15, sigmaY=1.15)
    mascara = np.where(suave >= limiar, 255, 0).astype(np.uint8)
    nucleo = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    return cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, nucleo)


def _aplicar_mascara_gradiente(regiao: np.ndarray, mascara: np.ndarray) -> None:
    """Aplica azul no horizonte e ciano perto do robo com borda antialias."""

    altura, largura = mascara.shape
    progresso = np.linspace(0.0, 1.0, altura, dtype=np.float32)[:, None, None]
    cor_distante = np.array([165.0, 55.0, 10.0], dtype=np.float32)
    cor_proxima = np.array([245.0, 215.0, 0.0], dtype=np.float32)
    cores = cor_distante * (1.0 - progresso) + cor_proxima * progresso
    cores = np.broadcast_to(cores, (altura, largura, 3))
    base = regiao.astype(np.float32)
    preenchimento = (mascara.astype(np.float32) / 255.0)[..., None] * 0.22
    base = base * (1.0 - preenchimento) + cores * preenchimento

    nucleo = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    borda = cv2.morphologyEx(mascara, cv2.MORPH_GRADIENT, nucleo)
    alpha_borda = cv2.GaussianBlur(borda, (0, 0), sigmaX=0.8).astype(np.float32)
    alpha_borda = (alpha_borda / 255.0 * 0.92)[..., None]
    base = base * (1.0 - alpha_borda) + cores * alpha_borda
    regiao[:] = np.clip(base, 0, 255).astype(np.uint8)


def _suavizar_polilinha(pontos: np.ndarray, repeticoes: int = 2) -> np.ndarray:
    """Cria uma curva visual continua sem alterar os pontos usados pelo controle."""

    if len(pontos) < 3:
        return pontos.astype(np.int32)
    suaves = pontos.astype(np.float32)
    for _ in range(repeticoes):
        refinados = [suaves[0]]
        for inicio, fim in pairwise(suaves):
            refinados.extend((0.75 * inicio + 0.25 * fim, 0.25 * inicio + 0.75 * fim))
        refinados.append(suaves[-1])
        suaves = np.asarray(refinados, dtype=np.float32)
    return np.rint(suaves).astype(np.int32)


def _desenhar_marcador(
    imagem: np.ndarray,
    centro: tuple[int, int],
    cor: tuple[int, int, int],
) -> None:
    halo = imagem.copy()
    cv2.circle(halo, centro, 20, cor, -1, cv2.LINE_AA)
    cv2.addWeighted(halo, 0.24, imagem, 0.76, 0.0, dst=imagem)
    cv2.circle(imagem, centro, 13, (8, 10, 12), -1, cv2.LINE_AA)
    cv2.circle(imagem, centro, 12, (255, 255, 255), -1, cv2.LINE_AA)
    cv2.circle(imagem, centro, 9, cor, -1, cv2.LINE_AA)
    cv2.circle(imagem, centro, 3, (255, 255, 255), -1, cv2.LINE_AA)


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
    mascara_visual = _criar_mascara_visual(
        resultado.probabilidade,
        largura,
        altura_roi,
        configuracao.limiar_mascara,
    )
    regiao = imagem[y0:]
    _aplicar_mascara_gradiente(regiao, mascara_visual)

    def pixel(ponto: PontoNormalizado) -> tuple[int, int]:
        return (
            round(ponto.x * (largura - 1)),
            round(y0 + ponto.y * max(1, altura_roi - 1)),
        )

    if estimativa.ponto_atual is not None and estimativa.ponto_objetivo is not None:
        atual = pixel(estimativa.ponto_atual)
        objetivo = pixel(estimativa.ponto_objetivo)
        pontos = estimativa.centro_linha
        if len(pontos) >= 2:
            indice_atual = min(
                range(len(pontos)),
                key=lambda indice: abs(pontos[indice].y - estimativa.ponto_atual.y),
            )
            indice_objetivo = min(
                range(len(pontos)),
                key=lambda indice: abs(pontos[indice].y - estimativa.ponto_objetivo.y),
            )
            if indice_objetivo <= indice_atual:
                trecho = list(pontos[indice_objetivo : indice_atual + 1])
            else:
                trecho = list(reversed(pontos[indice_atual : indice_objetivo + 1]))
            centro_bruto = np.array([pixel(ponto) for ponto in trecho], dtype=np.int32)
            centro_bruto[0] = objetivo
            centro_bruto[-1] = atual
            centro = _suavizar_polilinha(centro_bruto)
            cv2.polylines(imagem, [centro], False, (4, 5, 7), 7, cv2.LINE_AA)
            cv2.polylines(imagem, [centro], False, (35, 45, 245), 3, cv2.LINE_AA)
        _desenhar_marcador(imagem, objetivo, (165, 55, 10))
        _desenhar_marcador(imagem, atual, (255, 230, 0))
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
