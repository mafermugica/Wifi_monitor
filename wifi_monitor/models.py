"""
modelos.py — Estructuras de datos para dispositivos e historial de consumo.

Simula las tablas de una base de datos relacional usando dataclasses
para facilitar la serialización y futura migración a SQLite / PostgreSQL.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional


# ──────────────────────────────────────────────
#  Entidad: Dispositivo
# ──────────────────────────────────────────────

@dataclass
class Dispositivo:
    """
    Representa un dispositivo conectado a la red local.

    Atributos:
        mac       — Dirección MAC única del dispositivo.
        ip        — Última dirección IP conocida (puede cambiar con DHCP).
        nombre    — Nombre amigable asignado por el usuario.
        primera_vez — Timestamp del primer avistamiento.
        ultima_vez  — Timestamp del último avistamiento.
    """
    mac: str
    ip: str = ""
    nombre: str = "Desconocido"
    primera_vez: datetime = field(default_factory=datetime.now)
    ultima_vez: datetime = field(default_factory=datetime.now)

    def actualizar_ip(self, nueva_ip: str) -> None:
        """Actualiza la IP y la marca de tiempo del último avistamiento."""
        self.ip = nueva_ip
        self.ultima_vez = datetime.now()

    def a_diccionario(self) -> dict:
        """Convierte la entidad a diccionario (útil para JSON)."""
        return asdict(self)

    def __hash__(self) -> int:
        return hash(self.mac.upper())

    def __eq__(self, otro: object) -> bool:
        if not isinstance(otro, Dispositivo):
            return NotImplemented
        return self.mac.upper() == otro.mac.upper()


# ──────────────────────────────────────────────
#  Entidad: HistorialConsumo
# ──────────────────────────────────────────────

@dataclass
class HistorialConsumo:
    """
    Registro puntual de consumo de ancho de banda para un dispositivo.

    Atributos:
        id_dispositivo — MAC del dispositivo asociado.
        mb_bajada     — Megabytes descargados en el período.
        mb_subida     — Megabytes subidos en el período.
        timestamp     — Momento en que se tomó la medición.
    """
    id_dispositivo: str
    mb_bajada: float = 0.0
    mb_subida: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def a_diccionario(self) -> dict:
        return asdict(self)


# ──────────────────────────────────────────────
#  Repositorio en memoria (simula DB)
# ──────────────────────────────────────────────

class RepositorioDispositivos:
    """Colección en memoria de dispositivos conocidos."""

    def __init__(self) -> None:
        self._dispositivos: dict[str, Dispositivo] = {}

    def registrar(self, mac: str, ip: str, nombre: str = "") -> Dispositivo:
        mac = mac.upper()
        if mac in self._dispositivos:
            dispositivo = self._dispositivos[mac]
            dispositivo.actualizar_ip(ip)
            return dispositivo
        dispositivo = Dispositivo(mac=mac, ip=ip, nombre=nombre or f"Dispositivo_{mac[-8:]}")
        self._dispositivos[mac] = dispositivo
        return dispositivo

    def obtener(self, mac: str) -> Optional[Dispositivo]:
        return self._dispositivos.get(mac.upper())

    def listar_todos(self) -> List[Dispositivo]:
        return list(self._dispositivos.values())

    def eliminar(self, mac: str) -> bool:
        return self._dispositivos.pop(mac.upper(), None) is not None

    def __len__(self) -> int:
        return len(self._dispositivos)


class RepositorioHistorial:
    """Colección en memoria del historial de consumo."""

    def __init__(self) -> None:
        self._registros: List[HistorialConsumo] = []

    def agregar(self, mac: str, bajada: float, subida: float) -> None:
        self._registros.append(
            HistorialConsumo(id_dispositivo=mac.upper(), mb_bajada=bajada, mb_subida=subida)
        )

    def obtener_por_dispositivo(self, mac: str) -> List[HistorialConsumo]:
        mac = mac.upper()
        return [r for r in self._registros if r.id_dispositivo == mac]

    def listar_todos(self) -> List[HistorialConsumo]:
        return list(self._registros)

    def __len__(self) -> int:
        return len(self._registros)
