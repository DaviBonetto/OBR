import json
import re
from pathlib import Path

from obr_oficial.captura import GerenciadorSessoesCaptura
from obr_oficial.dispositivos.camera_simulada import CameraSimulada
from obr_oficial.painel import criar_painel_captura


def test_fluxo_http_completo_de_uma_sessao(tmp_path: Path) -> None:
    camera = CameraSimulada(largura=160, altura=120, fps=20.0)
    sessoes = GerenciadorSessoesCaptura(tmp_path)
    camera.iniciar()
    try:
        app = criar_painel_captura(camera, sessoes)
        cliente = app.test_client()

        pagina = cliente.get("/")
        assert pagina.status_code == 200
        html = pagina.get_data(as_text=True)
        assert "Captura de Dataset" in html
        trecho_opcoes = html.split('<select id="tipo-quadro">', 1)[1].split("</select>", 1)[0]
        assert re.findall(r'<option value="([^"]+)">([^<]+)</option>', trecho_opcoes) == [
            ("reta", "Linha reta"),
            ("curva_fechada", "Curva fechada"),
            ("curva_aberta", "Curva aberta"),
            ("intersecao", "Interseção em T — seguir reto"),
            ("sem_linha", "Sem linha / negativo"),
        ]

        estado = cliente.get("/api/estado")
        assert estado.status_code == 200
        assert estado.get_json()["camera"]["saudavel"] is True

        inicio = cliente.post(
            "/api/sessoes",
            json={"contexto": {"nome": "integracao", "local": "teste"}},
        )
        assert inicio.status_code == 201

        captura = cliente.post(
            "/api/capturas",
            json={"contexto": {"tipo_quadro": "reta"}},
        )
        assert captura.status_code == 201
        assert captura.get_json()["registro"]["numero"] == 1

        finalizacao = cliente.post("/api/sessoes/atual/finalizar", json={})
        assert finalizacao.status_code == 200
        assert finalizacao.get_json()["captura"]["ativa"] is False
    finally:
        sessoes.finalizar_se_ativa()
        camera.parar()


def test_fluxo_verde_valida_rotulo_e_mantem_contagens(tmp_path: Path) -> None:
    camera = CameraSimulada(largura=160, altura=120, fps=20.0)
    sessoes = GerenciadorSessoesCaptura(tmp_path)
    camera.iniciar()
    try:
        app = criar_painel_captura(camera, sessoes, modo="verde")
        cliente = app.test_client()

        pagina = cliente.get("/")
        assert pagina.status_code == 200
        html = pagina.get_data(as_text=True)
        assert "Captura do Verde" in html
        assert re.findall(r'name="categoria-verde" value="([^"]+)"', html) == [
            "antes_esquerda",
            "antes_direita",
            "dois_antes_180",
            "depois_ignorar",
            "sem_verde_negativo",
        ]

        esquema = cliente.get("/api/esquema-captura").get_json()["esquema"]
        assert esquema["tarefa"] == "verde"
        assert esquema["ausencia_verde_interrompe_linha"] is False

        inicio = cliente.post(
            "/api/sessoes",
            json={"contexto": {"nome": "verde", "local": "quadra", "tarefa": "linha"}},
        )
        assert inicio.status_code == 201
        sessao = inicio.get_json()["captura"]["sessao"]
        assert sessao["contexto"]["tarefa"] == "verde"

        esquerda = cliente.post(
            "/api/capturas",
            json={
                "contexto": {
                    "categoria_verde": "antes_esquerda",
                    "cruz_mista": True,
                }
            },
        )
        assert esquerda.status_code == 201
        contexto = esquerda.get_json()["registro"]["contexto"]
        assert contexto["decisao_verde_esperada"] == "virar_esquerda"
        assert contexto["marcador_depois_presente"] is True

        negativo = cliente.post(
            "/api/capturas",
            json={"contexto": {"categoria_verde": "sem_verde_negativo"}},
        )
        assert negativo.status_code == 201
        contexto_negativo = negativo.get_json()["registro"]["contexto"]
        assert contexto_negativo["mascara_marcador_verde_esperada_vazia"] is True
        assert contexto_negativo["decisao_verde_esperada"] == "nenhuma"

        invalida = cliente.post(
            "/api/capturas",
            json={"contexto": {"categoria_verde": "sem_verde_negativo", "cruz_mista": True}},
        )
        assert invalida.status_code == 400

        estado = cliente.get("/api/estado").get_json()
        assert estado["modo_captura"] == "verde"
        assert estado["captura"]["sessao"]["contagens_por_categoria"] == {
            "antes_esquerda": 1,
            "sem_verde_negativo": 1,
        }

        pasta = Path(estado["captura"]["pasta"])
        registros = [
            json.loads(linha)
            for linha in (pasta / "capturas.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert len(registros) == 2
        assert registros[0]["contexto"]["tarefa"] == "verde"
    finally:
        sessoes.finalizar_se_ativa()
        camera.parar()
