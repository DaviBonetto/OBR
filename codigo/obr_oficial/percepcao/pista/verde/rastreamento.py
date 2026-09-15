"""Confirmacao temporal conservadora das decisoes verdes na intersecao."""

from __future__ import annotations

from collections import deque
from dataclasses import replace
from time import perf_counter

from obr_oficial.nucleo.contratos import DecisaoVerde, EstadoVerde, EstimativaVerde, FonteEstimativa
from obr_oficial.percepcao.pista.verde.configuracao import ConfiguracaoTemporalVerde


class RastreadorVerde:
    """Exige observacoes consecutivas iguais antes de confirmar uma intencao."""

    def __init__(self, configuracao: ConfiguracaoTemporalVerde) -> None:
        self._configuracao = configuracao
        self._historico: deque[EstimativaVerde] = deque(maxlen=configuracao.janela_quadros)

    def atualizar(self, observacao: EstimativaVerde) -> EstimativaVerde:
        """Confirma apenas candidatos consecutivos, ainda visiveis no T."""

        inicio = perf_counter()
        if observacao.decisao is DecisaoVerde.NENHUMA:
            self._historico.clear()
            return self._com_tempo(observacao, inicio)

        if self._historico and self._historico[-1].decisao is not observacao.decisao:
            self._historico.clear()
        self._historico.append(observacao)
        limite_s = self._configuracao.memoria_maxima_ms / 1_000.0
        while (
            self._historico
            and observacao.instante_monotonico_s
            - self._historico[0].instante_monotonico_s
            > limite_s
        ):
            self._historico.popleft()

        if len(self._historico) < self._configuracao.confirmacoes_minimas:
            return self._com_tempo(
                replace(
                    observacao,
                    estado=EstadoVerde.CANDIDATA,
                    motivo="aguardando_confirmacao_temporal_verde",
                ),
                inicio,
            )

        confianca = min(item.confianca for item in self._historico)
        return self._com_tempo(
            replace(
                observacao,
                estado=EstadoVerde.CONFIRMADA,
                confianca=confianca,
                fonte=FonteEstimativa.TEMPORAL,
                motivo="confirmada_temporalmente_na_intersecao",
            ),
            inicio,
        )

    def reiniciar(self) -> None:
        """Descarta observacoes ao trocar fonte, pista ou sessao."""

        self._historico.clear()

    @staticmethod
    def _com_tempo(observacao: EstimativaVerde, inicio: float) -> EstimativaVerde:
        return replace(
            observacao,
            tempos=replace(
                observacao.tempos,
                rastreamento_ms=(perf_counter() - inicio) * 1_000.0,
            ),
        )
