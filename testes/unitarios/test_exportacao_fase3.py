import hashlib
import json
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from obr_oficial.treinamento.exportacao_dataset import (
    ConfiguracaoExportacaoTreinamento,
    ErroExportacaoTreinamento,
    ExportadorDatasetTreinamento,
)


def _preparar(tmp_path: Path, divisao: str = "treino") -> tuple[Path, Path]:
    brutos = tmp_path / "brutos"
    rotulos = tmp_path / "rotulos"
    (brutos / "sessao").mkdir(parents=True)
    (rotulos / "mascaras" / "sessao").mkdir(parents=True)
    imagem = np.full((48, 64, 3), 220, dtype=np.uint8)
    mascara = np.zeros((32, 48), dtype=np.uint8)
    mascara[:, 20:28] = 255
    assert cv2.imwrite(str(brutos / "sessao" / "quadro.png"), imagem)
    assert cv2.imwrite(str(rotulos / "mascaras" / "sessao" / "quadro.png"), mascara)
    conteudo_mascara = (rotulos / "mascaras" / "sessao" / "quadro.png").read_bytes()
    anotacoes = [
        {
            "id_amostra": "sessao:1",
            "divisao": divisao,
            "tipo_quadro": "reta",
            "trajetoria_desejada": "seguir_linha",
            "origem": "sessao/quadro.png",
            "estado_rotulo": "aprovada_por_regra_usuario",
            "mascara": "mascaras/sessao/quadro.png",
            "sha256_mascara": hashlib.sha256(conteudo_mascara).hexdigest(),
        },
        {
            "id_amostra": "sessao:2",
            "divisao": "treino",
            "tipo_quadro": "intersecao",
            "trajetoria_desejada": "reto",
            "origem": "sessao/nao_deve_ser_lida.png",
            "estado_rotulo": "aguardando_active_learning",
            "mascara": None,
            "sha256_mascara": None,
        },
    ]
    (rotulos / "anotacoes.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in anotacoes),
        encoding="utf-8",
    )
    (rotulos / "manifesto.json").write_text("{}\n", encoding="utf-8")
    return brutos, rotulos


def test_exporta_apenas_rotulos_supervisionados(tmp_path: Path) -> None:
    brutos, rotulos = _preparar(tmp_path)
    saida = tmp_path / "dataset.zip"

    resultado = ExportadorDatasetTreinamento(
        ConfiguracaoExportacaoTreinamento(brutos, rotulos, saida)
    ).exportar()

    assert resultado["quantidades"] == {"total": 1, "treino": 1, "validacao": 0}
    assert resultado["divisao_teste_incluida"] is False
    with zipfile.ZipFile(saida) as arquivo:
        assert sorted(arquivo.namelist()) == [
            "imagens/sessao/quadro.png",
            "indice.jsonl",
            "manifesto.json",
            "rotulos/mascaras/sessao/quadro.png",
        ]
        indice = json.loads(arquivo.read("indice.jsonl"))
        assert indice["id_amostra"] == "sessao:1"
    assert saida.with_suffix(".manifesto.json").is_file()


def test_exportacao_deterministica(tmp_path: Path) -> None:
    brutos, rotulos = _preparar(tmp_path)
    primeira = tmp_path / "primeira.zip"
    segunda = tmp_path / "segunda.zip"

    ExportadorDatasetTreinamento(
        ConfiguracaoExportacaoTreinamento(brutos, rotulos, primeira)
    ).exportar()
    ExportadorDatasetTreinamento(
        ConfiguracaoExportacaoTreinamento(brutos, rotulos, segunda)
    ).exportar()

    assert (
        hashlib.sha256(primeira.read_bytes()).digest()
        == hashlib.sha256(segunda.read_bytes()).digest()
    )


def test_recusa_teste_e_saida_existente(tmp_path: Path) -> None:
    brutos, rotulos = _preparar(tmp_path, divisao="teste")
    saida = tmp_path / "dataset.zip"
    exportador = ExportadorDatasetTreinamento(
        ConfiguracaoExportacaoTreinamento(brutos, rotulos, saida)
    )
    with pytest.raises(ErroExportacaoTreinamento, match="Divisao proibida"):
        exportador.exportar()

    saida.write_bytes(b"existente")
    with pytest.raises(ErroExportacaoTreinamento, match="ja existe"):
        exportador.exportar()
