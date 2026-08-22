"""Deteccao, geometria e rastreamento da linha da pista."""

from obr_oficial.percepcao.linha.detector_classico import (
    ConfiguracaoDetectorClassico,
    DetectorClassicoLinha,
    ResultadoDetectorClassico,
    carregar_configuracao_detector_classico,
)
from obr_oficial.percepcao.linha.detector_neural import (
    ConfiguracaoDetectorNeural,
    DetectorNeuralLinha,
    DiagnosticoGeometria,
    ErroDetectorNeural,
    ExtratorGeometriaLinha,
    ResultadoDetectorNeural,
    carregar_configuracao_detector_neural,
    preprocessar_quadro,
)
from obr_oficial.percepcao.linha.execucao_continua import (
    EstadoProcessadorLinha,
    ProcessadorContinuoLinha,
    ResultadoQuadroLinha,
    desenhar_sobreposicao,
    estimativa_como_dict,
)
from obr_oficial.percepcao.linha.rastreamento import RastreadorLinha

__all__ = [
    "ConfiguracaoDetectorClassico",
    "ConfiguracaoDetectorNeural",
    "DetectorClassicoLinha",
    "DetectorNeuralLinha",
    "DiagnosticoGeometria",
    "ErroDetectorNeural",
    "EstadoProcessadorLinha",
    "ExtratorGeometriaLinha",
    "ProcessadorContinuoLinha",
    "RastreadorLinha",
    "ResultadoDetectorClassico",
    "ResultadoDetectorNeural",
    "ResultadoQuadroLinha",
    "carregar_configuracao_detector_classico",
    "carregar_configuracao_detector_neural",
    "desenhar_sobreposicao",
    "estimativa_como_dict",
    "preprocessar_quadro",
]
