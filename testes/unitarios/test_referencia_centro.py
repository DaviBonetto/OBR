from __future__ import annotations

from pathlib import Path

import pytest

from obr_oficial.dados.referencia_centro import (
    ErroReferenciaCentro,
    RepositorioReferenciaCentro,
    preparar_selecao_referencia,
)


def test_selecao_estratificada_e_anotacao_humana(
    tmp_path: Path,
    preparar_dataset_referencia,
) -> None:
    dataset = preparar_dataset_referencia(tmp_path)
    referencia = tmp_path / "referencia"

    preparar_selecao_referencia(dataset, referencia, quantidade_por_tipo=2)
    repositorio = RepositorioReferenciaCentro(dataset, referencia)

    assert len(repositorio.amostras) == 8
    assert repositorio.resumo()["pendentes"] == 8
    id_amostra = str(repositorio.amostras[0]["id_amostra"])
    registro = repositorio.registrar(
        id_amostra,
        [
            {"x": 0.5, "y": 1.0},
            {"x": 0.5, "y": 0.7},
            {"x": 0.5, "y": 0.4},
            {"x": 0.5, "y": 0.0},
        ],
    )
    assert registro["origem"] == "humana_manual"
    assert repositorio.resumo()["anotadas"] == 1
    assert repositorio.consultar(indice=0, estado="anotadas")["total"] == 1


def test_referencia_recusa_indice_contaminado_pelo_teste(
    tmp_path: Path,
    preparar_dataset_referencia,
) -> None:
    dataset = preparar_dataset_referencia(tmp_path, incluir_teste=True)

    with pytest.raises(ErroReferenciaCentro, match="contaminado"):
        preparar_selecao_referencia(dataset, tmp_path / "referencia", quantidade_por_tipo=1)


def test_referencia_recusa_trajetoria_curta(
    tmp_path: Path,
    preparar_dataset_referencia,
) -> None:
    dataset = preparar_dataset_referencia(tmp_path)
    referencia = tmp_path / "referencia"
    preparar_selecao_referencia(dataset, referencia, quantidade_por_tipo=1)
    repositorio = RepositorioReferenciaCentro(dataset, referencia)

    with pytest.raises(ErroReferenciaCentro, match="curta"):
        repositorio.registrar(
            str(repositorio.amostras[0]["id_amostra"]),
            [
                {"x": 0.5, "y": 0.55},
                {"x": 0.5, "y": 0.54},
                {"x": 0.5, "y": 0.53},
                {"x": 0.5, "y": 0.52},
            ],
        )
