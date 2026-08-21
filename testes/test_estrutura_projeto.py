import json
from pathlib import Path


def test_arquivos_fundamentais_estao_presentes() -> None:
    raiz = Path(__file__).resolve().parents[1]
    caminhos = (
        "README.md",
        "pyproject.toml",
        "configuracoes/camera_usb.toml",
        "configuracoes/percepcao.toml",
        "configuracoes/controle.toml",
        "configuracoes/dataset_fase2.toml",
        "documentacao/ARQUITETURA.md",
        "documentacao/SEGURANCA.md",
        "documentacao/ESTADO_DO_PROJETO.md",
        "codigo/obr_oficial/nucleo/contratos.py",
        "codigo/obr_oficial/dados/preparacao_dataset.py",
        "dados/manifestos/fase2_v1.json",
    )

    ausentes = [caminho for caminho in caminhos if not (raiz / caminho).is_file()]

    assert ausentes == []


def test_configuracao_mantem_atuadores_desabilitados() -> None:
    raiz = Path(__file__).resolve().parents[1]
    conteudo = (raiz / "configuracoes" / "controle.toml").read_text(encoding="utf-8")

    assert "atuadores_habilitados = false" in conteudo
    assert "modo_simulacao = true" in conteudo


def test_resumo_versionado_do_dataset_fase2_e_consistente() -> None:
    raiz = Path(__file__).resolve().parents[1]
    manifesto = json.loads(
        (raiz / "dados" / "manifestos" / "fase2_v1.json").read_text(encoding="utf-8")
    )

    assert manifesto["pronto_para_anotacao"] is True
    assert manifesto["originais_alterados"] is False
    assert manifesto["quantidades"]["selecionados"] == sum(
        manifesto["quantidades"][divisao] for divisao in ("treino", "validacao", "teste")
    )
    assert set(manifesto["selecionados_por_divisao_e_tipo"]) == {
        "treino",
        "validacao",
        "teste",
    }
    assert all(len(hash_sha256) == 64 for hash_sha256 in manifesto["fingerprints"].values())
