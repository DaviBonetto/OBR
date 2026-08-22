import json
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from obr_oficial.treinamento.dataset_v2 import ErroDatasetV2, consolidar_dataset_v2


def _png(caminho: Path, imagem: np.ndarray) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(caminho), imagem)


def _preparar(tmp_path: Path) -> tuple[Path, Path]:
    dataset = tmp_path / "v1"
    auditoria = tmp_path / "auditoria"
    auditoria.mkdir()
    registros = []
    candidatas = []
    revisoes = []
    casos = (
        ("negativo", "sem_linha", "reprocessar"),
        ("curva", "curva_aberta", "aprovada"),
        ("t", "intersecao", "reprocessar"),
    )
    for indice, (nome, tipo, decisao) in enumerate(casos):
        imagem = np.full((48, 64, 3), 180, dtype=np.uint8)
        if nome == "t":
            imagem[20:30, :] = 5
            imagem[:, 27:37] = 5
        imagem_rel = Path("imagens") / f"{nome}.png"
        mascara_rel = Path("rotulos/mascaras") / f"{nome}.png"
        candidata_rel = Path("mascaras_modelo") / f"{nome}.png"
        _png(dataset / imagem_rel, imagem)
        _png(dataset / mascara_rel, np.zeros((24, 32), dtype=np.uint8))
        candidata = np.zeros((24, 32), dtype=np.uint8)
        candidata[:, 12:20] = 255
        _png(auditoria / candidata_rel, candidata)
        id_amostra = f"sessao:{indice}"
        registros.append(
            {
                "id_amostra": id_amostra,
                "divisao": "treino" if indice != 1 else "validacao",
                "tipo_quadro": tipo,
                "trajetoria_desejada": "reto",
                "imagem": imagem_rel.as_posix(),
                "mascara": mascara_rel.as_posix(),
                "estado_rotulo": "aprovada_vazia_por_usuario",
            }
        )
        candidatas.append(
            {
                "id_amostra": id_amostra,
                "divisao": registros[-1]["divisao"],
                "tipo_quadro": tipo,
                "mascara_candidata": candidata_rel.as_posix(),
                "motivo_auditoria": "rotulo_vazio_manual",
            }
        )
        revisoes.append({"id_amostra": id_amostra, "decisao": decisao})
    dataset.mkdir(exist_ok=True)
    (dataset / "indice.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in registros), encoding="utf-8"
    )
    (dataset / "manifesto.json").write_text("{}\n", encoding="utf-8")
    (auditoria / "candidatas.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in candidatas), encoding="utf-8"
    )
    (auditoria / "revisoes.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in revisoes), encoding="utf-8"
    )
    return dataset, auditoria


def test_consolida_correcoes_e_empacota_sem_teste(tmp_path: Path) -> None:
    dataset, auditoria = _preparar(tmp_path)
    saida = tmp_path / "v2"
    pacote = tmp_path / "v2.zip"

    manifesto = consolidar_dataset_v2(
        dataset,
        auditoria,
        saida,
        pacote,
        tmp_path / "manifesto_publico.json",
    )

    assert manifesto["divisao_teste_incluida"] is False
    assert manifesto["correcoes"] == {
        "hard_negatives_sombra": 1,
        "intersecoes_reconstruidas": 1,
        "mascaras_modelo_aprovadas": 1,
    }
    assert np.count_nonzero(cv2.imread(str(saida / "rotulos/mascaras/negativo.png"), 0)) == 0
    assert np.count_nonzero(cv2.imread(str(saida / "rotulos/mascaras/curva.png"), 0)) > 0
    assert np.count_nonzero(cv2.imread(str(saida / "rotulos/mascaras/t.png"), 0)) > 0
    with zipfile.ZipFile(pacote) as arquivo:
        assert "indice.jsonl" in arquivo.namelist()


def test_recusa_auditoria_incompleta(tmp_path: Path) -> None:
    dataset, auditoria = _preparar(tmp_path)
    linhas = (auditoria / "revisoes.jsonl").read_text().splitlines()
    (auditoria / "revisoes.jsonl").write_text("\n".join(linhas[:-1]) + "\n")

    with pytest.raises(ErroDatasetV2, match="pendencias"):
        consolidar_dataset_v2(
            dataset,
            auditoria,
            tmp_path / "v2",
            tmp_path / "v2.zip",
            tmp_path / "manifesto.json",
        )
