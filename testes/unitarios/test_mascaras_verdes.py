import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from obr_oficial.dados import (
    ConfiguracaoGeracaoMascarasVerdes,
    ConfiguracaoMascarasVerdes,
    DetectorCromaticoVerde,
    GeradorMascarasVerdes,
)
from obr_oficial.dados.mascaras_verdes import _marcar_fila_revisao_essencial


def _configuracao() -> ConfiguracaoMascarasVerdes:
    return ConfiguracaoMascarasVerdes(
        versao=1,
        matiz_minima=32,
        matiz_maxima=100,
        saturacao_minima=35,
        valor_minimo=15,
        excesso_verde_minimo=12,
        diferenca_verde_vermelho_minima=3,
        abertura_px=5,
        fechamento_px=3,
        area_componente_minima=0.0008,
        penalidade_borda=0.90,
        limiar_prioridade=0.70,
        razao_ambiguidade=0.65,
        area_por_marcador_minima=0.02,
        area_por_marcador_maxima=0.32,
        hash_arquivo="a" * 64,
    )


def _imagem_com_quadrados(quantidade: int) -> np.ndarray:
    imagem = np.full((120, 180, 3), 225, dtype=np.uint8)
    cv2.rectangle(imagem, (82, 0), (98, 119), (5, 5, 5), -1)
    if quantidade >= 1:
        cv2.rectangle(imagem, (20, 50), (70, 105), (45, 125, 55), -1)
    if quantidade >= 2:
        cv2.rectangle(imagem, (110, 50), (160, 105), (45, 125, 55), -1)
    return imagem


def _gravar_imagem(caminho: Path, imagem: np.ndarray) -> str:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    sucesso, codificada = cv2.imencode(".png", imagem)
    assert sucesso
    conteudo = codificada.tobytes()
    caminho.write_bytes(conteudo)
    return hashlib.sha256(conteudo).hexdigest()


def test_detector_seleciona_quantidade_esperada_e_forca_negativo_vazio() -> None:
    detector = DetectorCromaticoVerde(_configuracao())

    simples = detector.processar(
        _imagem_com_quadrados(1),
        categoria="antes_esquerda",
        cruz_mista=False,
    )
    duplo = detector.processar(
        _imagem_com_quadrados(2),
        categoria="dois_antes_180",
        cruz_mista=False,
    )
    negativo = detector.processar(
        _imagem_com_quadrados(1),
        categoria="sem_verde_negativo",
        cruz_mista=False,
    )

    assert simples.quantidade_selecionada == 1
    assert np.count_nonzero(simples.mascara) > 2_000
    assert duplo.quantidade_selecionada == 2
    assert np.count_nonzero(duplo.mascara) > np.count_nonzero(simples.mascara)
    assert negativo.quantidade_esperada == 0
    assert np.count_nonzero(negativo.mascara) == 0
    assert negativo.prioridade == "contrato"


def test_mascara_cromatica_nao_muda_com_papel_antes_ou_depois() -> None:
    detector = DetectorCromaticoVerde(_configuracao())
    imagem = _imagem_com_quadrados(1)

    antes = detector.processar(imagem, categoria="antes_esquerda", cruz_mista=False)
    depois = detector.processar(imagem, categoria="depois_ignorar", cruz_mista=False)

    assert np.array_equal(antes.mascara, depois.mascara)


def test_detector_prefere_marcador_claro_a_reflexo_escuro_maior() -> None:
    detector = DetectorCromaticoVerde(_configuracao())
    imagem = np.full((180, 220, 3), 225, dtype=np.uint8)
    cv2.rectangle(imagem, (25, 15), (95, 80), (35, 180, 45), -1)
    cv2.rectangle(imagem, (105, 90), (205, 175), (20, 70, 25), -1)

    resultado = detector.processar(imagem, categoria="antes_esquerda", cruz_mista=False)

    assert resultado.mascara[45, 55] == 255
    assert resultado.mascara[130, 155] == 0


def test_detector_suprime_reflexo_inferior_mais_regular() -> None:
    detector = DetectorCromaticoVerde(_configuracao())
    imagem = np.full((220, 240, 3), 225, dtype=np.uint8)
    cv2.rectangle(imagem, (90, 0), (225, 68), (65, 170, 75), -1)
    cv2.rectangle(imagem, (20, 115), (180, 219), (8, 105, 18), -1)

    resultado = detector.processar(imagem, categoria="antes_esquerda", cruz_mista=False)

    assert resultado.mascara[30, 160] == 255
    assert resultado.mascara[165, 90] == 0
    assert "componente_extra_ambiguo" in resultado.motivos_prioridade


def test_detector_preenche_brilho_interno_na_silhueta_do_marcador() -> None:
    detector = DetectorCromaticoVerde(_configuracao())
    imagem = _imagem_com_quadrados(1)
    cv2.rectangle(imagem, (38, 62), (51, 91), (250, 250, 250), -1)

    resultado = detector.processar(imagem, categoria="antes_esquerda", cruz_mista=False)

    assert resultado.mascara[75, 45] == 255


def test_fila_essencial_escolhe_menor_confianca_por_sequencia() -> None:
    def registro(quadro: int, confianca: float) -> dict[str, object]:
        return {
            "id_amostra": f"sessao:quadro-{quadro}",
            "origem": f"sessao/quadros/quadro_{quadro:06d}.png",
            "categoria_verde": "antes_esquerda",
            "cruz_mista": False,
            "prioridade": "prioritaria",
            "motivos_prioridade": ["confianca_baixa"],
            "confianca_bootstrap": confianca,
        }

    registros = [registro(1, 0.5), registro(5, 0.4), registro(20, 0.3)]

    quantidade = _marcar_fila_revisao_essencial(registros)

    assert quantidade == 2
    assert [item["fila_revisao_essencial"] for item in registros] == [False, True, True]
    assert registros[0]["grupo_revisao"] == registros[1]["grupo_revisao"]
    assert registros[1]["grupo_revisao"] != registros[2]["grupo_revisao"]


def test_gerador_nao_abre_teste_e_preserva_hashes(tmp_path: Path) -> None:
    brutos = tmp_path / "brutos"
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    registros = []
    definicoes = (
        ("treino:1", "treino", "dois_antes_180", _imagem_com_quadrados(1)),
        ("validacao:1", "validacao", "sem_verde_negativo", _imagem_com_quadrados(0)),
    )
    for id_amostra, divisao, categoria, imagem in definicoes:
        relativo = Path(divisao) / f"{id_amostra.split(':')[1]}.png"
        hash_imagem = _gravar_imagem(brutos / relativo, imagem)
        registros.append(
            {
                "id_amostra": id_amostra,
                "divisao": divisao,
                "origem": {
                    "caminho_relativo_raiz": relativo.as_posix(),
                    "sha256": hash_imagem,
                },
                "contexto_efetivo": {
                    "categoria_verde": categoria,
                    "cruz_mista": False,
                    "decisao_verde_esperada": "nenhuma",
                },
            }
        )
    registros.append(
        {
            "id_amostra": "teste:arquivo_inexistente",
            "divisao": "teste",
            "origem": {
                "caminho_relativo_raiz": "teste/nao_pode_ser_aberto.png",
                "sha256": "0" * 64,
            },
            "contexto_efetivo": {
                "categoria_verde": "antes_esquerda",
                "cruz_mista": False,
                "decisao_verde_esperada": "virar_esquerda",
            },
        }
    )
    (dataset / "amostras.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in registros),
        encoding="utf-8",
    )
    hashes_antes = {
        caminho: hashlib.sha256(caminho.read_bytes()).hexdigest()
        for caminho in brutos.rglob("*.png")
    }
    saida = tmp_path / "candidatas"

    manifesto = GeradorMascarasVerdes(
        ConfiguracaoGeracaoMascarasVerdes(brutos, dataset, saida),
        DetectorCromaticoVerde(_configuracao()),
    ).gerar()

    assert manifesto["divisao_teste_processada"] is False
    assert manifesto["quantidades"]["total"] == 2
    assert manifesto["pronto_para_treinamento"] is False
    assert len(manifesto["hash_implementacao"]) == 64
    assert len(manifesto["hash_candidatas"]) == 64
    candidatas = [
        json.loads(linha)
        for linha in (saida / "candidatas.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {item["divisao"] for item in candidatas} == {"treino", "validacao"}
    negativa = next(item for item in candidatas if item["categoria_verde"].startswith("sem_"))
    assert negativa["revisao_inicial"] == "aprovada_vazia_por_contrato"
    assert all("latencia_ms" not in item for item in candidatas)
    prioritaria = next(item for item in candidatas if item["prioridade"] == "prioritaria")
    assert prioritaria["fila_revisao_essencial"] is True
    assert prioritaria["grupo_revisao"] == "verde-prioridade-0001"
    assert hashes_antes == {
        caminho: hashlib.sha256(caminho.read_bytes()).hexdigest()
        for caminho in brutos.rglob("*.png")
    }
