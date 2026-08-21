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
        assert "Captura de Dataset" in pagina.get_data(as_text=True)

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
