import pytest

from obr_oficial.nucleo.contratos import (
    DecisaoVerde,
    EstadoDeteccao,
    EstadoVerde,
    EstimativaLinha,
    EstimativaPista,
    EstimativaVerde,
    FonteEstimativa,
    PontoNormalizado,
    TipoCurva,
)


def _linha_encontrada(id_quadro: int = 7) -> EstimativaLinha:
    pontos = (
        PontoNormalizado(0.50, 0.90),
        PontoNormalizado(0.50, 0.60),
        PontoNormalizado(0.50, 0.30),
    )
    return EstimativaLinha(
        id_quadro=id_quadro,
        instante_monotonico_s=1.0,
        estado=EstadoDeteccao.ENCONTRADA,
        confianca=0.99,
        centro_linha=pontos,
        ponto_atual=pontos[0],
        ponto_objetivo=pontos[-1],
        tipo_curva=TipoCurva.RETA,
        fonte=FonteEstimativa.IA,
    )


def test_ausencia_de_verde_e_neutra_e_preserva_linha() -> None:
    linha = _linha_encontrada()
    verde = EstimativaVerde(
        id_quadro=linha.id_quadro,
        instante_monotonico_s=1.0,
        estado=EstadoVerde.AUSENTE,
        decisao=DecisaoVerde.NENHUMA,
        confianca=0.0,
        motivo="sem_marcador_verde",
    )

    pista = EstimativaPista(linha=linha, verde=verde)

    assert pista.linha.estado is EstadoDeteccao.ENCONTRADA
    assert pista.verde.tem_comando is False
    assert pista.id_quadro == 7


def test_estimativa_pista_rejeita_resultados_de_quadros_diferentes() -> None:
    linha = _linha_encontrada(id_quadro=7)
    verde = EstimativaVerde(
        id_quadro=8,
        instante_monotonico_s=1.0,
        estado=EstadoVerde.AUSENTE,
        decisao=DecisaoVerde.NENHUMA,
        confianca=0.0,
    )

    with pytest.raises(ValueError, match="mesmo quadro"):
        EstimativaPista(linha=linha, verde=verde)


def test_estado_ausente_nao_pode_publicar_curva() -> None:
    with pytest.raises(ValueError, match="deve ser neutro"):
        EstimativaVerde(
            id_quadro=1,
            instante_monotonico_s=1.0,
            estado=EstadoVerde.AUSENTE,
            decisao=DecisaoVerde.VIRAR_ESQUERDA,
            confianca=0.9,
        )
