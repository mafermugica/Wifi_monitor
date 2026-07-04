"""
main.py — Orquestador principal del monitor Wi-Fi.

Ejecuta tareas automatizadas en segundo plano:
  - Cada 5 minutos: escanea la red, registra consumo por dispositivo
                    y alerta si detecta intrusos.
  - Cada 1 hora:    prueba de velocidad contra el ISP y guarda
                    el resultado en el historial.

Requiere: pip install schedule
"""

import logging
import signal
import sys
import time
from datetime import datetime

import schedule

from wifi_monitor.database import (
    cerrar_db,
    guardar_muestra_consumo,
    guardar_prueba_velocidad,
    inicializar_db,
)
from wifi_monitor.intrusion_detector import (
    MODO_APRENDIZAJE,
    detectar_intrusos,
    escanear_red_arp,
    mostrar_alerta,
    obtener_lista_blanca,
)
from wifi_monitor.models import RepositorioDispositivos
from wifi_monitor.network_monitor import medir_velocidad
from wifi_monitor.network_tester import verificar_desviacion

# ──────────────────────────────────────────────
#  Configuración de logging
# ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("wifi_monitor")

# ──────────────────────────────────────────────
#  Estado global
# ──────────────────────────────────────────────

_ejecutando = True
conn = None
repo = RepositorioDispositivos()


# ──────────────────────────────────────────────
#  Manejo de señal de salida (Ctrl+C)
# ──────────────────────────────────────────────

def _detener(sig, frame):
    global _ejecutando
    log.info("Señal de detención recibida. Finalizando...")
    _ejecutando = False


# ──────────────────────────────────────────────
#  Tarea 1: Escaneo de red (cada 5 minutos)
# ──────────────────────────────────────────────

def tarea_escaneo_red() -> None:
    """
    Escanea la red local vía ARP, registra consumo actual
    para cada dispositivo detectado y verifica intrusos.
    """
    log.info("Iniciando escaneo de red...")

    try:
        macs_activas = escanear_red_arp()
    except Exception as e:
        log.error("Error al escanear la red: %s", e)
        return

    if not macs_activas:
        log.warning("No se detectaron dispositivos en la red.")
        return

    log.info("Dispositivos detectados: %d", len(macs_activas))

    # ── Medir tráfico actual ──
    try:
        _, _, mb_subidos, mb_bajados = medir_velocidad(intervalo=3)
    except Exception as e:
        log.error("Error al medir tráfico de red: %s", e)
        mb_bajados = 0.0
        mb_subidos = 0.0

    # Si hay varios dispositivos, distribuir el tráfico equitativamente
    mb_bajada_por_disp = round(mb_bajados / len(macs_activas), 4)
    mb_subida_por_disp = round(mb_subidos / len(macs_activas), 4)

    for mac in macs_activas:
        try:
            guardar_muestra_consumo(conn, mac=mac, mb_bajada=mb_bajada_por_disp, mb_subida=mb_subida_por_disp)
        except Exception as e:
            log.error("Error al guardar consumo para %s: %s", mac, e)

    # ── Detección de intrusos ──
    try:
        lista_blanca = obtener_lista_blanca()
        intrusos = detectar_intrusos(macs_activas, lista_blanca, repo)
        mostrar_alerta(intrusos)
        if intrusos:
            log.warning("Intrusos detectados: %s", ", ".join(intrusos))
    except Exception as e:
        log.error("Error en detección de intrusos: %s", e)

    modo = "APRENDIZAJE" if MODO_APRENDIZAJE else "PRODUCCIÓN"
    log.info(
        "Escaneo completado — %d dispositivos, %.2f MB bajada, %.2f MB subida | Modo: %s",
        len(macs_activas),
        mb_bajados,
        mb_subidos,
        modo,
    )


# ──────────────────────────────────────────────
#  Tarea 2: Prueba de velocidad (cada 1 hora)
# ──────────────────────────────────────────────

def tarea_prueba_velocidad() -> None:
    """
    Ejecuta speedtest, verifica desviación contra lo contratado
    y guarda el resultado en HistorialVelocidad.
    """
    log.info("Iniciando prueba de velocidad...")

    try:
        resultado = verificar_desviacion()
    except Exception as e:
        log.error("Error en prueba de velocidad: %s", e)
        return

    if not resultado.get("exitoso", False):
        log.warning("Prueba de velocidad fallida — se omite el guardado.")
        return

    try:
        guardar_prueba_velocidad(
            conn,
            bajada_mbps=resultado["bajada"],
            subida_mbps=resultado["subida"],
            ping_ms=resultado["ping"],
            desviacion_detectada=resultado["desviacion_detectada"],
        )
    except Exception as e:
        log.error("Error al guardar prueba de velocidad: %s", e)
        return

    if resultado["desviacion_detectada"]:
        log.warning(
            "DESVIACIÓN — Bajada: %.2f Mbps (contratado: 100 Mbps, mínimo: 60 Mbps)",
            resultado["bajada"],
        )
    else:
        log.info(
            "Velocidad OK — Bajada: %.2f Mbps | Subida: %.2f Mbps | Ping: %.1f ms",
            resultado["bajada"],
            resultado["subida"],
            resultado["ping"],
        )


# ──────────────────────────────────────────────
#  Inicio del orquestador
# ──────────────────────────────────────────────

def main() -> None:
    """
    Punto de entrada. Inicializa la BD, programa las tareas
    y ejecuta el loop principal.
    """
    global conn

    signal.signal(signal.SIGINT, _detener)
    signal.signal(signal.SIGTERM, _detener)

    # ── Inicializar base de datos ──
    try:
        conn = inicializar_db()
        log.info("Base de datos inicializada correctamente.")
    except Exception as e:
        log.critical("No se pudo inicializar la base de datos: %s", e)
        sys.exit(1)

    # ── Programar tareas ──
    schedule.every(5).minutes.do(tarea_escaneo_red)
    schedule.every(1).hour.do(tarea_prueba_velocidad)

    modo = "APRENDIZAJE" if MODO_APRENDIZAJE else "PRODUCCIÓN"
    log.info("═" * 50)
    log.info("  WIFI MONITOR — INICIADO")
    log.info("  Modo: %s", modo)
    log.info("  Escaneo de red:   cada 5 minutos")
    log.info("  Prueba velocidad: cada 1 hora")
    log.info("  Ctrl+C para detener")
    log.info("═" * 50)

    # Ejecutar primera vez al arrancar
    log.info("Ejecutando tareas iniciales...")
    tarea_escaneo_red()
    tarea_prueba_velocidad()

    # ── Loop principal ──
    while _ejecutando:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            log.error("Error en el loop principal: %s", e)
            time.sleep(5)

    # ── Shutdown ──
    log.info("Deteniendo el monitor...")
    if conn:
        cerrar_db(conn)
    log.info("Monitor detenido correctamente.")
    sys.exit(0)


if __name__ == "__main__":
    main()
