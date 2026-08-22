from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from obr_oficial.dados.referencia_centro import (
    RepositorioReferenciaCentro,
    preparar_selecao_referencia,
)
from obr_oficial.nucleo.contratos import (
    EstadoDeteccao,
    EstimativaLinha,
    FonteEstimativa,
    PontoNormalizado,
    TipoCurva,
)
from obr_oficial.painel.referencia_centro import criar_painel_referencia_centro


class DetectorFalso:
    configuracao = SimpleNamespace(roi_y=0.3, largura=320, altura=192)

    def processar(self, imagem, *, id_quadro=0):
        pontos = (
            PontoNormalizado(0.5, 0.0),
            PontoNormalizado(0.5, 0.5),
            PontoNormalizado(0.5, 1.0),
        )
        estimativa = EstimativaLinha(
            id_quadro=id_quadro,
            instante_monotonico_s=1.0,
            estado=EstadoDeteccao.ENCONTRADA,
            confianca=0.95,
            centro_linha=pontos,
            ponto_atual=pontos[-1],
            ponto_objetivo=pontos[1],
            tipo_curva=TipoCurva.RETA,
            fonte=FonteEstimativa.IA,
        )
        return SimpleNamespace(estimativa=estimativa)


def test_painel_renderiza_salva_e_revela_previsao(
    tmp_path: Path,
    preparar_dataset_referencia,
) -> None:
    dataset = preparar_dataset_referencia(tmp_path)
    referencia = tmp_path / "referencia"
    preparar_selecao_referencia(dataset, referencia, quantidade_por_tipo=1)
    repositorio = RepositorioReferenciaCentro(dataset, referencia)
    cliente = criar_painel_referencia_centro(repositorio, DetectorFalso()).test_client()

    consulta = cliente.get("/api/amostra?estado=pendentes")
    assert consulta.status_code == 200
    amostra = consulta.json["amostra"]
    assert cliente.get(f"/api/imagem/{amostra['indice_original']}").mimetype == "image/jpeg"
    previsao = cliente.get(f"/api/previsao/{amostra['indice_original']}")
    assert previsao.status_code == 200
    assert len(previsao.json["estimativa"]["centro_linha"]) == 3

    resposta = cliente.post(
        "/api/anotacoes",
        json={
            "id_amostra": amostra["id_amostra"],
            "pontos": [
                {"x": 0.5, "y": 1.0},
                {"x": 0.5, "y": 0.7},
                {"x": 0.5, "y": 0.4},
                {"x": 0.5, "y": 0.0},
            ],
        },
    )
    assert resposta.status_code == 201
    assert cliente.get("/api/amostra?estado=anotadas").json["total"] == 1
