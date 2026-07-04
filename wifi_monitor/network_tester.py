"""
network_tester.py — Prueba automatizada de velocidad de internet.

Mide descarga, subida y ping usando speedtest-cli, compara
contra la velocidad contratada y alerta si hay desviación
de línea (posible fallo del proveedor).
"""

import time
from datetime import datetime
from typing import Any, Dict

import speedtest

# ──────────────────────────────────────────────
#  Constantes globales
# ──────────────────────────────────────────────

VELOCIDAD_CONTRATADA: int = 100     # Mbps contratados con el ISP
UMBRAL_DESVIACION: float = 0.6      # 60% — por debajo se considera desviación
INTENTOS: int = 3                   # reintentos ante fallos de conexión
ESPERA_REINTENTO: int = 5           # segundos entre reintentos


# ──────────────────────────────────────────────
#  Función principal: verificar_desviacion
# ──────────────────────────────────────────────

def verificar_desviacion() -> Dict[str, Any]:
    """
    Ejecuta una prueba de velocidad completa y verifica si hay
    desviación respecto a la velocidad contratada.

    La función:
      1. Mide descarga, subida y ping con speedtest-cli.
      2. Compara la descarga contra el 60 % de VELOCIDAD_CONTRATADA.
      3. Si está por debajo, imprime una alerta crítica en consola.
      4. Retorna un diccionario con los resultados para su posterior
         almacenamiento o visualización.

    Retorna:
        Diccionario con las siguientes llaves:
          - bajada (float):         Velocidad de descarga en Mbps.
          - subida (float):         Velocidad de subida en Mbps.
          - ping (float):           Latencia en milisegundos.
          - desviacion_detectada (bool): True si hay desviación de línea.
          - timestamp (str):        Momento de la prueba (ISO 8601).
          - exitoso (bool):         False si la prueba no pudo completarse.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    desviacion_detectada: bool = False

    # ── Ejecutar test con reintentos ──
    for intento in range(1, INTENTOS + 1):
        try:
            print(f"[i] Ejecutando prueba de velocidad "
                  f"(intento {intento}/{INTENTOS})...")

            st = speedtest.Speedtest()
            st.get_best_server()
            servidor = st.results.server.get("host", "desconocido")
            print(f"[i] Servidor: {servidor}")

            st.download()
            st.upload()

            bajada = round(st.results.download / 1_000_000, 2)
            subida = round(st.results.upload / 1_000_000, 2)
            ping = round(st.results.ping, 1)

            print(f"[✓] Descarga: {bajada} Mbps  |  "
                  f"Subida: {subida} Mbps  |  Ping: {ping} ms")

            # ── Verificar desviación ──
            limite_inferior = VELOCIDAD_CONTRATADA * UMBRAL_DESVIACION

            if bajada < limite_inferior:
                desviacion_detectada = True
                print("\n" + "!" * 60)
                print("  🚨 ALERTA: Desviación de velocidad detectada "
                      "- Posible fallo del proveedor")
                print("!" * 60)
                print(f"  Contratado: {VELOCIDAD_CONTRATADA} Mbps")
                print(f"  Detectado:  {bajada} Mbps")
                print(f"  Mínimo esperado: {limite_inferior:.0f} Mbps "
                      f"({UMBRAL_DESVIACION * 100:.0f}% de lo contratado)")
                print("!" * 60 + "\n")
            else:
                print(f"[✓] Velocidad dentro del rango aceptable "
                      f"(mínimo esperado: {limite_inferior:.0f} Mbps).\n")

            return {
                "bajada": bajada,
                "subida": subida,
                "ping": ping,
                "desviacion_detectada": desviacion_detectada,
                "timestamp": timestamp,
                "exitoso": True,
            }

        except speedtest.SpeedtestException as e:
            print(f"[!] Error en la prueba de velocidad: {e}")
            if intento < INTENTOS:
                print(f"[i] Reintentando en {ESPERA_REINTENTO} segundos...")
                time.sleep(ESPERA_REINTENTO)

        except (OSError, ConnectionError) as e:
            print(f"[!] Error de red — posible corte de internet: {e}")
            if intento < INTENTOS:
                print(f"[i] Reintentando en {ESPERA_REINTENTO} segundos...")
                time.sleep(ESPERA_REINTENTO)

    # ── Todos los intentos fallaron ──
    print("\n[✗] No se pudo completar la prueba de velocidad "
          f"tras {INTENTOS} intentos.")

    return {
        "bajada": 0.0,
        "subida": 0.0,
        "ping": 0.0,
        "desviacion_detectada": True,
        "timestamp": timestamp,
        "exitoso": False,
    }


# ──────────────────────────────────────────────
#  Punto de entrada directo
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("═" * 55)
    print("  PRUEBA DE VELOCIDAD — Wifi Monitor")
    print("═" * 55)
    resultado = verificar_desviacion()
    print("\nResumen:")
    for k, v in resultado.items():
        print(f"  {k}: {v}")
