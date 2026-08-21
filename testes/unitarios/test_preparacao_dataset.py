import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from obr_oficial.dados import (
    ErroPreparacaoDataset,
    PreparadorDataset,
    carregar_configuracao_dataset,
)
from obr_oficial.dispositivos.metricas_imagem import calcular_metricas_imagem


def _configuracao(tmp_path: Path) -> Path:
    caminho = tmp_path / "dataset.toml"
    caminho.write_text(
        """
[dataset]
nome = "teste_v1"
versao = 1
largura = 64
altura = 48
tipos_permitidos = ["reta", "curva_fechada", "curva_aberta", "intersecao", "sem_linha"]

[filtros]
limiar_diferenca_media = 5.0
brilho_minimo = 20.0
brilho_maximo = 225.0
percentual_escuro_maximo = 80.0
percentual_claro_maximo = 50.0

[criterios]
minimo_por_tipo_por_divisao = 1

[divisoes]
treino = ["ambiente_treino"]
validacao = ["ambiente_validacao"]
teste = ["ambiente_teste"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return caminho


def _criar_sessao(
    raiz: Path,
    nome: str,
    local: str,
    tipo: str,
    imagens: list[np.ndarray],
) -> None:
    pasta = raiz / nome
    quadros = pasta / "quadros"
    quadros.mkdir(parents=True)
    registros = []
    for numero, imagem in enumerate(imagens, start=1):
        sucesso, codificada = cv2.imencode(".png", imagem)
        assert sucesso
        conteudo = codificada.tobytes()
        caminho_relativo = Path("quadros") / f"quadro_{numero:06d}.png"
        (pasta / caminho_relativo).write_bytes(conteudo)
        registros.append(
            {
                "versao_registro": 1,
                "numero": numero,
                "arquivo": caminho_relativo.as_posix(),
                "sha256": hashlib.sha256(conteudo).hexdigest(),
                "captura_utc": f"2026-08-21T12:00:{numero:02d}+00:00",
                "quadro": {"largura": 64, "altura": 48},
                "metricas": calcular_metricas_imagem(imagem).como_dict(),
                "contexto": {"tipo_quadro": tipo},
            }
        )
    manifesto = {
        "versao_manifesto": 1,
        "id_sessao": nome,
        "estado": "finalizada",
        "contexto": {"local": local},
        "camera": {"nome_perfil": "teste"},
        "capturas": len(registros),
    }
    (pasta / "manifesto.json").write_text(
        json.dumps(manifesto),
        encoding="utf-8",
    )
    (pasta / "capturas.jsonl").write_text(
        "".join(json.dumps(registro) + "\n" for registro in registros),
        encoding="utf-8",
    )


def _imagem(valor: int) -> np.ndarray:
    return np.full((48, 64, 3), valor, dtype=np.uint8)


def test_prepara_dataset_sem_alterar_originais(tmp_path: Path) -> None:
    raiz = tmp_path / "brutos"
    imagem_distinta = _imagem(100)
    imagem_distinta[:, :32] = 30
    imagem_validacao = _imagem(110)
    imagem_validacao[:, 32:] = 40
    _criar_sessao(
        raiz,
        "sessao_treino",
        "Ambiente Treino",
        "reta",
        [_imagem(100), _imagem(100), _imagem(102), imagem_distinta],
    )
    _criar_sessao(
        raiz,
        "sessao_validacao",
        "Ambiente Validação",
        "intersecao",
        [imagem_validacao],
    )
    _criar_sessao(
        raiz,
        "sessao_teste",
        "Ambiente Teste",
        "sem_linha",
        [_imagem(0)],
    )
    hashes_antes = {
        caminho: hashlib.sha256(caminho.read_bytes()).hexdigest() for caminho in raiz.rglob("*.png")
    }

    saida = tmp_path / "processado"
    configuracao = carregar_configuracao_dataset(_configuracao(tmp_path))
    manifesto = PreparadorDataset(raiz, saida, configuracao).preparar()

    assert manifesto["originais_alterados"] is False
    assert manifesto["pronto_para_anotacao"] is False
    assert manifesto["tipos_ausentes_por_divisao"] == {
        "treino": ["curva_fechada", "curva_aberta", "intersecao", "sem_linha"],
        "validacao": ["reta", "curva_fechada", "curva_aberta", "sem_linha"],
        "teste": ["reta", "curva_fechada", "curva_aberta", "intersecao", "sem_linha"],
    }
    assert manifesto["tipos_insuficientes_por_divisao"] == {
        "treino": {
            "curva_fechada": 0,
            "curva_aberta": 0,
            "intersecao": 0,
            "sem_linha": 0,
        },
        "validacao": {
            "reta": 0,
            "curva_fechada": 0,
            "curva_aberta": 0,
            "sem_linha": 0,
        },
        "teste": {
            "reta": 0,
            "curva_fechada": 0,
            "curva_aberta": 0,
            "intersecao": 0,
            "sem_linha": 0,
        },
    }
    assert manifesto["quantidades"]["quadros_brutos"] == 6
    assert manifesto["quantidades"]["quadros_selecionados"] == 3
    assert manifesto["quantidades"]["por_divisao"] == {"treino": 2, "validacao": 1}
    assert manifesto["quantidades"]["rejeicoes_por_motivo"] == {
        "brilho_muito_baixo": 1,
        "duplicata_exata": 1,
        "imagem_predominantemente_escura": 1,
        "quase_duplicata_temporal": 2,
    }
    assert hashes_antes == {
        caminho: hashlib.sha256(caminho.read_bytes()).hexdigest() for caminho in raiz.rglob("*.png")
    }

    amostras = [
        json.loads(linha)
        for linha in (saida / "amostras.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    intersecao = next(item for item in amostras if item["tipo_quadro"] == "intersecao")
    assert intersecao["trajetoria_desejada"] == "reto"
    assert intersecao["anotacao"] == {
        "estado": "pendente",
        "linha_central_normalizada": None,
        "mascara_linha": None,
        "ponto_objetivo_normalizado": None,
    }
    assert (saida / "divisoes" / "treino.txt").read_text().count("\n") == 2
    assert (saida / "divisoes" / "validacao.txt").read_text().count("\n") == 1
    assert (saida / "divisoes" / "teste.txt").read_text() == ""


def test_rejeita_ambiente_sem_divisao_e_remove_temporario(tmp_path: Path) -> None:
    raiz = tmp_path / "brutos"
    _criar_sessao(raiz, "sessao", "Ambiente Desconhecido", "reta", [_imagem(100)])
    saida = tmp_path / "processado"

    with pytest.raises(ErroPreparacaoDataset, match="exatamente uma divisao"):
        PreparadorDataset(
            raiz,
            saida,
            carregar_configuracao_dataset(_configuracao(tmp_path)),
        ).preparar()

    assert not saida.exists()
    assert not list(tmp_path.glob(".processado.tmp-*"))


def test_nao_sobrescreve_dataset_processado(tmp_path: Path) -> None:
    raiz = tmp_path / "brutos"
    _criar_sessao(raiz, "sessao", "Ambiente Treino", "reta", [_imagem(100)])
    saida = tmp_path / "processado"
    saida.mkdir()

    with pytest.raises(ErroPreparacaoDataset, match="Saida ja existe"):
        PreparadorDataset(
            raiz,
            saida,
            carregar_configuracao_dataset(_configuracao(tmp_path)),
        ).preparar()


def test_hash_da_configuracao_independe_da_quebra_de_linha(tmp_path: Path) -> None:
    caminho_lf = _configuracao(tmp_path)
    conteudo = caminho_lf.read_text(encoding="utf-8")
    caminho_crlf = tmp_path / "dataset_crlf.toml"
    caminho_crlf.write_bytes(conteudo.replace("\n", "\r\n").encode("utf-8"))

    assert (
        carregar_configuracao_dataset(caminho_lf).hash_configuracao
        == carregar_configuracao_dataset(caminho_crlf).hash_configuracao
    )
