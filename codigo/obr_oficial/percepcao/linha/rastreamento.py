"""Suavizacao e memoria temporal limitada da trajetoria da linha."""

from __future__ import annotations

from dataclasses import replace
from time import perf_counter

import numpy as np

from obr_oficial.nucleo.contratos import (
    EstadoDeteccao,
    EstimativaLinha,
    FonteEstimativa,
    PontoNormalizado,
)
from obr_oficial.percepcao.linha.detector_neural import ConfiguracaoDetectorNeural


class RastreadorLinha:
    """Estabiliza observacoes atuais e limita estritamente previsoes sem imagem."""

    def __init__(self, configuracao: ConfiguracaoDetectorNeural) -> None:
        self.configuracao = configuracao
        self._ultima_valida: EstimativaLinha | None = None
        self._candidata: EstimativaLinha | None = None
        self._confirmacoes = 0

    def reiniciar(self) -> None:
        self._ultima_valida = None
        self._candidata = None
        self._confirmacoes = 0

    def atualizar(self, atual: EstimativaLinha) -> EstimativaLinha:
        inicio = perf_counter()
        if atual.estado is not EstadoDeteccao.PERDIDA and atual.ponto_objetivo is not None:
            if self._rastro_ativo(atual):
                resultado = self._suavizar(atual)
                self._ultima_valida = resultado
                self._limpar_candidata()
            else:
                resultado = self._confirmar_nova_rota(atual)
        else:
            resultado = self._projetar_temporal(atual)
        duracao_ms = (perf_counter() - inicio) * 1000.0
        return replace(
            resultado,
            tempos=replace(
                resultado.tempos,
                rastreamento_ms=resultado.tempos.rastreamento_ms + duracao_ms,
            ),
        )

    def _rastro_ativo(self, atual: EstimativaLinha) -> bool:
        if self._ultima_valida is None:
            return False
        idade_ms = (
            atual.instante_monotonico_s - self._ultima_valida.instante_monotonico_s
        ) * 1000.0
        return 0.0 <= idade_ms <= self.configuracao.idade_maxima_temporal_ms

    def _confirmar_nova_rota(self, atual: EstimativaLinha) -> EstimativaLinha:
        if self._candidata is None or not self._rotas_coerentes(self._candidata, atual):
            self._candidata = atual
            self._confirmacoes = 1
        else:
            self._candidata = atual
            self._confirmacoes += 1
        if self._confirmacoes >= self.configuracao.quadros_confirmacao:
            self._ultima_valida = atual
            self._limpar_candidata()
            return atual
        return replace(
            atual,
            estado=EstadoDeteccao.INCERTA,
            confianca=min(atual.confianca, self.configuracao.limiar_encontrada - 1e-6),
            motivo="aguardando_confirmacao_temporal",
        )

    @staticmethod
    def _rotas_coerentes(primeira: EstimativaLinha, segunda: EstimativaLinha) -> bool:
        if primeira.ponto_atual is None or segunda.ponto_atual is None:
            return False
        if primeira.ponto_objetivo is None or segunda.ponto_objetivo is None:
            return False
        distancia_atual = abs(primeira.ponto_atual.x - segunda.ponto_atual.x)
        distancia_objetivo = abs(primeira.ponto_objetivo.x - segunda.ponto_objetivo.x)
        return distancia_atual <= 0.18 and distancia_objetivo <= 0.25

    def _limpar_candidata(self) -> None:
        self._candidata = None
        self._confirmacoes = 0

    def _suavizar(self, atual: EstimativaLinha) -> EstimativaLinha:
        anterior = self._ultima_valida
        if anterior is None or anterior.ponto_atual is None or anterior.ponto_objetivo is None:
            return atual
        alfa = self.configuracao.suavizacao

        def ponto(novo: PontoNormalizado, velho: PontoNormalizado) -> PontoNormalizado:
            return PontoNormalizado(
                x=float(alfa * novo.x + (1.0 - alfa) * velho.x),
                y=float(alfa * novo.y + (1.0 - alfa) * velho.y),
            )

        ponto_atual = ponto(atual.ponto_atual, anterior.ponto_atual)
        ponto_objetivo = ponto(atual.ponto_objetivo, anterior.ponto_objetivo)
        erro_lateral = (ponto_atual.x - 0.5) * 2.0
        dx = ponto_objetivo.x - ponto_atual.x
        dy = max(1e-6, ponto_atual.y - ponto_objetivo.y)
        erro_angular = float(np.degrees(np.arctan2(dx, dy)))
        return replace(
            atual,
            ponto_atual=ponto_atual,
            ponto_objetivo=ponto_objetivo,
            erro_lateral_normalizado=float(np.clip(erro_lateral, -1, 1)),
            erro_angular_graus=erro_angular,
        )

    def _projetar_temporal(self, atual: EstimativaLinha) -> EstimativaLinha:
        anterior = self._ultima_valida
        if anterior is None:
            self._limpar_candidata()
            return atual
        idade_ms = (atual.instante_monotonico_s - anterior.instante_monotonico_s) * 1000.0
        if idade_ms < 0.0 or idade_ms > self.configuracao.idade_maxima_temporal_ms:
            self._ultima_valida = None
            self._limpar_candidata()
            return atual
        fracao = idade_ms / self.configuracao.idade_maxima_temporal_ms
        confianca = max(
            self.configuracao.limiar_incerta,
            anterior.confianca * (1.0 - 0.55 * fracao),
        )
        return replace(
            anterior,
            id_quadro=atual.id_quadro,
            instante_monotonico_s=atual.instante_monotonico_s,
            estado=EstadoDeteccao.INCERTA,
            confianca=confianca,
            fonte=FonteEstimativa.TEMPORAL,
            idade_observacao_ms=idade_ms,
            motivo="gap_temporal_mantendo_ultima_direcao",
            tempos=atual.tempos,
        )
