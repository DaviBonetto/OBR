"""Calculo leve de qualidade tecnica para cada quadro capturado."""

from __future__ import annotations

import cv2
import numpy as np
from numpy.typing import NDArray

from obr_oficial.dispositivos.camera_base import MetricasImagem


def calcular_metricas_imagem(
    imagem_bgr: NDArray[np.uint8],
    *,
    limiar_escuro: int = 10,
    limiar_claro: int = 245,
) -> MetricasImagem:
    """Mede brilho, saturacao nas extremidades e nitidez sem alterar a imagem."""

    if imagem_bgr.ndim != 3 or imagem_bgr.shape[2] != 3:
        raise ValueError("imagem_bgr deve possuir formato altura x largura x 3")

    cinza = cv2.cvtColor(imagem_bgr, cv2.COLOR_BGR2GRAY)
    quantidade = float(cinza.size)
    percentual_escuro = float(np.count_nonzero(cinza <= limiar_escuro) * 100.0 / quantidade)
    percentual_claro = float(np.count_nonzero(cinza >= limiar_claro) * 100.0 / quantidade)
    nitidez = float(cv2.Laplacian(cinza, cv2.CV_64F).var())

    return MetricasImagem(
        brilho_medio=float(cinza.mean()),
        percentual_escuro=percentual_escuro,
        percentual_claro=percentual_claro,
        nitidez_laplaciano=nitidez,
    )
