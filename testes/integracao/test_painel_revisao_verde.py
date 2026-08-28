import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from obr_oficial.painel.revisao_verde import (
    ErroRevisaoVerde,
    RepositorioRevisaoVerde,
    criar_painel_revisao_verde,
)


def _preparar(tmp_path: Path, divisao: str = "treino") -> RepositorioRevisaoVerde:
    brutos = tmp_path / "brutos"
    candidatas = tmp_path / "candidatas"
    (brutos / "sessao").mkdir(parents=True)
    (candidatas / "mascaras" / "sessao").mkdir(parents=True)
    imagem = np.full((48, 64, 3), 230, dtype=np.uint8)
    cv2.rectangle(imagem, (8, 20), (24, 42), (35, 120, 45), -1)
    mascara = np.zeros((48, 64), dtype=np.uint8)
    mascara[20:43, 8:25] = 255
    assert cv2.imwrite(str(brutos / "sessao" / "quadro.png"), imagem)
    assert cv2.imwrite(
        str(candidatas / "mascaras" / "sessao" / "quadro.png"),
        mascara,
    )
    registro = {
        "id_amostra": "sessao:1",
        "divisao": divisao,
        "categoria_verde": "antes_esquerda",
        "cruz_mista": False,
        "origem": "sessao/quadro.png",
        "mascara_candidata": "mascaras/sessao/quadro.png",
        "confianca_bootstrap": 0.7,
        "area_mascara_normalizada": 0.12,
        "quantidade_marcadores_esperada": 1,
        "quantidade_componentes_selecionada": 1,
        "prioridade": "prioritaria",
        "fila_revisao_essencial": True,
        "grupo_revisao": "verde-prioridade-0001",
        "motivos_prioridade": ["confianca_baixa"],
        "revisao_inicial": "pendente",
    }
    (candidatas / "candidatas.jsonl").write_text(
        json.dumps(registro) + "\n",
        encoding="utf-8",
    )
    return RepositorioRevisaoVerde(brutos, candidatas)


def test_painel_verde_filtra_renderiza_e_registra(tmp_path: Path) -> None:
    app = criar_painel_revisao_verde(_preparar(tmp_path))
    cliente = app.test_client()

    resposta = cliente.get("/api/amostra?prioridade=fila&revisao=pendente")
    assert resposta.status_code == 200
    assert resposta.json["amostra"]["id_amostra"] == "sessao:1"
    assert resposta.json["resumo"]["fila_revisao_essencial"] == 1
    assert cliente.get("/api/imagem/0/sobreposicao").mimetype == "image/jpeg"
    revisao = cliente.post(
        "/api/revisoes",
        json={"id_amostra": "sessao:1", "decisao": "aprovada", "observacao": "ok"},
    )
    assert revisao.status_code == 201
    assert cliente.get("/api/amostra?revisao=pendente").json["total"] == 0
    assert cliente.get("/api/amostra?prioridade=todas&revisao=aprovada").json["total"] == 1


def test_painel_verde_recusa_teste(tmp_path: Path) -> None:
    with pytest.raises(ErroRevisaoVerde, match="divisao de teste"):
        _preparar(tmp_path, divisao="teste")
