import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from obr_oficial.dados.mascaras_classicas import (
    ConfiguracaoGeracaoMascaras,
    ErroGeracaoMascaras,
    GeradorMascarasClassicas,
)
from obr_oficial.nucleo.contratos import EstadoDeteccao
from obr_oficial.percepcao.linha import ConfiguracaoDetectorClassico, DetectorClassicoLinha


def _configuracao() -> ConfiguracaoDetectorClassico:
    return ConfiguracaoDetectorClassico(
        largura=160,
        altura=96,
        roi_y=0.0,
        roi_altura=1.0,
        limite_clahe=2.0,
        grade_clahe=8,
        bloco_adaptativo=21,
        constante_adaptativa=7.0,
        kernel_abertura=3,
        kernel_fechamento=5,
        area_minima=0.01,
        area_maxima=0.75,
        altura_minima=0.25,
        nitidez_borda_minima=25.0,
        confianca_encontrada=0.58,
        confianca_incerta=0.35,
        linhas_centro=13,
        fator_largura_intersecao=1.8,
    )


def _detector() -> DetectorClassicoLinha:
    return DetectorClassicoLinha(_configuracao())


def _imagem_branca() -> np.ndarray:
    return np.full((96, 160, 3), 235, dtype=np.uint8)


def test_detecta_linha_reta_em_iluminacao_desigual() -> None:
    gradiente = np.linspace(170, 255, 160, dtype=np.uint8)
    cinza = np.repeat(gradiente[np.newaxis, :], 96, axis=0)
    imagem = cv2.cvtColor(cinza, cv2.COLOR_GRAY2BGR)
    cv2.rectangle(imagem, (68, 0), (92, 95), (10, 10, 10), -1)

    resultado = _detector().processar(imagem)

    assert resultado.estimativa.estado in {
        EstadoDeteccao.ENCONTRADA,
        EstadoDeteccao.INCERTA,
    }
    assert resultado.estimativa.ponto_atual is not None
    assert resultado.estimativa.ponto_atual.x == pytest.approx(0.5, abs=0.08)
    assert resultado.area_normalizada > 0.10


def test_intersecao_t_mantem_continuacao_reta() -> None:
    imagem = _imagem_branca()
    cv2.rectangle(imagem, (68, 0), (92, 95), (5, 5, 5), -1)
    cv2.rectangle(imagem, (8, 35), (151, 55), (5, 5, 5), -1)

    resultado = _detector().processar(imagem)

    xs = [ponto.x for ponto in resultado.estimativa.centro_linha]
    assert len(xs) >= 8
    assert max(abs(x - 0.5) for x in xs) < 0.10
    assert resultado.estimativa.ponto_objetivo is not None
    assert resultado.estimativa.ponto_objetivo.x == pytest.approx(0.5, abs=0.10)


def test_sem_linha_produz_sem_evidencia() -> None:
    resultado = _detector().processar(_imagem_branca())

    assert resultado.estimativa.estado is EstadoDeteccao.PERDIDA
    assert resultado.estimativa.motivo == "sem_evidencia_suficiente"
    assert np.count_nonzero(resultado.mascara) == 0


def _registro(divisao: str, tipo: str, caminho: str, indice: int) -> dict[str, object]:
    return {
        "id_amostra": f"amostra:{indice}",
        "selecionada": True,
        "divisao": divisao,
        "tipo_quadro": tipo,
        "trajetoria_desejada": "reto" if tipo == "intersecao" else "seguir_linha",
        "origem": {"caminho_relativo_raiz": caminho},
    }


def test_gerador_nao_abre_divisao_de_teste(tmp_path: Path) -> None:
    brutos = tmp_path / "brutos"
    processado = tmp_path / "processado"
    brutos.mkdir()
    processado.mkdir()
    imagem = _imagem_branca()
    cv2.rectangle(imagem, (68, 0), (92, 95), (5, 5, 5), -1)
    (brutos / "sessao" / "quadros").mkdir(parents=True)
    caminho_treino = "sessao/quadros/quadro.png"
    assert cv2.imwrite(str(brutos / caminho_treino), imagem)
    registros = [
        _registro("treino", "reta", caminho_treino, 1),
        # O arquivo propositalmente nao existe: se o teste for aberto, a geracao falha.
        _registro("teste", "reta", "teste/nao_abrir.png", 2),
    ]
    (processado / "amostras.jsonl").write_text(
        "".join(json.dumps(registro) + "\n" for registro in registros),
        encoding="utf-8",
    )
    saida = tmp_path / "saida"

    manifesto = GeradorMascarasClassicas(
        ConfiguracaoGeracaoMascaras(brutos, processado, saida, intervalo_sobreposicao=1),
        _detector(),
        hash_configuracao_detector="a" * 64,
    ).gerar()

    assert manifesto["divisao_teste_processada"] is False
    assert manifesto["quantidades"]["total"] == 1
    auditoria = (saida / "candidatas.jsonl").read_text(encoding="utf-8")
    assert '"divisao": "teste"' not in auditoria
    assert (saida / "mascaras" / caminho_treino).is_file()


def test_gerador_nao_sobrescreve_saida(tmp_path: Path) -> None:
    saida = tmp_path / "saida"
    saida.mkdir()
    with pytest.raises(ErroGeracaoMascaras, match="Saida ja existe"):
        GeradorMascarasClassicas(
            ConfiguracaoGeracaoMascaras(tmp_path, tmp_path, saida),
            _detector(),
            hash_configuracao_detector="a" * 64,
        ).gerar()
