"""Construcao do estado observavel do painel, sem acessos bloqueantes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from shutil import disk_usage
from subprocess import CompletedProcess, TimeoutExpired, run
from threading import Lock
from time import monotonic

from obr_oficial.dispositivos.camera_base import FonteCamera
from obr_oficial.percepcao.linha.execucao_continua import (
    ProcessadorContinuoLinha,
    estimativa_como_dict,
)


def _executar_vcgencmd(argumento: str) -> str | None:
    """Le uma metrica local do Raspberry Pi sem abrir shell nem tocar atuadores."""

    try:
        resultado: CompletedProcess[str] = run(
            ["vcgencmd", argumento],
            check=False,
            capture_output=True,
            text=True,
            timeout=0.25,
        )
    except (FileNotFoundError, OSError, TimeoutExpired):
        return None
    if resultado.returncode != 0:
        return None
    texto = resultado.stdout.strip()
    return texto or None


def _numero_vcgencmd(texto: str | None, inicio: str, fim: str) -> float | None:
    if texto is None or not texto.startswith(inicio) or not texto.endswith(fim):
        return None
    try:
        return round(float(texto.removeprefix(inicio).removesuffix(fim)), 2)
    except ValueError:
        return None


def _temperatura_cpu_c() -> float | None:
    """Le a temperatura exposta pelo Linux do Pi, quando estiver disponivel."""

    try:
        milicelsius = int(Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip())
    except (OSError, ValueError):
        return None
    return round(milicelsius / 1000, 1)


def _memoria_disponivel_mb() -> int | None:
    """Le a memoria disponivel do sistema local sem criar processo adicional."""

    try:
        linhas = Path("/proc/meminfo").read_text().splitlines()
    except OSError:
        return None
    for linha in linhas:
        if linha.startswith("MemAvailable:"):
            try:
                return round(int(linha.split()[1]) / 1024)
            except (IndexError, ValueError):
                return None
    return None


def _estado_raspberry() -> dict[str, object]:
    """Retorna apenas telemetria local que o firmware do Pi consegue confirmar."""

    tensao_nucleo = _numero_vcgencmd(_executar_vcgencmd("measure_volts"), "volt=", "V")
    throttled = _executar_vcgencmd("get_throttled")
    try:
        mascara = int(throttled.removeprefix("throttled="), 16) if throttled else None
    except ValueError:
        mascara = None
    return {
        "tensao_nucleo_v": tensao_nucleo,
        "subtensao_atual": None if mascara is None else bool(mascara & 0x1),
        "subtensao_ocorreu": None if mascara is None else bool(mascara & 0x10000),
        "temperatura_cpu_c": _temperatura_cpu_c(),
        "memoria_disponivel_mb": _memoria_disponivel_mb(),
    }


class EstadoOperacao:
    """Monta instantaneos serializaveis combinando todas as fontes leves."""

    def __init__(
        self,
        fonte_camera: FonteCamera,
        processador: ProcessadorContinuoLinha | None,
        gerenciador_viradas: object,
        *,
        raiz_disco: Path,
        capturador: object | None = None,
    ) -> None:
        self._fonte = fonte_camera
        self._processador = processador
        self._viradas = gerenciador_viradas
        self._capturador = capturador
        self._raiz_disco = raiz_disco
        self._inicio_monotonico_s = monotonic()
        self._lock_ultimo = Lock()
        self._ultimo_id_quadro: int | None = None
        self._raspberry: dict[str, object] = _estado_raspberry()
        self._ultima_leitura_raspberry_s = monotonic()

    def _obter_raspberry(self) -> dict[str, object]:
        """Atualiza a leitura local do Pi no maximo uma vez a cada cinco segundos."""

        agora = monotonic()
        with self._lock_ultimo:
            if agora - self._ultima_leitura_raspberry_s >= 5.0:
                self._raspberry = _estado_raspberry()
                self._ultima_leitura_raspberry_s = agora
            return dict(self._raspberry)

    def construir(self) -> dict[str, object]:
        """Retorna o retrato atual; toda leitura aqui e nao bloqueante."""

        percepcao: dict[str, object] | None = None
        if self._processador is not None:
            resultado = self._processador.obter_ultimo_resultado(timeout_s=0.0)
            if resultado is not None:
                with self._lock_ultimo:
                    self._ultimo_id_quadro = resultado.id_quadro
                percepcao = {
                    "estimativa": estimativa_como_dict(resultado.estimativa),
                    "latencia_total_ms": resultado.estimativa.tempos.total_ms,
                }
        livre_bytes = disk_usage(self._raiz_disco).free
        return {
            "instante_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "modo_percepcao": self._processador is not None,
            "camera": self._fonte.obter_estado().como_dict(),
            "processador": (
                self._processador.obter_estado().como_dict()
                if self._processador is not None
                else None
            ),
            "percepcao": percepcao,
            "viradas": self._viradas.como_dict(),
            "captura": (self._capturador.estado() if self._capturador is not None else None),
            "sistema": {
                "tempo_ativo_s": round(monotonic() - self._inicio_monotonico_s),
                "disco_livre_gb": round(livre_bytes / 1024**3, 1),
                "raspberry": self._obter_raspberry(),
            },
        }
