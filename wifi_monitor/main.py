"""
main.py — Punto de entrada del monitor Wi-Fi.

Orquesta la medición periódica de tráfico de red, el escaneo de
dispositivos y la detección de intrusos en un bucle infinito.
"""

import signal
import sys
import time
from datetime import datetime
from typing import NoReturn

from wifi_monitor.models import RepositorioDispositivos, RepositorioHistorial
from wifi_monitor.network_monitor import medir_velocidad
from wifi_monitor.intrusion_detector import (
    LISTA_BLANCA,
    escanear_red_arp,
    detectar_intrusos,
    inicializar_lista_blanca,
    mostrar_alerta,
)

# ──────────────────────────────────────────────
#  Configuración
# ──────────────────────────────────────────────

INTERVALO_MEDICION = 10       # segundos entre cada ciclo
INTERVALO_ESCANEO = 60        # segundos entre escaneos de red
MB_ALERTA_CAIDA = 1.0         # MB/s por debajo de esto se considera caída

REPO_DISPOSITIVOS = RepositorioDispositivos()
REPO_HISTORIAL = RepositorioHistorial()

# Bandera para detener el loop con Ctrl+C
_ejecutando = True


def _manejador_signal(sig: int, frame) -> None:
    """Captura Ctrl+C y permite un shutdown graceful."""
    global _ejecutando
    print("\n[⏹] Deteniendo monitor...")
    _ejecutando = False


def _resumen_monitoreo() -> None:
    """Imprime un resumen de lo registrado hasta ahora."""
    print("\n" + "═" * 55)
    print(f"  📊  RESUMEN — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("═" * 55)
    print(f"  Dispositivos únicos vistos: {len(REPO_DISPOSITIVOS)}")
    print(f"  Mediciones registradas:     {len(REPO_HISTORIAL)}")
    print("═" * 55)
    for disp in REPO_DISPOSITIVOS.listar_todos():
        print(f"  • {disp.nombre:20s}  {disp.ip:15s}  {disp.mac}")
    print("═" * 55 + "\n")


def verificar_caida_velocidad(tasa_bajada: float) -> None:
    """
    Si la velocidad de bajada cae por debajo del umbral configurado,
    muestra una advertencia en consola (posible problema con el ISP).
    """
    if tasa_bajada < MB_ALERTA_CAIDA:
        print(
            f"[⚠] Velocidad baja ({tasa_bajada:.2f} MB/s) — "
            f"Posible caída del proveedor de internet."
        )


def ejecutar() -> NoReturn:
    """
    Bucle principal del monitor Wi-Fi.

    1. Mide velocidad de red y guarda en el historial.
    2. Escanea dispositivos conectados (cada INTERVALO_ESCANEO segundos).
    3. Compara contra lista blanca y alerta si hay intrusos.
    4. Verifica caídas de velocidad.
    """
    signal.signal(signal.SIGINT, _manejador_signal)
    signal.signal(signal.SIGTERM, _manejador_signal)

    lista_blanca = inicializar_lista_blanca(list(LISTA_BLANCA))
    ultimo_escaneo: float = 0.0

    print("╔══════════════════════════════════════════════╗")
    print("║      🛜  MONITOR Wi-Fi  —  v0.1.0           ║")
    print("║  Presiona Ctrl+C para detener               ║")
    print("╚══════════════════════════════════════════════╝")

    while _ejecutando:
        ahora = time.time()

        # ── 1. Medición de red ──
        try:
            tasa_subida, tasa_bajada, mb_subidos, mb_bajados = medir_velocidad(
                intervalo=2
            )
        except Exception as e:
            print(f"[!] Error en medición de red: {e}")
            time.sleep(INTERVALO_MEDICION)
            continue

        # Guardar en el historial
        REPO_HISTORIAL.agregar(
            mac="TODAS_LAS_INTERFACES",
            bajada=round(mb_bajados, 3),
            subida=round(mb_subidos, 3),
        )

        # ── 2. Escaneo periódico de dispositivos ──
        if ahora - ultimo_escaneo >= INTERVALO_ESCANEO:
            macs_activas = escanear_red_arp()
            if macs_activas:
                intrusos = detectar_intrusos(macs_activas, lista_blanca, REPO_DISPOSITIVOS)
                mostrar_alerta(intrusos)
            ultimo_escaneo = ahora

        # ── 3. Verificación de velocidad ──
        verificar_caida_velocidad(tasa_bajada)

        # ── 4. Mostrar estado actual ──
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] "
            f"⬇ {tasa_bajada:.2f} MB/s  ⬆ {tasa_subida:.2f} MB/s  "
            f"| Dispositivos: {len(REPO_DISPOSITIVOS)}"
        )

        time.sleep(INTERVALO_MEDICION)

    # ── Shutdown graceful ──
    _resumen_monitoreo()
    print("[✓] Monitor detenido correctamente.")
    sys.exit(0)


if __name__ == "__main__":
    ejecutar()
