"""
intrusion_detector.py — Detección básica de intrusos en la red local.

Escanea la red usando ARP, descubre las MAC activas y las compara
contra una lista blanca configurable. Si aparece una MAC desconocida
lanza una alerta en consola.
"""

import re
import subprocess
import sys
from typing import List, Set

from wifi_monitor.models import RepositorioDispositivos


# ──────────────────────────────────────────────
#  Lista blanca de dispositivos conocidos
# ──────────────────────────────────────────────

# Formato: mayúsculas, sin guiones ni dos puntos.
# El usuario debe editar este conjunto con sus propias MAC.
LISTA_BLANCA: Set[str] = {
    "AA:BB:CC:DD:EE:FF",  # → Reemplazar con MAC reales
    "00:11:22:33:44:55",
}

# Mensaje de ayuda para el primer uso
_AYUDA_MAC = """
╔══════════════════════════════════════════════════════╗
║  IMPORTANTE: Configura tu lista blanca              ║
║                                                     ║
║  1. Abre intrusion_detector.py                      ║
║  2. Edita el conjunto LISTA_BLANCA con las MAC      ║
║     de tus dispositivos autorizados.                ║
║                                                     ║
║  Formato: "AA:BB:CC:DD:EE:FF" (mayúsculas)         ║
╚══════════════════════════════════════════════════════╝
"""


def _normalizar_mac(mac: str) -> str:
    """
    Limpia y normaliza una dirección MAC:
    - Elimina guiones y espacios
    - Convierte a mayúsculas
    - Inserta dos puntos cada 2 caracteres si hiciera falta
    """
    mac = mac.strip().upper().replace("-", "").replace(":", "").replace(" ", "")
    if len(mac) != 12:
        raise ValueError(f"MAC inválida (longitud incorrecta): {mac}")
    return ":".join(mac[i : i + 2] for i in range(0, 12, 2))


def inicializar_lista_blanca(macs_raw: List[str]) -> Set[str]:
    """
    Convierte una lista de MACs crudas en el conjunto normalizado
    que se usará como lista blanca.

    Args:
        macs_raw: strings con MACs (con o sin formato).

    Retorna:
        Set de MACs normalizadas.
    """
    return {_normalizar_mac(m) for m in macs_raw}


def escanear_red_arp() -> List[str]:
    """
    Escanea la red local ejecutando 'arp -a' y parsea la salida.

    Retorna:
        Lista de direcciones MAC encontradas (formato AA:BB:CC:DD:EE:FF).

    Cross-platform: funciona en Windows, Linux y macOS.
    """
    try:
        resultado = subprocess.run(
            ["arp", "-a"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"[!] Error ejecutando arp -a: {e}")
        return []

    salida = resultado.stdout + resultado.stderr
    macs_encontradas: List[str] = []

    # Patrón para capturar direcciones MAC típicas (con guión o dos puntos)
    patron_mac = re.compile(
        r"(?:[0-9A-Fa-f]{2}[-:]){5}[0-9A-Fa-f]{2}"
    )

    for coincidencia in patron_mac.finditer(salida):
        try:
            mac_normalizada = _normalizar_mac(coincidencia.group(0))
            macs_encontradas.append(mac_normalizada)
        except ValueError:
            continue

    return list(set(macs_encontradas))  # eliminar duplicados


def detectar_intrusos(
    macs_detectadas: List[str],
    lista_blanca: Set[str],
    repo: RepositorioDispositivos,
) -> List[str]:
    """
    Compara las MAC detectadas contra la lista blanca.

    Args:
        macs_detectadas: MACs obtenidas del escaneo de red.
        lista_blanca:    conjunto de MACs autorizadas (normalizadas).
        repo:            repositorio de dispositivos (se actualiza aquí).

    Retorna:
        Lista de MACs desconocidas (posibles intrusos).
    """
    macs_extrañas: List[str] = []

    for mac in macs_detectadas:
        if mac in lista_blanca:
            # Dispositivo conocido → actualizar en el repositorio
            repo.registrar(mac=mac, ip="", nombre="Conocido")
        else:
            # Dispositivo desconocido → posible intruso
            repo.registrar(mac=mac, ip="", nombre="⚠ INTRUSO ⚠")
            macs_extrañas.append(mac)

    return macs_extrañas


def mostrar_alerta(macs_extrañas: List[str]) -> None:
    """Imprime una alerta visible en consola si hay MACs sospechosas."""
    if not macs_extrañas:
        return

    print("\n" + "!" * 60)
    print("  🚨 ALERTA DE SEGURIDAD — INTRUSO DETECTADO 🚨")
    print("!" * 60)
    for mac in macs_extrañas:
        print(f"     → MAC desconocida: {mac}")
    print("!" * 60 + "\n")
