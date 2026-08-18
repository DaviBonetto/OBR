"""Contratos imutaveis compartilhados pela percepcao, painel e futuro controle."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite


class EstadoDeteccao(StrEnum):
    """Qualidade logica da deteccao no quadro atual."""

    ENCONTRADA = "encontrada"
    INCERTA = "incerta"
    PERDIDA = "perdida"


class FonteEstimativa(StrEnum):
    """Origem da evidencia usada na estimativa."""

    NENHUMA = "nenhuma"
    IA = "ia"
    CLASSICA = "classica"
    HIBRIDA = "hibrida"
    TEMPORAL = "temporal"


class TipoCurva(StrEnum):
    """Classificacao geometrica simples da trajetoria observada."""

    INDEFINIDA = "indefinida"
    RETA = "reta"
    ESQUERDA_SUAVE = "esquerda_suave"
    DIREITA_SUAVE = "direita_suave"
    ESQUERDA_FECHADA = "esquerda_fechada"
    DIREITA_FECHADA = "direita_fechada"


def _exigir_finito(nome: str, valor: float) -> None:
    if not isfinite(valor):
        raise ValueError(f"{nome} deve ser finito")


def _exigir_intervalo(nome: str, valor: float, minimo: float, maximo: float) -> None:
    _exigir_finito(nome, valor)
    if not minimo <= valor <= maximo:
        raise ValueError(f"{nome} deve estar entre {minimo} e {maximo}")


@dataclass(frozen=True, slots=True)
class PontoNormalizado:
    """Ponto independente da resolucao, com origem no canto superior esquerdo."""

    x: float
    y: float

    def __post_init__(self) -> None:
        _exigir_intervalo("x", self.x, 0.0, 1.0)
        _exigir_intervalo("y", self.y, 0.0, 1.0)


@dataclass(frozen=True, slots=True)
class TemposProcessamento:
    """Latencias das etapas de um quadro, expressas em milissegundos."""

    pre_processamento_ms: float = 0.0
    inferencia_ms: float = 0.0
    geometria_ms: float = 0.0
    rastreamento_ms: float = 0.0

    def __post_init__(self) -> None:
        for nome, valor in (
            ("pre_processamento_ms", self.pre_processamento_ms),
            ("inferencia_ms", self.inferencia_ms),
            ("geometria_ms", self.geometria_ms),
            ("rastreamento_ms", self.rastreamento_ms),
        ):
            _exigir_finito(nome, valor)
            if valor < 0.0:
                raise ValueError(f"{nome} nao pode ser negativo")

    @property
    def total_ms(self) -> float:
        """Soma das etapas monitoradas do processamento."""

        return (
            self.pre_processamento_ms
            + self.inferencia_ms
            + self.geometria_ms
            + self.rastreamento_ms
        )


@dataclass(frozen=True, slots=True)
class EstimativaLinha:
    """Saida unica e independente da implementacao interna do detector."""

    id_quadro: int
    instante_monotonico_s: float
    estado: EstadoDeteccao
    confianca: float
    centro_linha: tuple[PontoNormalizado, ...] = field(default_factory=tuple)
    ponto_atual: PontoNormalizado | None = None
    ponto_objetivo: PontoNormalizado | None = None
    erro_lateral_normalizado: float | None = None
    erro_angular_graus: float | None = None
    curvatura_normalizada: float | None = None
    tipo_curva: TipoCurva = TipoCurva.INDEFINIDA
    fonte: FonteEstimativa = FonteEstimativa.NENHUMA
    idade_observacao_ms: float = 0.0
    motivo: str = ""
    tempos: TemposProcessamento = field(default_factory=TemposProcessamento)

    def __post_init__(self) -> None:
        if self.id_quadro < 0:
            raise ValueError("id_quadro nao pode ser negativo")
        _exigir_finito("instante_monotonico_s", self.instante_monotonico_s)
        if self.instante_monotonico_s < 0.0:
            raise ValueError("instante_monotonico_s nao pode ser negativo")

        _exigir_intervalo("confianca", self.confianca, 0.0, 1.0)
        _exigir_finito("idade_observacao_ms", self.idade_observacao_ms)
        if self.idade_observacao_ms < 0.0:
            raise ValueError("idade_observacao_ms nao pode ser negativa")

        if not isinstance(self.centro_linha, tuple):
            raise TypeError("centro_linha deve ser uma tupla imutavel")

        if self.erro_lateral_normalizado is not None:
            _exigir_intervalo(
                "erro_lateral_normalizado", self.erro_lateral_normalizado, -1.0, 1.0
            )
        if self.erro_angular_graus is not None:
            _exigir_finito("erro_angular_graus", self.erro_angular_graus)
        if self.curvatura_normalizada is not None:
            _exigir_intervalo(
                "curvatura_normalizada", self.curvatura_normalizada, -1.0, 1.0
            )

        if self.estado is EstadoDeteccao.ENCONTRADA:
            if len(self.centro_linha) < 2:
                raise ValueError("Linha encontrada exige ao menos dois pontos centrais")
            if self.ponto_atual is None or self.ponto_objetivo is None:
                raise ValueError("Linha encontrada exige ponto atual e ponto objetivo")
