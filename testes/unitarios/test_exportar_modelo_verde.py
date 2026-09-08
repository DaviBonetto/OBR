from pathlib import Path

from obr_oficial.aplicacao import exportar_modelo_verde


def test_exporta_candidato_verde_com_gates_especificos(tmp_path: Path, monkeypatch) -> None:
    manifesto_salvo = {}
    argumentos_recebidos = {}

    def preparar_pacote(checkpoint: Path, onnx: Path, dataset: Path, **opcoes):
        argumentos_recebidos.update(
            checkpoint=checkpoint,
            onnx=onnx,
            dataset=dataset,
            **opcoes,
        )
        return {
            "validacao_limiar_calibrado": {
                "dice": 0.951,
                "precisao": 0.971,
                "recall": 0.931,
                "taxa_falso_positivo_negativos_significativos": 0.0,
            }
        }

    monkeypatch.setattr(exportar_modelo_verde, "raiz_projeto", lambda: tmp_path)
    monkeypatch.setattr(exportar_modelo_verde, "preparar_pacote", preparar_pacote)
    monkeypatch.setattr(
        exportar_modelo_verde,
        "salvar_manifesto",
        lambda manifesto, destino: manifesto_salvo.update(manifesto=manifesto, destino=destino),
    )

    assert exportar_modelo_verde.main([]) == 0

    assert argumentos_recebidos["limiar"] == 0.75
    assert manifesto_salvo["manifesto"]["gates_validacao"]["aprovado"] is True
    assert manifesto_salvo["manifesto"]["tarefa"] == "segmentacao_binaria_de_marcadores_verdes"
    assert manifesto_salvo["manifesto"]["estado"].startswith("candidato_fase_verde_4")
