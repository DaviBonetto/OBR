from pathlib import Path


def test_arquivos_fundamentais_estao_presentes() -> None:
    raiz = Path(__file__).resolve().parents[1]
    caminhos = (
        "README.md",
        "pyproject.toml",
        "configuracoes/camera_usb.toml",
        "configuracoes/percepcao.toml",
        "configuracoes/controle.toml",
        "documentacao/ARQUITETURA.md",
        "documentacao/SEGURANCA.md",
        "documentacao/ESTADO_DO_PROJETO.md",
        "codigo/obr_oficial/nucleo/contratos.py",
    )

    ausentes = [caminho for caminho in caminhos if not (raiz / caminho).is_file()]

    assert ausentes == []


def test_configuracao_mantem_atuadores_desabilitados() -> None:
    raiz = Path(__file__).resolve().parents[1]
    conteudo = (raiz / "configuracoes" / "controle.toml").read_text(encoding="utf-8")

    assert "atuadores_habilitados = false" in conteudo
    assert "modo_simulacao = true" in conteudo
