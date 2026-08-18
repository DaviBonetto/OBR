import pytest

from obr_oficial.nucleo.contratos import (
    EstadoDeteccao,
    EstimativaLinha,
    FonteEstimativa,
    PontoNormalizado,
    TemposProcessamento,
    TipoCurva,
)


def test_cria_estimativa_encontrada_com_contrato_completo() -> None:
    pontos = (
        PontoNormalizado(0.50, 0.90),
        PontoNormalizado(0.48, 0.60),
        PontoNormalizado(0.44, 0.30),
    )

    estimativa = EstimativaLinha(
        id_quadro=12,
        instante_monotonico_s=25.5,
        estado=EstadoDeteccao.ENCONTRADA,
        confianca=0.97,
        centro_linha=pontos,
        ponto_atual=pontos[0],
        ponto_objetivo=pontos[2],
        erro_lateral_normalizado=-0.03,
        erro_angular_graus=-4.2,
        curvatura_normalizada=-0.15,
        tipo_curva=TipoCurva.ESQUERDA_SUAVE,
        fonte=FonteEstimativa.HIBRIDA,
        tempos=TemposProcessamento(
            pre_processamento_ms=2.0,
            inferencia_ms=11.0,
            geometria_ms=3.0,
            rastreamento_ms=1.0,
        ),
    )

    assert estimativa.estado is EstadoDeteccao.ENCONTRADA
    assert estimativa.ponto_objetivo == pontos[2]
    assert estimativa.tempos.total_ms == pytest.approx(17.0)


def test_rejeita_ponto_fora_da_imagem_normalizada() -> None:
    with pytest.raises(ValueError, match="x deve estar entre"):
        PontoNormalizado(1.01, 0.5)


def test_rejeita_confianca_fora_do_intervalo() -> None:
    with pytest.raises(ValueError, match="confianca deve estar entre"):
        EstimativaLinha(
            id_quadro=0,
            instante_monotonico_s=0.0,
            estado=EstadoDeteccao.PERDIDA,
            confianca=1.1,
        )


def test_linha_encontrada_exige_trajetoria_e_pontos_de_referencia() -> None:
    with pytest.raises(ValueError, match="ao menos dois pontos"):
        EstimativaLinha(
            id_quadro=1,
            instante_monotonico_s=1.0,
            estado=EstadoDeteccao.ENCONTRADA,
            confianca=0.9,
        )


def test_linha_perdida_pode_ser_representada_sem_geometria() -> None:
    estimativa = EstimativaLinha(
        id_quadro=2,
        instante_monotonico_s=2.0,
        estado=EstadoDeteccao.PERDIDA,
        confianca=0.1,
        motivo="sem_evidencia",
    )

    assert estimativa.centro_linha == ()
    assert estimativa.fonte is FonteEstimativa.NENHUMA
