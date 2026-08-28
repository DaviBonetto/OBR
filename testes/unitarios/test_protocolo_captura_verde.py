import pytest

from obr_oficial.captura import ErroCaptura
from obr_oficial.captura.protocolo_verde import (
    CategoriaCapturaVerde,
    contexto_quadro_verde,
    contexto_sessao_verde,
    esquema_captura_verde,
)


@pytest.mark.parametrize(
    ("categoria", "decisao", "antes", "depois", "dois", "mascara_vazia"),
    [
        ("antes_esquerda", "virar_esquerda", True, False, False, False),
        ("antes_direita", "virar_direita", True, False, False, False),
        ("dois_antes_180", "retornar_180", True, False, True, False),
        ("depois_ignorar", "nenhuma", False, True, False, False),
        ("sem_verde_negativo", "nenhuma", False, False, False, True),
    ],
)
def test_materializa_semantica_da_categoria(
    categoria: str,
    decisao: str,
    antes: bool,
    depois: bool,
    dois: bool,
    mascara_vazia: bool,
) -> None:
    contexto = contexto_quadro_verde({"categoria_verde": categoria})

    assert contexto["tarefa"] == "verde"
    assert contexto["versao_protocolo_verde"] == 1
    assert contexto["decisao_verde_esperada"] == decisao
    assert contexto["marcador_antes_presente"] is antes
    assert contexto["marcador_depois_presente"] is depois
    assert contexto["dois_marcadores_antes"] is dois
    assert contexto["mascara_marcador_verde_esperada_vazia"] is mascara_vazia


def test_cruz_mista_preserva_decisao_de_antes_e_registra_depois() -> None:
    contexto = contexto_quadro_verde({"categoria_verde": "antes_direita", "cruz_mista": True})

    assert contexto["decisao_verde_esperada"] == "virar_direita"
    assert contexto["marcador_antes_presente"] is True
    assert contexto["marcador_depois_presente"] is True


@pytest.mark.parametrize("categoria", ["depois_ignorar", "sem_verde_negativo"])
def test_cruz_mista_sem_marcador_antes_e_rejeitada(categoria: str) -> None:
    with pytest.raises(ErroCaptura, match="exige ao menos"):
        contexto_quadro_verde({"categoria_verde": categoria, "cruz_mista": True})


def test_categoria_inexistente_e_rejeitada() -> None:
    with pytest.raises(ErroCaptura, match="categoria_verde invalida"):
        contexto_quadro_verde({"categoria_verde": "qualquer"})


def test_contexto_de_sessao_forca_tarefa_e_versao() -> None:
    contexto = contexto_sessao_verde({"nome": "teste", "tarefa": "linha"})

    assert contexto["nome"] == "teste"
    assert contexto["tarefa"] == "verde"
    assert contexto["versao_protocolo_verde"] == 1


def test_esquema_expoe_cinco_categorias_e_linha_independente() -> None:
    esquema = esquema_captura_verde()

    assert [item["categoria"] for item in esquema["categorias"]] == [
        categoria.value for categoria in CategoriaCapturaVerde
    ]
    assert esquema["ausencia_verde_interrompe_linha"] is False
