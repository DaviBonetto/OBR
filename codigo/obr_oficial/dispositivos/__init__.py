"""Acesso isolado aos dispositivos fisicos e simulados."""

from obr_oficial.dispositivos.camera_base import (
    EstadoCamera,
    FonteCamera,
    MetricasImagem,
    QuadroCamera,
)
from obr_oficial.dispositivos.camera_reproducao import (
    CameraReproducaoImagens,
    ErroReproducaoCapturas,
    carregar_imagens_dataset,
)
from obr_oficial.dispositivos.camera_simulada import CameraSimulada
from obr_oficial.dispositivos.camera_usb import CameraUSB, ConfiguracaoCameraUSB

__all__ = [
    "CameraReproducaoImagens",
    "CameraSimulada",
    "CameraUSB",
    "ConfiguracaoCameraUSB",
    "ErroReproducaoCapturas",
    "EstadoCamera",
    "FonteCamera",
    "MetricasImagem",
    "QuadroCamera",
    "carregar_imagens_dataset",
]
