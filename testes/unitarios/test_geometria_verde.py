import pytest

from obr_oficial.nucleo.contratos import (
    DecisaoVerde,
    EstadoVerde,
    PontoNormalizado,
    PosicaoMarcadorVerde,
)
from obr_oficial.percepcao.pista.verde.configuracao import ConfiguracaoGeometriaVerde
from obr_oficial.percepcao.pista.verde.geometria import (
    CandidatoMarcadorVerde,
    InterpretadorGeometricoVerde,
    ReferencialIntersecao,
)


@pytest.fixture
def interpretador() -> InterpretadorGeometricoVerde:
    return InterpretadorGeometricoVerde(
        ConfiguracaoGeometriaVerde(
            confianca_minima=0.75,
            area_normalizada_minima=0.0001,
            area_normalizada_maxima=0.08,
            margem_antes_depois=0.01,
            margem_lateral=0.015,
        )
    )


@pytest.fixture
def intersecao_vertical() -> ReferencialIntersecao:
    # O robo vem de baixo e avanca para cima da imagem.
    return ReferencialIntersecao(
        centro=PontoNormalizado(0.50, 0.40),
        direcao_avanco_x=0.0,
        direcao_avanco_y=-1.0,
    )


def _candidato(x: float, y: float, confianca: float = 0.95) -> CandidatoMarcadorVerde:
    return CandidatoMarcadorVerde(
        centro=PontoNormalizado(x, y),
        confianca=confianca,
        area_normalizada=0.01,
    )


def _interpretar(
    interpretador: InterpretadorGeometricoVerde,
    referencial: ReferencialIntersecao,
    *candidatos: CandidatoMarcadorVerde,
):
    return interpretador.interpretar(
        tuple(candidatos),
        referencial,
        id_quadro=10,
        instante_monotonico_s=2.0,
    )


def test_sem_verde_publica_ausente_sem_comando(
    interpretador: InterpretadorGeometricoVerde,
    intersecao_vertical: ReferencialIntersecao,
) -> None:
    resultado = _interpretar(interpretador, intersecao_vertical)

    assert resultado.estado is EstadoVerde.AUSENTE
    assert resultado.decisao is DecisaoVerde.NENHUMA
    assert resultado.tem_comando is False


def test_verde_antes_a_esquerda_pede_esquerda(
    interpretador: InterpretadorGeometricoVerde,
    intersecao_vertical: ReferencialIntersecao,
) -> None:
    resultado = _interpretar(interpretador, intersecao_vertical, _candidato(0.35, 0.60))

    assert resultado.decisao is DecisaoVerde.VIRAR_ESQUERDA
    assert resultado.marcadores[0].posicao is PosicaoMarcadorVerde.ANTES_ESQUERDA


def test_verde_antes_a_direita_pede_direita(
    interpretador: InterpretadorGeometricoVerde,
    intersecao_vertical: ReferencialIntersecao,
) -> None:
    resultado = _interpretar(interpretador, intersecao_vertical, _candidato(0.65, 0.60))

    assert resultado.decisao is DecisaoVerde.VIRAR_DIREITA
    assert resultado.marcadores[0].posicao is PosicaoMarcadorVerde.ANTES_DIREITA


def test_verde_depois_e_detectado_mas_ignorado(
    interpretador: InterpretadorGeometricoVerde,
    intersecao_vertical: ReferencialIntersecao,
) -> None:
    resultado = _interpretar(interpretador, intersecao_vertical, _candidato(0.35, 0.20))

    assert resultado.estado is EstadoVerde.AUSENTE
    assert resultado.decisao is DecisaoVerde.NENHUMA
    assert resultado.marcadores[0].posicao is PosicaoMarcadorVerde.DEPOIS_IGNORADO
    assert resultado.motivo == "somente_marcadores_depois_ignorados"


def test_dois_verdes_antes_em_lados_opostos_pedem_retorno(
    interpretador: InterpretadorGeometricoVerde,
    intersecao_vertical: ReferencialIntersecao,
) -> None:
    resultado = _interpretar(
        interpretador,
        intersecao_vertical,
        _candidato(0.35, 0.60, 0.98),
        _candidato(0.65, 0.60, 0.91),
    )

    assert resultado.decisao is DecisaoVerde.RETORNAR_180
    assert resultado.confianca == pytest.approx(0.91)


def test_cruz_mista_obedece_antes_e_descarta_depois(
    interpretador: InterpretadorGeometricoVerde,
    intersecao_vertical: ReferencialIntersecao,
) -> None:
    resultado = _interpretar(
        interpretador,
        intersecao_vertical,
        _candidato(0.35, 0.60),  # antes, esquerda
        _candidato(0.65, 0.20),  # depois, deve ser ignorado
    )

    assert resultado.decisao is DecisaoVerde.VIRAR_ESQUERDA
    assert [marcador.posicao for marcador in resultado.marcadores] == [
        PosicaoMarcadorVerde.ANTES_ESQUERDA,
        PosicaoMarcadorVerde.DEPOIS_IGNORADO,
    ]


def test_dois_verdes_no_mesmo_lado_nao_inventam_retorno(
    interpretador: InterpretadorGeometricoVerde,
    intersecao_vertical: ReferencialIntersecao,
) -> None:
    resultado = _interpretar(
        interpretador,
        intersecao_vertical,
        _candidato(0.30, 0.60),
        _candidato(0.37, 0.58),
    )

    assert resultado.decisao is DecisaoVerde.VIRAR_ESQUERDA


def test_candidato_fraco_e_ambiguo_e_nunca_comanda(
    interpretador: InterpretadorGeometricoVerde,
    intersecao_vertical: ReferencialIntersecao,
) -> None:
    resultado = _interpretar(
        interpretador,
        intersecao_vertical,
        _candidato(0.35, 0.60, confianca=0.40),
    )

    assert resultado.estado is EstadoVerde.AMBIGUA
    assert resultado.decisao is DecisaoVerde.NENHUMA


def test_esquerda_e_relativa_ao_sentido_de_chegada(
    interpretador: InterpretadorGeometricoVerde,
) -> None:
    # O robo agora vem da esquerda e avanca para a direita. A esquerda dele fica acima.
    referencial = ReferencialIntersecao(
        centro=PontoNormalizado(0.50, 0.50),
        direcao_avanco_x=1.0,
        direcao_avanco_y=0.0,
    )
    resultado = _interpretar(interpretador, referencial, _candidato(0.30, 0.35))

    assert resultado.decisao is DecisaoVerde.VIRAR_ESQUERDA
    assert resultado.marcadores[0].posicao is PosicaoMarcadorVerde.ANTES_ESQUERDA


def test_rejeita_direcao_de_avanco_nao_finita() -> None:
    with pytest.raises(ValueError, match="deve ser finita"):
        ReferencialIntersecao(
            centro=PontoNormalizado(0.50, 0.50),
            direcao_avanco_x=float("nan"),
            direcao_avanco_y=0.0,
        )
