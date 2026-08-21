"""Contratos das fontes de imagem, independentes do modelo da camera."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Protocol

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class MetricasImagem:
    """Indicadores simples para encontrar capturas tecnicamente ruins."""

    brilho_medio: float
    percentual_escuro: float
    percentual_claro: float
    nitidez_laplaciano: float

    def como_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class QuadroCamera:
    """Um quadro com identidade e tempos preservados."""

    id_quadro: int
    instante_monotonico_s: float
    instante_utc: str
    imagem_bgr: NDArray[np.uint8] = field(repr=False)
    metricas: MetricasImagem

    @property
    def largura(self) -> int:
        return int(self.imagem_bgr.shape[1])

    @property
    def altura(self) -> int:
        return int(self.imagem_bgr.shape[0])


@dataclass(frozen=True, slots=True)
class EstadoCamera:
    """Estado serializavel exibido no painel e salvo nos manifestos."""

    ativa: bool
    saudavel: bool
    nome_perfil: str
    nome_dispositivo: str
    origem: str
    backend: str
    largura: int
    altura: int
    quadros_por_segundo_configurado: float
    quadros_por_segundo_medido: float
    total_quadros: int
    total_falhas: int
    ultimo_erro: str
    idade_ultimo_quadro_ms: float | None
    propriedades: dict[str, str | int | float | bool | None] = field(default_factory=dict)

    def como_dict(self) -> dict[str, object]:
        return asdict(self)


class FonteCamera(Protocol):
    """Interface pequena que permite trocar camera sem alterar consumidores."""

    def iniciar(self) -> None:
        """Abre a fonte e aguarda o primeiro quadro valido."""

    def parar(self) -> None:
        """Interrompe a fonte e libera recursos."""

    def obter_ultimo_quadro(
        self,
        *,
        depois_de: int | None = None,
        timeout_s: float = 0.0,
    ) -> QuadroCamera | None:
        """Retorna uma copia do quadro mais recente, nunca uma fila antiga."""

    def obter_estado(self) -> EstadoCamera:
        """Retorna informacoes atuais da fonte."""
