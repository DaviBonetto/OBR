"""Buffer de tamanho um: consumidores nunca acumulam quadros antigos."""

from __future__ import annotations

from dataclasses import replace
from threading import Condition
from time import monotonic

from obr_oficial.dispositivos.camera_base import QuadroCamera


class BufferUltimoQuadro:
    """Publica somente o quadro mais recente e permite espera limitada."""

    def __init__(self) -> None:
        self._condicao = Condition()
        self._quadro: QuadroCamera | None = None

    def publicar(self, quadro: QuadroCamera) -> None:
        with self._condicao:
            self._quadro = quadro
            self._condicao.notify_all()

    def obter(
        self,
        *,
        depois_de: int | None = None,
        timeout_s: float = 0.0,
    ) -> QuadroCamera | None:
        limite = monotonic() + max(timeout_s, 0.0)
        with self._condicao:
            while self._quadro is None or (
                depois_de is not None and self._quadro.id_quadro <= depois_de
            ):
                restante = limite - monotonic()
                if restante <= 0.0:
                    return None
                self._condicao.wait(restante)

            quadro = self._quadro
            return replace(quadro, imagem_bgr=quadro.imagem_bgr.copy())
