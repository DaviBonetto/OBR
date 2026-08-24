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


class EstadoVerde(StrEnum):
    """Estado temporal da interpretacao dos marcadores verdes."""

    AUSENTE = "ausente"
    CANDIDATA = "candidata"
    CONFIRMADA = "confirmada"
    AMBIGUA = "ambigua"


class DecisaoVerde(StrEnum):
    """Intencao publicada pelo verde; ``NENHUMA`` nunca interrompe a linha."""

    NENHUMA = "nenhuma"
    VIRAR_ESQUERDA = "virar_esquerda"
    VIRAR_DIREITA = "virar_direita"
    RETORNAR_180 = "retornar_180"


class PosicaoMarcadorVerde(StrEnum):
    """Papel geometrico de um marcador em relacao ao sentido de chegada."""

    ANTES_ESQUERDA = "antes_esquerda"
    ANTES_DIREITA = "antes_direita"
    DEPOIS_IGNORADO = "depois_ignorado"
    AMBIGUA = "ambigua"


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
            _exigir_intervalo("erro_lateral_normalizado", self.erro_lateral_normalizado, -1.0, 1.0)
        if self.erro_angular_graus is not None:
            _exigir_finito("erro_angular_graus", self.erro_angular_graus)
        if self.curvatura_normalizada is not None:
            _exigir_intervalo("curvatura_normalizada", self.curvatura_normalizada, -1.0, 1.0)

        if self.estado is EstadoDeteccao.ENCONTRADA:
            if len(self.centro_linha) < 2:
                raise ValueError("Linha encontrada exige ao menos dois pontos centrais")
            if self.ponto_atual is None or self.ponto_objetivo is None:
                raise ValueError("Linha encontrada exige ponto atual e ponto objetivo")


@dataclass(frozen=True, slots=True)
class MarcadorVerde:
    """Componente verde ja posicionado no referencial local da intersecao."""

    centro: PontoNormalizado
    confianca: float
    area_normalizada: float
    posicao: PosicaoMarcadorVerde
    deslocamento_longitudinal: float
    deslocamento_lateral: float

    def __post_init__(self) -> None:
        _exigir_intervalo("confianca do marcador", self.confianca, 0.0, 1.0)
        _exigir_intervalo("area_normalizada", self.area_normalizada, 0.0, 1.0)
        _exigir_finito("deslocamento_longitudinal", self.deslocamento_longitudinal)
        _exigir_finito("deslocamento_lateral", self.deslocamento_lateral)

    @property
    def valido_para_decisao(self) -> bool:
        """Informa se o marcador esta antes e em um lado definido da linha."""

        return self.posicao in {
            PosicaoMarcadorVerde.ANTES_ESQUERDA,
            PosicaoMarcadorVerde.ANTES_DIREITA,
        }


@dataclass(frozen=True, slots=True)
class EstimativaVerde:
    """Saida do verde, independente do detector e neutra quando nao ha comando."""

    id_quadro: int
    instante_monotonico_s: float
    estado: EstadoVerde
    decisao: DecisaoVerde
    confianca: float
    marcadores: tuple[MarcadorVerde, ...] = field(default_factory=tuple)
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
        if not isinstance(self.marcadores, tuple):
            raise TypeError("marcadores deve ser uma tupla imutavel")

        tem_decisao = self.decisao is not DecisaoVerde.NENHUMA
        if self.estado in {EstadoVerde.CANDIDATA, EstadoVerde.CONFIRMADA} and not tem_decisao:
            raise ValueError("Estado candidato ou confirmado exige uma decisao verde")
        if self.estado in {EstadoVerde.AUSENTE, EstadoVerde.AMBIGUA} and tem_decisao:
            raise ValueError("Estado ausente ou ambiguo deve ser neutro")

        posicoes_validas = {marcador.posicao for marcador in self.marcadores}
        if self.decisao is DecisaoVerde.VIRAR_ESQUERDA:
            if PosicaoMarcadorVerde.ANTES_ESQUERDA not in posicoes_validas:
                raise ValueError("Virar a esquerda exige marcador antes a esquerda")
        elif self.decisao is DecisaoVerde.VIRAR_DIREITA:
            if PosicaoMarcadorVerde.ANTES_DIREITA not in posicoes_validas:
                raise ValueError("Virar a direita exige marcador antes a direita")
        elif self.decisao is DecisaoVerde.RETORNAR_180:
            lados_obrigatorios = {
                PosicaoMarcadorVerde.ANTES_ESQUERDA,
                PosicaoMarcadorVerde.ANTES_DIREITA,
            }
            if not lados_obrigatorios.issubset(posicoes_validas):
                raise ValueError("Retorno exige dois marcadores antes, um em cada lado")

    @property
    def tem_comando(self) -> bool:
        """Distingue uma intencao verde da operacao normal do seguidor de linha."""

        return self.decisao is not DecisaoVerde.NENHUMA


@dataclass(frozen=True, slots=True)
class EstimativaPista:
    """Compoe linha e verde do mesmo quadro sem uma estimativa substituir a outra."""

    linha: EstimativaLinha
    verde: EstimativaVerde

    def __post_init__(self) -> None:
        if self.linha.id_quadro != self.verde.id_quadro:
            raise ValueError("Linha e verde devem pertencer ao mesmo quadro")

    @property
    def id_quadro(self) -> int:
        return self.linha.id_quadro
