import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from obr_oficial.dados.consolidacao_rotulos import (
    ConfiguracaoConsolidacaoRotulos,
    ConsolidadorRotulos,
    ErroConsolidacaoRotulos,
)


def _preparar_candidatas(tmp_path: Path, incluir_teste: bool = False) -> Path:
    pasta = tmp_path / "candidatas"
    mascaras = pasta / "mascaras"
    mascaras.mkdir(parents=True)
    registros = []
    especificacoes = [
        ("pendente_linha", "reta", "treino"),
        ("vazia_linha", "curva_aberta", "validacao"),
        ("reprocessar_linha", "intersecao", "treino"),
        ("reprocessar_negativo", "sem_linha", "validacao"),
        ("pendente_negativo", "sem_linha", "treino"),
    ]
    if incluir_teste:
        especificacoes.append(("teste", "reta", "teste"))
    for indice, (identificador, tipo, divisao) in enumerate(especificacoes):
        mascara = np.zeros((24, 32), dtype=np.uint8)
        mascara[:, 12:20] = 255
        nome = f"{indice}.png"
        assert cv2.imwrite(str(mascaras / nome), mascara)
        registros.append(
            {
                "id_amostra": identificador,
                "divisao": divisao,
                "tipo_quadro": tipo,
                "trajetoria_desejada": "reto" if tipo == "intersecao" else "seguir_linha",
                "origem": f"origem/{nome}",
                "mascara_candidata": f"mascaras/{nome}",
            }
        )
    (pasta / "candidatas.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in registros),
        encoding="utf-8",
    )
    revisoes = [
        {"id_amostra": "vazia_linha", "decisao": "mascara_vazia", "observacao": ""},
        {"id_amostra": "reprocessar_linha", "decisao": "reprocessar", "observacao": ""},
        {"id_amostra": "reprocessar_negativo", "decisao": "reprocessar", "observacao": ""},
    ]
    (pasta / "revisoes.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in revisoes),
        encoding="utf-8",
    )
    return pasta


def test_consolida_regra_do_usuario_sem_inventar_rotulo(tmp_path: Path) -> None:
    candidatas = _preparar_candidatas(tmp_path)
    saida = tmp_path / "saida"

    manifesto = ConsolidadorRotulos(
        ConfiguracaoConsolidacaoRotulos(candidatas, saida)
    ).consolidar()

    assert manifesto["quantidades"] == {
        "amostras": 5,
        "revisoes_explicitas_unicas": 3,
        "aprovacoes_implicitas": 2,
        "rotulos_supervisionados": 4,
        "mascaras_positivas": 1,
        "mascaras_vazias": 3,
        "fila_correcao": 1,
        "treino_supervisionado": 2,
        "validacao_supervisionada": 2,
    }
    anotacoes = {
        item["id_amostra"]: item
        for item in (
            json.loads(linha)
            for linha in (saida / "anotacoes.jsonl").read_text(encoding="utf-8").splitlines()
        )
    }
    assert anotacoes["pendente_linha"]["estado_rotulo"] == "aprovada_por_regra_usuario"
    assert anotacoes["reprocessar_linha"]["mascara"] is None
    assert anotacoes["reprocessar_negativo"]["estado_rotulo"] == (
        "aprovada_vazia_por_contrato"
    )
    for identificador in ("vazia_linha", "reprocessar_negativo", "pendente_negativo"):
        caminho = saida / anotacoes[identificador]["mascara"]
        imagem = cv2.imread(str(caminho), cv2.IMREAD_GRAYSCALE)
        assert np.count_nonzero(imagem) == 0
    assert (saida / "fila_correcao.jsonl").read_text().count("\n") == 1


def test_recusa_divisao_de_teste_e_remove_saida_parcial(tmp_path: Path) -> None:
    candidatas = _preparar_candidatas(tmp_path, incluir_teste=True)
    saida = tmp_path / "saida"

    with pytest.raises(ErroConsolidacaoRotulos, match="divisao de teste"):
        ConsolidadorRotulos(ConfiguracaoConsolidacaoRotulos(candidatas, saida)).consolidar()

    assert not saida.exists()


def test_nao_sobrescreve_saida(tmp_path: Path) -> None:
    candidatas = _preparar_candidatas(tmp_path)
    saida = tmp_path / "saida"
    saida.mkdir()

    with pytest.raises(ErroConsolidacaoRotulos, match="Saida ja existe"):
        ConsolidadorRotulos(ConfiguracaoConsolidacaoRotulos(candidatas, saida)).consolidar()
