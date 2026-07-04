"""
intrusion_detector.py — Detección de intrusos con modo aprendizaje.

Modo Aprendizaje (True):
  Escanea la red y guarda todas las MAC detectadas en
  'dispositivos_conocidos.json' para construir la lista blanca.

Modo Producción (False):
  Carga las MAC desde el JSON y las usa como lista blanca.
  Cualquier MAC no listada genera una alerta de intruso.
"""

import json
import os
import re
import subprocess
import sys
from typing import List, Set

from wifi_monitor.models import RepositorioDispositivos


# ──────────────────────────────────────────────
#  Configuración del modo aprendizaje
# ──────────────────────────────────────────────

MODO_APRENDIZAJE: bool = True
RUTA_JSON: str = "dispositivos_conocidos.json"


# ──────────────────────────────────────────────
#  Normalización de MAC
# ──────────────────────────────────────────────

def _normalizar_mac(mac: str) -> str:
    """
    Limpia y normaliza una dirección MAC:
    - Elimina guiones, espacios y dos puntos
    - Convierte a mayúsculas
    - Inserta dos puntos cada 2 caracteres
    """
    mac = mac.strip().upper().replace("-", "").replace(":", "").replace(" ", "")
    if len(mac) != 12:
        raise ValueError(f"MAC inválida (longitud incorrecta): {mac}")
    return ":".join(mac[i : i + 2] for i in range(0, 12, 2))


# ──────────────────────────────────────────────
#  Persistencia de la lista blanca (JSON)
# ──────────────────────────────────────────────

def _cargar_lista_blanca() -> Set[str]:
    """
    Carga las MAC conocidas desde el archivo JSON.

    Retorna:
        Set de MACs normalizadas. Vacío si el archivo no existe o está dañado.
    """
    if not os.path.exists(RUTA_JSON):
        print(f"[!] Archivo '{RUTA_JSON}' no encontrado. Lista blanca vacía.")
        return set()

    try:
        with open(RUTA_JSON, "r", encoding="utf-8") as f:
            datos = json.load(f)
        return set(datos.get("dispositivos", []))
    except (json.JSONDecodeError, KeyError, OSError) as e:
        print(f"[!] Error al leer '{RUTA_JSON}': {e}")
        return set()


def _guardar_lista_blanca(macs: Set[str]) -> None:
    """
    Guarda un conjunto de MACs en el archivo JSON.

    Args:
        macs: MACs normalizadas a persistir.
    """
    datos = {"dispositivos": sorted(macs)}
    with open(RUTA_JSON, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
    print(f"[✓] Lista blanca guardada: {len(macs)} dispositivos → {RUTA_JSON}")


def aprender_macs(macs_detectadas: List[str]) -> None:
    """
    Incorpora las MACs detectadas a la lista blanca persistida.

    Es aditivo: carga las MACs existentes, agrega las nuevas
    y vuelve a guardar. Así no se pierden dispositivos que
    estén apagados durante un escaneo.

    Args:
        macs_detectadas: MACs obtenidas del escaneo de red.
    """
    existentes = _cargar_lista_blanca()
    nuevas = set(macs_detectadas)
    combinadas = existentes | nuevas
    if combinadas != existentes:
        _guardar_lista_blanca(combinadas)
    else:
        print(f"[i] No se detectaron MACs nuevas (total: {len(combinadas)}).")


def obtener_lista_blanca() -> Set[str]:
    """
    Obtiene la lista blanca según el modo de operación.

    En modo aprendizaje devuelve un conjunto vacío
    (todo se acepta sin alertar).

    En modo producción carga y devuelve las MACs del JSON.
    """
    if MODO_APRENDIZAJE:
        return set()
    return _cargar_lista_blanca()


# ──────────────────────────────────────────────
#  Escaneo de red vía ARP
# ──────────────────────────────────────────────

def escanear_red_arp() -> List[str]:
    """
    Escanea la red local ejecutando 'arp -a' y parsea la salida.

    Retorna:
        Lista de direcciones MAC encontradas (formato AA:BB:CC:DD:EE:FF).

    Cross-platform: funciona en Windows, Linux y macOS.
    """
    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        resultado = subprocess.run(
            ["arp", "-a"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=flags,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"[!] Error ejecutando arp -a: {e}")
        return []

    salida = resultado.stdout + resultado.stderr
    macs_encontradas: List[str] = []

    patron_mac = re.compile(r"(?:[0-9A-Fa-f]{2}[-:]){5}[0-9A-Fa-f]{2}")

    for coincidencia in patron_mac.finditer(salida):
        try:
            mac_normalizada = _normalizar_mac(coincidencia.group(0))
            macs_encontradas.append(mac_normalizada)
        except ValueError:
            continue

    return list(set(macs_encontradas))


# ──────────────────────────────────────────────
#  Detección de intrusos
# ──────────────────────────────────────────────

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
            repo.registrar(mac=mac, ip="", nombre="Conocido")
        else:
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
