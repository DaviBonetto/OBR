"""Paineis opcionais que observam o sistema sem entrar no caminho critico."""

from obr_oficial.painel.captura import criar_painel_captura
from obr_oficial.painel.revisao_mascaras import (
    RepositorioRevisaoMascaras,
    criar_painel_revisao,
)

__all__ = ["RepositorioRevisaoMascaras", "criar_painel_captura", "criar_painel_revisao"]
