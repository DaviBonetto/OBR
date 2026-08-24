"""Gravacao rastreavel de imagens e metadados para os datasets."""

from obr_oficial.captura.gerenciador_sessoes import (
    ErroCaptura,
    GerenciadorSessoesCaptura,
)
from obr_oficial.captura.protocolo_verde import (
    CategoriaCapturaVerde,
    contexto_quadro_verde,
    contexto_sessao_verde,
    esquema_captura_verde,
)

__all__ = [
    "CategoriaCapturaVerde",
    "ErroCaptura",
    "GerenciadorSessoesCaptura",
    "contexto_quadro_verde",
    "contexto_sessao_verde",
    "esquema_captura_verde",
]
