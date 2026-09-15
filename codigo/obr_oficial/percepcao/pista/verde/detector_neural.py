"""Inferencia ONNX dos marcadores verdes no quadro inteiro."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from time import perf_counter

import cv2
import numpy as np

from obr_oficial.nucleo.contratos import PontoNormalizado
from obr_oficial.percepcao.pista.verde.configuracao import ConfiguracaoDetectorVerde
from obr_oficial.percepcao.pista.verde.geometria import CandidatoMarcadorVerde


class ErroDetectorVerde(RuntimeError):
    """Indica falha de integridade, entrada ou inferencia do detector verde."""


@dataclass(frozen=True, slots=True)
class ResultadoDetectorVerde:
    """Mascara e componentes observados no mesmo quadro da linha."""

    probabilidade: np.ndarray
    mascara: np.ndarray
    candidatos: tuple[CandidatoMarcadorVerde, ...]
    pre_processamento_ms: float
    inferencia_ms: float


def _sha256_arquivo(caminho: str) -> str:
    resumo = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def preprocessar_quadro_verde(
    quadro_bgr: np.ndarray,
    configuracao: ConfiguracaoDetectorVerde,
) -> np.ndarray:
    """Replica a entrada RGB normalizada do treinamento verde."""

    if quadro_bgr.ndim != 3 or quadro_bgr.shape[2] != 3 or quadro_bgr.size == 0:
        raise ErroDetectorVerde("quadro verde deve ser BGR nao vazio com tres canais")
    imagem = cv2.resize(
        quadro_bgr,
        (configuracao.largura, configuracao.altura),
        interpolation=cv2.INTER_AREA,
    )
    rgb = cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    rgb = (rgb - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array(
        [0.229, 0.224, 0.225],
        dtype=np.float32,
    )
    return np.ascontiguousarray(np.transpose(rgb, (2, 0, 1))[None], dtype=np.float32)


def _sigmoid(logits: np.ndarray) -> np.ndarray:
    positivos = logits >= 0
    resultado = np.empty_like(logits, dtype=np.float32)
    resultado[positivos] = 1.0 / (1.0 + np.exp(-logits[positivos]))
    exp_negativos = np.exp(logits[~positivos])
    resultado[~positivos] = exp_negativos / (1.0 + exp_negativos)
    return resultado


class DetectorNeuralVerde:
    """Executa o ONNX verde e devolve componentes, sem decidir movimento."""

    def __init__(
        self,
        configuracao: ConfiguracaoDetectorVerde,
        *,
        sessao: object | None = None,
    ) -> None:
        self.configuracao = configuracao
        if sessao is None:
            caminho = configuracao.arquivo_modelo
            if not caminho.is_file():
                raise ErroDetectorVerde(f"modelo ONNX verde ausente: {caminho}")
            obtido = _sha256_arquivo(str(caminho))
            if obtido.lower() != configuracao.sha256_modelo:
                raise ErroDetectorVerde("SHA-256 do ONNX verde diverge do manifesto")
            try:
                import onnxruntime as ort
            except (ImportError, ModuleNotFoundError) as erro:
                raise ErroDetectorVerde("ONNX Runtime nao esta instalado") from erro
            opcoes = ort.SessionOptions()
            opcoes.intra_op_num_threads = configuracao.threads_onnx
            opcoes.inter_op_num_threads = 1
            opcoes.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            sessao = ort.InferenceSession(
                str(caminho),
                sess_options=opcoes,
                providers=["CPUExecutionProvider"],
            )
        self._sessao = sessao

    def processar(self, quadro_bgr: np.ndarray) -> ResultadoDetectorVerde:
        """Segmenta e mede cada componente sem fundir a semantica com a linha."""

        inicio = perf_counter()
        entrada = preprocessar_quadro_verde(quadro_bgr, self.configuracao)
        apos_pre = perf_counter()
        try:
            logits = np.asarray(
                self._sessao.run(["logits"], {"imagem": entrada})[0], dtype=np.float32
            )
        except Exception as erro:
            raise ErroDetectorVerde(f"falha na inferencia ONNX verde: {erro}") from erro
        apos_inferencia = perf_counter()
        forma = (1, 1, self.configuracao.altura, self.configuracao.largura)
        if logits.shape != forma:
            raise ErroDetectorVerde(
                f"saida ONNX verde invalida: esperado {forma}, obtido {logits.shape}"
            )
        probabilidade = _sigmoid(logits[0, 0])
        mascara_modelo = np.where(
            probabilidade >= self.configuracao.limiar_mascara,
            255,
            0,
        ).astype(np.uint8)
        altura, largura = quadro_bgr.shape[:2]
        mascara = cv2.resize(mascara_modelo, (largura, altura), interpolation=cv2.INTER_NEAREST)
        probabilidade_quadro = cv2.resize(
            probabilidade,
            (largura, altura),
            interpolation=cv2.INTER_LINEAR,
        )
        candidatos = self._extrair_componentes(mascara, probabilidade_quadro)
        return ResultadoDetectorVerde(
            probabilidade=probabilidade_quadro,
            mascara=mascara,
            candidatos=candidatos,
            pre_processamento_ms=(apos_pre - inicio) * 1000.0,
            inferencia_ms=(apos_inferencia - apos_pre) * 1000.0,
        )

    @staticmethod
    def _extrair_componentes(
        mascara: np.ndarray,
        probabilidade: np.ndarray,
    ) -> tuple[CandidatoMarcadorVerde, ...]:
        quantidade, rotulos, estatisticas, centroides = cv2.connectedComponentsWithStats(
            mascara,
            connectivity=8,
        )
        altura, largura = mascara.shape
        area_quadro = float(altura * largura)
        candidatos = []
        for rotulo in range(1, quantidade):
            area = int(estatisticas[rotulo, cv2.CC_STAT_AREA])
            if area == 0:
                continue
            pixels = rotulos == rotulo
            x, y = centroides[rotulo]
            candidatos.append(
                CandidatoMarcadorVerde(
                    centro=PontoNormalizado(
                        x=float(np.clip(x / max(1, largura - 1), 0.0, 1.0)),
                        y=float(np.clip(y / max(1, altura - 1), 0.0, 1.0)),
                    ),
                    confianca=float(np.mean(probabilidade[pixels])),
                    area_normalizada=area / area_quadro,
                )
            )
        return tuple(candidatos)
