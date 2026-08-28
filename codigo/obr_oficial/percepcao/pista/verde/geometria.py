"""Interpretacao deterministica de verde no referencial local da intersecao."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite
from time import perf_counter

from obr_oficial.nucleo.contratos import (
    DecisaoVerde,
    EstadoVerde,
    EstimativaVerde,
    FonteEstimativa,
    MarcadorVerde,
    PontoNormalizado,
    PosicaoMarcadorVerde,
    TemposProcessamento,
)
from obr_oficial.percepcao.pista.verde.configuracao import ConfiguracaoGeometriaVerde


@dataclass(frozen=True, slots=True)
class CandidatoMarcadorVerde:
    """Componente segmentado antes da validacao geometrica."""

    centro: PontoNormalizado
    confianca: float
    area_normalizada: float

    def __post_init__(self) -> None:
        if not isfinite(self.confianca) or not isfinite(self.area_normalizada):
            raise ValueError("confianca e area_normalizada devem ser finitas")
        if not 0.0 <= self.confianca <= 1.0:
            raise ValueError("confianca deve estar entre zero e um")
        if not 0.0 <= self.area_normalizada <= 1.0:
            raise ValueError("area_normalizada deve estar entre zero e um")


@dataclass(frozen=True, slots=True)
class ReferencialIntersecao:
    """Centro e vetor unitario apontando para depois da intersecao."""

    centro: PontoNormalizado
    direcao_avanco_x: float
    direcao_avanco_y: float

    def __post_init__(self) -> None:
        if not isfinite(self.direcao_avanco_x) or not isfinite(self.direcao_avanco_y):
            raise ValueError("direcao de avanco deve ser finita")
        if hypot(self.direcao_avanco_x, self.direcao_avanco_y) <= 1e-9:
            raise ValueError("direcao de avanco nao pode ser nula")

    @property
    def direcao_unitaria(self) -> tuple[float, float]:
        norma = hypot(self.direcao_avanco_x, self.direcao_avanco_y)
        return self.direcao_avanco_x / norma, self.direcao_avanco_y / norma

    @property
    def esquerda_unitaria(self) -> tuple[float, float]:
        """Vetor para a esquerda considerando coordenadas de imagem (y cresce para baixo)."""

        dx, dy = self.direcao_unitaria
        return dy, -dx


class InterpretadorGeometricoVerde:
    """Converte candidatos em intencao sem controlar motores ou substituir a linha."""

    def __init__(self, configuracao: ConfiguracaoGeometriaVerde) -> None:
        self._configuracao = configuracao

    def interpretar(
        self,
        candidatos: tuple[CandidatoMarcadorVerde, ...],
        referencial: ReferencialIntersecao,
        *,
        id_quadro: int,
        instante_monotonico_s: float,
        fonte: FonteEstimativa = FonteEstimativa.IA,
    ) -> EstimativaVerde:
        """Classifica antes/depois e lado; a confirmacao temporal vem em fase posterior."""

        inicio = perf_counter()
        marcadores = tuple(self._classificar(candidato, referencial) for candidato in candidatos)
        esquerdas = tuple(
            marcador
            for marcador in marcadores
            if marcador.posicao is PosicaoMarcadorVerde.ANTES_ESQUERDA
        )
        direitas = tuple(
            marcador
            for marcador in marcadores
            if marcador.posicao is PosicaoMarcadorVerde.ANTES_DIREITA
        )

        decisao = DecisaoVerde.NENHUMA
        estado = EstadoVerde.AUSENTE
        confianca = 0.0
        motivo = "sem_marcador_verde"
        if esquerdas and direitas:
            decisao = DecisaoVerde.RETORNAR_180
            estado = EstadoVerde.CANDIDATA
            confianca = min(
                max(marcador.confianca for marcador in esquerdas),
                max(marcador.confianca for marcador in direitas),
            )
            motivo = "dois_marcadores_antes_em_lados_opostos"
        elif esquerdas:
            decisao = DecisaoVerde.VIRAR_ESQUERDA
            estado = EstadoVerde.CANDIDATA
            confianca = max(marcador.confianca for marcador in esquerdas)
            motivo = "marcador_valido_antes_a_esquerda"
        elif direitas:
            decisao = DecisaoVerde.VIRAR_DIREITA
            estado = EstadoVerde.CANDIDATA
            confianca = max(marcador.confianca for marcador in direitas)
            motivo = "marcador_valido_antes_a_direita"
        elif any(marcador.posicao is PosicaoMarcadorVerde.AMBIGUA for marcador in marcadores):
            estado = EstadoVerde.AMBIGUA
            confianca = max((marcador.confianca for marcador in marcadores), default=0.0)
            motivo = "marcadores_sem_posicao_geometrica_valida"
        elif marcadores:
            motivo = "somente_marcadores_depois_ignorados"

        tempo_geometria = (perf_counter() - inicio) * 1_000.0
        return EstimativaVerde(
            id_quadro=id_quadro,
            instante_monotonico_s=instante_monotonico_s,
            estado=estado,
            decisao=decisao,
            confianca=confianca,
            marcadores=marcadores,
            fonte=fonte if marcadores else FonteEstimativa.NENHUMA,
            motivo=motivo,
            tempos=TemposProcessamento(geometria_ms=tempo_geometria),
        )

    def _classificar(
        self,
        candidato: CandidatoMarcadorVerde,
        referencial: ReferencialIntersecao,
    ) -> MarcadorVerde:
        cfg = self._configuracao
        delta_x = candidato.centro.x - referencial.centro.x
        delta_y = candidato.centro.y - referencial.centro.y
        avanco_x, avanco_y = referencial.direcao_unitaria
        esquerda_x, esquerda_y = referencial.esquerda_unitaria
        longitudinal = delta_x * avanco_x + delta_y * avanco_y
        lateral = delta_x * esquerda_x + delta_y * esquerda_y

        posicao = PosicaoMarcadorVerde.AMBIGUA
        candidato_plausivel = (
            candidato.confianca >= cfg.confianca_minima
            and cfg.area_normalizada_minima
            <= candidato.area_normalizada
            <= cfg.area_normalizada_maxima
        )
        if candidato_plausivel and longitudinal > cfg.margem_antes_depois:
            posicao = PosicaoMarcadorVerde.DEPOIS_IGNORADO
        elif candidato_plausivel and longitudinal < -cfg.margem_antes_depois:
            if lateral > cfg.margem_lateral:
                posicao = PosicaoMarcadorVerde.ANTES_ESQUERDA
            elif lateral < -cfg.margem_lateral:
                posicao = PosicaoMarcadorVerde.ANTES_DIREITA

        return MarcadorVerde(
            centro=candidato.centro,
            confianca=candidato.confianca,
            area_normalizada=candidato.area_normalizada,
            posicao=posicao,
            deslocamento_longitudinal=longitudinal,
            deslocamento_lateral=lateral,
        )
