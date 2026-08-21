"""Acesso isolado aos dispositivos fisicos e simulados."""

from obr_oficial.dispositivos.camera_base import (
    EstadoCamera,
    FonteCamera,
    MetricasImagem,
    QuadroCamera,
)
from obr_oficial.dispositivos.camera_simulada import CameraSimulada
from obr_oficial.dispositivos.camera_usb import CameraUSB, ConfiguracaoCameraUSB

__all__ = [
    "CameraSimulada",
    "CameraUSB",
    "ConfiguracaoCameraUSB",
    "EstadoCamera",
    "FonteCamera",
    "MetricasImagem",
    "QuadroCamera",
]
