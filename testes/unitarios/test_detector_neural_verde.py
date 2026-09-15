from pathlib import Path

import numpy as np

from obr_oficial.percepcao.pista.verde.configuracao import ConfiguracaoDetectorVerde
from obr_oficial.percepcao.pista.verde.detector_neural import DetectorNeuralVerde


class _SessaoVerde:
    def __init__(self) -> None:
        probabilidade = np.full((240, 320), 0.01, dtype=np.float32)
        probabilidade[150:210, 40:100] = 0.98
        probabilidade[30:75, 230:275] = 0.95
        self.logits = np.log(probabilidade / (1.0 - probabilidade))[None, None]

    def run(self, _saidas, _entradas):
        return [self.logits]


def _configuracao(tmp_path: Path) -> ConfiguracaoDetectorVerde:
    return ConfiguracaoDetectorVerde(
        arquivo_modelo=tmp_path / "verde.onnx",
        sha256_modelo="0" * 64,
        largura=320,
        altura=240,
        limiar_mascara=0.75,
    )


def test_detecta_componentes_verdes_no_quadro_inteiro(tmp_path: Path) -> None:
    detector = DetectorNeuralVerde(_configuracao(tmp_path), sessao=_SessaoVerde())
    quadro = np.full((120, 160, 3), 180, dtype=np.uint8)

    resultado = detector.processar(quadro)

    assert resultado.mascara.shape == (120, 160)
    assert len(resultado.candidatos) == 2
    assert max(candidato.confianca for candidato in resultado.candidatos) > 0.97
    assert any(
        candidato.centro.x < 0.35 and candidato.centro.y > 0.60
        for candidato in resultado.candidatos
    )
    assert resultado.pre_processamento_ms >= 0.0
    assert resultado.inferencia_ms >= 0.0
