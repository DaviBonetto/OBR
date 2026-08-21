import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from obr_oficial.painel.revisao_mascaras import (
    ErroRevisaoMascaras,
    RepositorioRevisaoMascaras,
    criar_painel_revisao,
)


def _preparar(tmp_path: Path, divisao: str = "treino") -> RepositorioRevisaoMascaras:
    brutos = tmp_path / "brutos"
    candidatas = tmp_path / "candidatas"
    (brutos / "sessao").mkdir(parents=True)
    (candidatas / "mascaras" / "sessao").mkdir(parents=True)
    origem = np.full((48, 64, 3), 230, dtype=np.uint8)
    cv2.rectangle(origem, (26, 0), (38, 47), (5, 5, 5), -1)
    mascara = np.zeros((32, 48), dtype=np.uint8)
    mascara[:, 19:29] = 255
    assert cv2.imwrite(str(brutos / "sessao" / "quadro.png"), origem)
    assert cv2.imwrite(str(candidatas / "mascaras" / "sessao" / "quadro.png"), mascara)
    registro = {
        "id_amostra": "sessao:1",
        "divisao": divisao,
        "tipo_quadro": "reta",
        "origem": "sessao/quadro.png",
        "mascara_candidata": "mascaras/sessao/quadro.png",
        "estado": "encontrada",
        "confianca": 0.9,
        "latencia_ms": 4.2,
    }
    (candidatas / "candidatas.jsonl").write_text(
        json.dumps(registro) + "\n",
        encoding="utf-8",
    )
    return RepositorioRevisaoMascaras(brutos, candidatas)


def test_painel_consulta_renderiza_e_registra_revisao(tmp_path: Path) -> None:
    app = criar_painel_revisao(_preparar(tmp_path))
    cliente = app.test_client()

    resposta = cliente.get("/api/amostra?revisao=pendente")
    assert resposta.status_code == 200
    assert resposta.json["amostra"]["id_amostra"] == "sessao:1"
    assert cliente.get("/api/imagem/0/sobreposicao").mimetype == "image/jpeg"

    revisao = cliente.post(
        "/api/revisoes",
        json={"id_amostra": "sessao:1", "decisao": "aprovada", "observacao": "ok"},
    )
    assert revisao.status_code == 201
    assert cliente.get("/api/amostra?revisao=pendente").json["total"] == 0
    assert cliente.get("/api/amostra?revisao=aprovada").json["total"] == 1


def test_painel_rejeita_decisao_invalida(tmp_path: Path) -> None:
    cliente = criar_painel_revisao(_preparar(tmp_path)).test_client()

    resposta = cliente.post(
        "/api/revisoes",
        json={"id_amostra": "sessao:1", "decisao": "inventada"},
    )

    assert resposta.status_code == 400
    assert "invalida" in resposta.json["erro"]


def test_repositorio_recusa_qualquer_candidata_de_teste(tmp_path: Path) -> None:
    with pytest.raises(ErroRevisaoMascaras, match="divisao de teste"):
        _preparar(tmp_path, divisao="teste")
