"""Paineis opcionais que observam o sistema sem entrar no caminho critico."""

from obr_oficial.painel.captura import criar_painel_captura
from obr_oficial.painel.percepcao_linha import criar_painel_percepcao_linha
from obr_oficial.painel.referencia_centro import criar_painel_referencia_centro
from obr_oficial.painel.revisao_mascaras import (
    RepositorioRevisaoMascaras,
    criar_painel_revisao,
)
from obr_oficial.painel.revisao_verde import (
    RepositorioRevisaoVerde,
    criar_painel_revisao_verde,
)

__all__ = [
    "RepositorioRevisaoMascaras",
    "RepositorioRevisaoVerde",
    "criar_painel_captura",
    "criar_painel_percepcao_linha",
    "criar_painel_referencia_centro",
    "criar_painel_revisao",
    "criar_painel_revisao_verde",
]
