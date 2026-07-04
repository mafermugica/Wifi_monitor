"""
network_monitor.py — Medición periódica del tráfico de red local.

Utiliza psutil para leer los contadores acumulativos de red y calcula
la velocidad de subida/bajada en megabytes por segundo (MB/s).
"""

import time
from typing import Tuple

import psutil


def obtener_contadores_acumulados() -> Tuple[int, int]:
    """
    Lee los bytes totales enviados y recibidos desde que el sistema
    está encendido (contadores acumulativos de todas las interfaces).

    Retorna:
        (bytes_enviados, bytes_recibidos) como enteros.
    """
    contadores = psutil.net_io_counters()
    return contadores.bytes_sent, contadores.bytes_recv


def medir_velocidad(intervalo: int = 2) -> Tuple[float, float, float, float]:
    """
    Mide la velocidad de red durante un intervalo dado.

    Para evitar fluctuaciones se toma el promedio en 'intervalo' segundos.

    Args:
        intervalo: segundos entre la muestra inicial y final.

    Retorna:
        (mb_subida, mb_bajada, total_subida, total_bajada)
        donde mb_subida/mb_bajada son tasas en MB/s,
        y total_subida/total_bajada son MB acumulados en el periodo.
    """
    env_1, rec_1 = obtener_contadores_acumulados()
    time.sleep(intervalo)
    env_2, rec_2 = obtener_contadores_acumulados()

    delta_env = env_2 - env_1
    delta_rec = rec_2 - rec_1

    megabytes_subida = delta_env / (1024 * 1024)
    megabytes_bajada = delta_rec / (1024 * 1024)

    tasa_subida = megabytes_subida / intervalo   # MB/s
    tasa_bajada = megabytes_bajada / intervalo   # MB/s

    return tasa_subida, tasa_bajada, megabytes_subida, megabytes_bajada


def obtener_estadisticas_completas(intervalo: int = 2) -> dict:
    """
    Devuelve un diccionario con estadísticas de red actuales.

    Incluye velocidad actual, total acumulado, conexiones activas
    e interfaces de red disponibles.
    """
    tasa_subida, tasa_bajada, mb_subidos, mb_bajados = medir_velocidad(intervalo)

    conexiones = psutil.net_connections()
    interfaces = psutil.net_if_addrs()

    return {
        "tasa_subida_mbps": round(tasa_subida * 8, 2),
        "tasa_bajada_mbps": round(tasa_bajada * 8, 2),
        "mb_subidos_periodo": round(mb_subidos, 3),
        "mb_bajados_periodo": round(mb_bajados, 3),
        "conexiones_activas": len(conexiones),
        "interfaces": list(interfaces.keys()),
    }
