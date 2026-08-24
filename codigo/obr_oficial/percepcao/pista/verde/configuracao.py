"""Configuracao versionada da percepcao dos marcadores verdes."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any

from obr_oficial.nucleo.configuracao import carregar_toml, exigir_secao


class ErroConfiguracaoVerde(ValueError):
    """Indica parametro incompatível com o contrato da percepcao verde."""


@dataclass(frozen=True, slots=True)
class ConfiguracaoGeometriaVerde:
    """Limites normalizados usados para interpretar candidatos verdes."""

    confianca_minima: float
    area_normalizada_minima: float
    area_normalizada_maxima: float
    margem_antes_depois: float
    margem_lateral: float

    def __post_init__(self) -> None:
        if not isfinite(self.confianca_minima) or not 0.0 <= self.confianca_minima <= 1.0:
            raise ErroConfiguracaoVerde("confianca_minima deve estar entre zero e um")
        if not all(
            isfinite(valor)
            for valor in (self.area_normalizada_minima, self.area_normalizada_maxima)
        ) or not 0.0 < self.area_normalizada_minima < self.area_normalizada_maxima <= 1.0:
            raise ErroConfiguracaoVerde("intervalo de area normalizada invalido")
        if not isfinite(self.margem_antes_depois) or not 0.0 <= self.margem_antes_depois < 0.25:
            raise ErroConfiguracaoVerde("margem_antes_depois invalida")
        if not isfinite(self.margem_lateral) or not 0.0 <= self.margem_lateral < 0.25:
            raise ErroConfiguracaoVerde("margem_lateral invalida")


@dataclass(frozen=True, slots=True)
class ConfiguracaoTemporalVerde:
    """Contrato da confirmacao temporal que sera implementada depois do modelo."""

    janela_quadros: int
    confirmacoes_minimas: int
    memoria_maxima_ms: float

    def __post_init__(self) -> None:
        if self.janela_quadros < 1:
            raise ErroConfiguracaoVerde("janela_quadros deve ser positiva")
        if not 1 <= self.confirmacoes_minimas <= self.janela_quadros:
            raise ErroConfiguracaoVerde("confirmacoes_minimas deve caber na janela")
        if not isfinite(self.memoria_maxima_ms) or self.memoria_maxima_ms < 0.0:
            raise ErroConfiguracaoVerde("memoria_maxima_ms nao pode ser negativa")


@dataclass(frozen=True, slots=True)
class ConfiguracaoVerde:
    """Configuracao completa congelada na Fase Verde 0."""

    versao: int
    geometria: ConfiguracaoGeometriaVerde
    temporal: ConfiguracaoTemporalVerde
    detector_linha_sempre_ativo: bool
    decisao_neutra_sem_verde: bool

    def __post_init__(self) -> None:
        if self.versao < 1:
            raise ErroConfiguracaoVerde("versao deve ser positiva")
        if not self.detector_linha_sempre_ativo:
            raise ErroConfiguracaoVerde("o detector de linha deve permanecer sempre ativo")
        if not self.decisao_neutra_sem_verde:
            raise ErroConfiguracaoVerde("a ausencia de verde deve produzir decisao neutra")


def _numero(secao: dict[str, Any], nome: str, tipo: type[int] | type[float]) -> int | float:
    valor = secao.get(nome)
    if isinstance(valor, bool) or not isinstance(valor, int | float):
        raise ErroConfiguracaoVerde(f"Parametro numerico ausente ou invalido: {nome}")
    return tipo(valor)


def _booleano(secao: dict[str, Any], nome: str) -> bool:
    valor = secao.get(nome)
    if not isinstance(valor, bool):
        raise ErroConfiguracaoVerde(f"Parametro booleano ausente ou invalido: {nome}")
    return valor


def carregar_configuracao_verde(caminho: Path) -> ConfiguracaoVerde:
    """Carrega e valida o arquivo oficial da percepcao verde."""

    dados = carregar_toml(caminho)
    projeto = exigir_secao(dados, "verde")
    geometria = exigir_secao(dados, "geometria")
    temporal = exigir_secao(dados, "temporal")
    integracao = exigir_secao(dados, "integracao")
    try:
        return ConfiguracaoVerde(
            versao=int(projeto["versao"]),
            geometria=ConfiguracaoGeometriaVerde(
                confianca_minima=float(_numero(geometria, "confianca_minima", float)),
                area_normalizada_minima=float(
                    _numero(geometria, "area_normalizada_minima", float)
                ),
                area_normalizada_maxima=float(
                    _numero(geometria, "area_normalizada_maxima", float)
                ),
                margem_antes_depois=float(
                    _numero(geometria, "margem_antes_depois", float)
                ),
                margem_lateral=float(_numero(geometria, "margem_lateral", float)),
            ),
            temporal=ConfiguracaoTemporalVerde(
                janela_quadros=int(_numero(temporal, "janela_quadros", int)),
                confirmacoes_minimas=int(_numero(temporal, "confirmacoes_minimas", int)),
                memoria_maxima_ms=float(_numero(temporal, "memoria_maxima_ms", float)),
            ),
            detector_linha_sempre_ativo=_booleano(
                integracao, "detector_linha_sempre_ativo"
            ),
            decisao_neutra_sem_verde=_booleano(integracao, "decisao_neutra_sem_verde"),
        )
    except (KeyError, TypeError, ValueError) as erro:
        if isinstance(erro, ErroConfiguracaoVerde):
            raise
        raise ErroConfiguracaoVerde(f"Configuracao verde invalida: {erro}") from erro
