from obr_oficial.nucleo.contratos import (
    DecisaoVerde,
    EstadoVerde,
    EstimativaVerde,
    FonteEstimativa,
    MarcadorVerde,
    PontoNormalizado,
    PosicaoMarcadorVerde,
)
from obr_oficial.percepcao.pista.verde.configuracao import ConfiguracaoTemporalVerde
from obr_oficial.percepcao.pista.verde.rastreamento import RastreadorVerde


def _estimativa(
    id_quadro: int,
    instante_s: float,
    decisao: DecisaoVerde,
) -> EstimativaVerde:
    if decisao is DecisaoVerde.NENHUMA:
        return EstimativaVerde(
            id_quadro=id_quadro,
            instante_monotonico_s=instante_s,
            estado=EstadoVerde.AUSENTE,
            decisao=decisao,
            confianca=0.0,
        )
    posicoes = {
        DecisaoVerde.VIRAR_ESQUERDA: (PosicaoMarcadorVerde.ANTES_ESQUERDA,),
        DecisaoVerde.VIRAR_DIREITA: (PosicaoMarcadorVerde.ANTES_DIREITA,),
        DecisaoVerde.RETORNAR_180: (
            PosicaoMarcadorVerde.ANTES_ESQUERDA,
            PosicaoMarcadorVerde.ANTES_DIREITA,
        ),
    }[decisao]
    marcadores = tuple(
        MarcadorVerde(
            centro=PontoNormalizado(0.4 + indice * 0.2, 0.6),
            confianca=0.9 - indice * 0.05,
            area_normalizada=0.01,
            posicao=posicao,
            deslocamento_longitudinal=-0.2,
            deslocamento_lateral=0.1 if indice == 0 else -0.1,
        )
        for indice, posicao in enumerate(posicoes)
    )
    return EstimativaVerde(
        id_quadro=id_quadro,
        instante_monotonico_s=instante_s,
        estado=EstadoVerde.CANDIDATA,
        decisao=decisao,
        confianca=0.9,
        marcadores=marcadores,
        fonte=FonteEstimativa.IA,
    )


def _rastreador() -> RastreadorVerde:
    return RastreadorVerde(
        ConfiguracaoTemporalVerde(
            janela_quadros=5,
            confirmacoes_minimas=3,
            memoria_maxima_ms=120.0,
        )
    )


def test_confirma_tres_observacoes_consecutivas_no_t() -> None:
    rastreador = _rastreador()

    primeira = rastreador.atualizar(
        _estimativa(1, 1.00, DecisaoVerde.VIRAR_ESQUERDA),
        intersecao_detectada=False,
    )
    segunda = rastreador.atualizar(
        _estimativa(2, 1.03, DecisaoVerde.VIRAR_ESQUERDA),
        intersecao_detectada=False,
    )
    terceira = rastreador.atualizar(
        _estimativa(3, 1.06, DecisaoVerde.VIRAR_ESQUERDA),
        intersecao_detectada=True,
    )

    assert primeira.decisao is DecisaoVerde.NENHUMA
    assert segunda.decisao is DecisaoVerde.NENHUMA
    assert terceira.estado is EstadoVerde.CONFIRMADA
    assert terceira.fonte is FonteEstimativa.TEMPORAL
    assert terceira.confianca == 0.9


def test_troca_de_lado_nao_reaproveita_confirmacoes() -> None:
    rastreador = _rastreador()

    rastreador.atualizar(
        _estimativa(1, 1.00, DecisaoVerde.VIRAR_ESQUERDA),
        intersecao_detectada=False,
    )
    rastreador.atualizar(
        _estimativa(2, 1.03, DecisaoVerde.VIRAR_DIREITA),
        intersecao_detectada=False,
    )
    resultado = rastreador.atualizar(
        _estimativa(3, 1.06, DecisaoVerde.VIRAR_DIREITA),
        intersecao_detectada=True,
    )

    assert resultado.estado is EstadoVerde.AMBIGUA
    assert resultado.decisao is DecisaoVerde.NENHUMA


def test_observacao_neutra_mantem_memoria_curta_ate_o_t() -> None:
    rastreador = _rastreador()

    for quadro in range(1, 4):
        rastreador.atualizar(
            _estimativa(quadro, 1.0 + quadro * 0.02, DecisaoVerde.VIRAR_ESQUERDA),
            intersecao_detectada=False,
        )
    neutra = rastreador.atualizar(
        _estimativa(4, 1.08, DecisaoVerde.NENHUMA),
        intersecao_detectada=False,
    )
    resultado = rastreador.atualizar(
        _estimativa(5, 1.10, DecisaoVerde.NENHUMA),
        intersecao_detectada=True,
    )

    assert neutra.decisao is DecisaoVerde.NENHUMA
    assert neutra.motivo == "evidencia_verde_antes_do_t_virar_esquerda"
    assert resultado.estado is EstadoVerde.CONFIRMADA
    assert resultado.decisao is DecisaoVerde.VIRAR_ESQUERDA


def test_memoria_expirada_nao_confirma() -> None:
    rastreador = _rastreador()

    rastreador.atualizar(
        _estimativa(1, 1.00, DecisaoVerde.VIRAR_ESQUERDA),
        intersecao_detectada=False,
    )
    rastreador.atualizar(
        _estimativa(2, 1.20, DecisaoVerde.VIRAR_ESQUERDA),
        intersecao_detectada=False,
    )
    resultado = rastreador.atualizar(
        _estimativa(3, 1.23, DecisaoVerde.VIRAR_ESQUERDA),
        intersecao_detectada=True,
    )

    assert resultado.estado is EstadoVerde.AMBIGUA


def test_t_confirma_evidencia_anterior_quando_o_marcador_ja_saiu_do_quadro() -> None:
    rastreador = _rastreador()
    for quadro in range(1, 4):
        rastreador.atualizar(
            _estimativa(quadro, 1.0 + quadro * 0.03, DecisaoVerde.RETORNAR_180),
            intersecao_detectada=False,
        )

    resultado = rastreador.atualizar(
        _estimativa(4, 1.12, DecisaoVerde.NENHUMA),
        intersecao_detectada=True,
    )

    assert resultado.estado is EstadoVerde.CONFIRMADA
    assert resultado.decisao is DecisaoVerde.RETORNAR_180


def test_retorno_confirma_sem_t_apos_tres_pares_alinhados() -> None:
    rastreador = _rastreador()

    primeira = rastreador.atualizar(
        _estimativa(1, 1.00, DecisaoVerde.RETORNAR_180),
        intersecao_detectada=False,
    )
    segunda = rastreador.atualizar(
        _estimativa(2, 1.03, DecisaoVerde.RETORNAR_180),
        intersecao_detectada=False,
    )
    terceira = rastreador.atualizar(
        _estimativa(3, 1.06, DecisaoVerde.RETORNAR_180),
        intersecao_detectada=False,
    )

    assert primeira.estado is EstadoVerde.CANDIDATA
    assert primeira.decisao is DecisaoVerde.RETORNAR_180
    assert segunda.estado is EstadoVerde.CANDIDATA
    assert terceira.estado is EstadoVerde.CONFIRMADA
    assert terceira.decisao is DecisaoVerde.RETORNAR_180
    assert terceira.motivo == "retorno_confirmado_temporalmente"
