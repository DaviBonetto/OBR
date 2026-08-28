from pathlib import Path

import pytest

from obr_oficial.percepcao.pista.verde.configuracao import (
    ConfiguracaoGeometriaVerde,
    ConfiguracaoTemporalVerde,
    ErroConfiguracaoVerde,
    carregar_configuracao_verde,
)


def test_carrega_configuracao_oficial_com_linha_sempre_ativa() -> None:
    raiz = Path(__file__).resolve().parents[2]

    configuracao = carregar_configuracao_verde(raiz / "configuracoes" / "percepcao_verde.toml")

    assert configuracao.versao == 1
    assert configuracao.detector_linha_sempre_ativo is True
    assert configuracao.decisao_neutra_sem_verde is True
    assert configuracao.temporal.confirmacoes_minimas == 3


def test_rejeita_intervalo_de_area_invertido() -> None:
    with pytest.raises(ErroConfiguracaoVerde, match="intervalo de area"):
        ConfiguracaoGeometriaVerde(
            confianca_minima=0.75,
            area_normalizada_minima=0.08,
            area_normalizada_maxima=0.01,
            margem_antes_depois=0.01,
            margem_lateral=0.01,
        )


def test_rejeita_confirmacao_maior_que_janela() -> None:
    with pytest.raises(ErroConfiguracaoVerde, match="caber na janela"):
        ConfiguracaoTemporalVerde(
            janela_quadros=3,
            confirmacoes_minimas=4,
            memoria_maxima_ms=120.0,
        )


def test_rejeita_booleano_textual_no_arquivo(tmp_path: Path) -> None:
    caminho = tmp_path / "verde.toml"
    caminho.write_text(
        """
[verde]
versao = 1
[geometria]
confianca_minima = 0.75
area_normalizada_minima = 0.0001
area_normalizada_maxima = 0.08
margem_antes_depois = 0.01
margem_lateral = 0.015
[temporal]
janela_quadros = 5
confirmacoes_minimas = 3
memoria_maxima_ms = 120.0
[integracao]
detector_linha_sempre_ativo = "true"
decisao_neutra_sem_verde = true
""",
        encoding="utf-8",
    )

    with pytest.raises(ErroConfiguracaoVerde, match="Parametro booleano"):
        carregar_configuracao_verde(caminho)
