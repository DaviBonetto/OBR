"""Painel de operacao OBR: observacao ao vivo e ajuste de tempos de virada."""

from obr_oficial.painel.operacao.captura import CapturadorOperacao
from obr_oficial.painel.operacao.persistencia import GerenciadorViradas
from obr_oficial.painel.operacao.servidor import criar_painel_operacao

__all__ = ["CapturadorOperacao", "GerenciadorViradas", "criar_painel_operacao"]
