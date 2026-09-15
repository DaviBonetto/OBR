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

    def atualizar(
        self,
        observacao: EstimativaVerde,
        *,
        intersecao_detectada: bool,
    ) -> EstimativaVerde:
        """Guarda evidência antes do T e só publica decisão quando ele chega."""

        inicio = perf_counter()
        if observacao.decisao is DecisaoVerde.NENHUMA:
            self._expirar(observacao.instante_monotonico_s)
            if intersecao_detectada:
                return self._com_tempo(self._confirmar_memoria(observacao), inicio)
            if self._historico:
                return self._com_tempo(
                    replace(
                        observacao,
                        motivo=(
                            "evidencia_verde_antes_do_t_"
                            f"{self._historico[-1].decisao.value}"
                        ),
                    ),
                    inicio,
                )
            return self._com_tempo(observacao, inicio)

        if self._historico and self._historico[-1].decisao is not observacao.decisao:
            self._historico.clear()
        self._historico.append(observacao)
        self._expirar(observacao.instante_monotonico_s)

        if not intersecao_detectada:
            return self._com_tempo(
                replace(
                    observacao,
                    estado=EstadoVerde.AUSENTE,
                    decisao=DecisaoVerde.NENHUMA,
                    confianca=0.0,
                    motivo=f"evidencia_verde_antes_do_t_{observacao.decisao.value}",
                ),
                inicio,
            )

        return self._com_tempo(self._confirmar_memoria(observacao), inicio)

    def _confirmar_memoria(self, observacao: EstimativaVerde) -> EstimativaVerde:
        if not self._historico:
            return observacao
        ultima = self._historico[-1]
        if len(self._historico) < self._configuracao.confirmacoes_minimas:
            return replace(
                observacao,
                estado=EstadoVerde.AMBIGUA,
                decisao=DecisaoVerde.NENHUMA,
                confianca=0.0,
                motivo="intersecao_sem_confirmacao_temporal_verde",
            )

        confianca = min(item.confianca for item in self._historico)
        return replace(
            ultima,
            id_quadro=observacao.id_quadro,
            instante_monotonico_s=observacao.instante_monotonico_s,
            estado=EstadoVerde.CONFIRMADA,
            confianca=confianca,
            fonte=FonteEstimativa.TEMPORAL,
            motivo="confirmada_temporalmente_na_intersecao",
        )

    def _expirar(self, instante_s: float) -> None:
        limite_s = self._configuracao.memoria_maxima_ms / 1_000.0
        while self._historico and instante_s - self._historico[0].instante_monotonico_s > limite_s:
            self._historico.popleft()

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
