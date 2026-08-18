from pathlib import Path

import pytest

from obr_oficial.nucleo.configuracao import (
    ErroConfiguracao,
    carregar_configuracao,
    carregar_toml,
    exigir_secao,
)


@pytest.mark.parametrize(
    "nome",
    [
        "camera_usb.toml",
        "percepcao.toml",
        "controle.toml",
        "resgate.toml",
        "painel.toml",
        "raspberry_pi.toml",
    ],
)
def test_carrega_todas_as_configuracoes_oficiais(nome: str) -> None:
    assert carregar_configuracao(nome)


def test_rejeita_caminho_fora_da_pasta_de_configuracoes() -> None:
    with pytest.raises(ErroConfiguracao, match="somente o nome"):
        carregar_configuracao("../pyproject.toml")


def test_informa_arquivo_ausente() -> None:
    with pytest.raises(ErroConfiguracao, match="nao encontrada"):
        carregar_configuracao("inexistente.toml")


def test_rejeita_extensao_diferente_de_toml(tmp_path: Path) -> None:
    caminho = tmp_path / "configuracao.txt"
    caminho.touch()

    with pytest.raises(ErroConfiguracao, match="deve ser TOML"):
        carregar_toml(caminho)


def test_exige_secao_existente() -> None:
    configuracao = carregar_configuracao("controle.toml")

    assert exigir_secao(configuracao, "seguranca")["atuadores_habilitados"] is False


def test_informa_secao_ausente() -> None:
    with pytest.raises(ErroConfiguracao, match="Secao obrigatoria"):
        exigir_secao({}, "inexistente")
