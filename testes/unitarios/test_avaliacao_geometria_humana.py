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
from obr_oficial.percepcao.linha.avaliacao_geometria import avaliar_referencia_humana


class DetectorCentroExato:
    configuracao = SimpleNamespace(largura=320, altura=192)

    def processar(self, imagem, *, id_quadro=0):
        pontos = tuple(PontoNormalizado(0.5, y) for y in (0.0, 0.33, 0.66, 1.0))
        return SimpleNamespace(
            estimativa=EstimativaLinha(
                id_quadro=id_quadro,
                instante_monotonico_s=1.0,
                estado=EstadoDeteccao.ENCONTRADA,
                confianca=0.99,
                centro_linha=pontos,
                ponto_atual=pontos[-1],
                ponto_objetivo=pontos[2],
                tipo_curva=TipoCurva.RETA,
                fonte=FonteEstimativa.IA,
            )
        )


def test_gate_humano_aprova_centro_exato_e_nao_abre_teste(
    tmp_path: Path,
    preparar_dataset_referencia,
) -> None:
    dataset = preparar_dataset_referencia(tmp_path)
    referencia = tmp_path / "referencia"
    preparar_selecao_referencia(dataset, referencia, quantidade_por_tipo=1)
    repositorio = RepositorioReferenciaCentro(dataset, referencia)
    for amostra in repositorio.amostras:
        repositorio.registrar(
            str(amostra["id_amostra"]),
            [
                {"x": 0.5, "y": 1.0},
                {"x": 0.5, "y": 0.66},
                {"x": 0.5, "y": 0.33},
                {"x": 0.5, "y": 0.0},
            ],
        )

    relatorio = avaliar_referencia_humana(DetectorCentroExato(), dataset, referencia)

    assert relatorio["teste_aberto"] is False
    assert relatorio["usa_mascara_como_referencia"] is False
    assert relatorio["referencia_completa"] is True
    assert relatorio["erro_centro_pixels"]["p95"] < 0.01
    assert relatorio["gate"]["aprovado"] is True
