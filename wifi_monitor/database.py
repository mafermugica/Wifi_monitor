"""
database.py — Capa de persistencia con SQLite.

Tablas:
  - Dispositivos (mac PK, ip_actual, nombre_personalizado, fecha_registro)
  - HistorialConsumo (id PK AUTO, mac_dispositivo FK,
                      megas_bajada, megas_subida, timestamp)

  - HistorialVelocidad (id PK AUTO, bajada_mbps, subida_mbps,
                        ping_ms, desviacion_detectada, timestamp)

Funciones principales:
  - inicializar_db()                          → Crea BD y tablas.
  - registrar_dispositivo(mac, ip, nombre)    → Inserta o actualiza dispositivo.
  - guardar_muestra_consumo(mac, mb_bajada, mb_subida) → Registra consumo.
  - guardar_prueba_velocidad(...)              → Guarda test de velocidad.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ──────────────────────────────────────────────
#  Configuración
# ──────────────────────────────────────────────

DB_PATH: str = str(Path(__file__).resolve().parent.parent / "wifi_monitor.db")
_FORMATO_FECHA: str = "%Y-%m-%d %H:%M:%S"


# ──────────────────────────────────────────────
#  Inicialización
# ──────────────────────────────────────────────

def inicializar_db(ruta: str = DB_PATH) -> sqlite3.Connection:
    """
    Abre (o crea) la base de datos SQLite y genera las tablas si no existen.

    Args:
        ruta: Ruta al archivo .db. Por defecto 'wifi_monitor.db' en la raíz.

    Retorna:
        Conexión SQLite con row_factory = sqlite3.Row y foreign_keys activadas.
    """
    conn = sqlite3.connect(ruta)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS Dispositivos (
            mac                  TEXT PRIMARY KEY,
            ip_actual            TEXT NOT NULL DEFAULT '',
            nombre_personalizado TEXT NOT NULL DEFAULT 'Dispositivo Desconocido',
            fecha_registro       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS HistorialConsumo (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            mac_dispositivo TEXT  NOT NULL,
            megas_bajada    REAL  NOT NULL DEFAULT 0.0,
            megas_subida    REAL  NOT NULL DEFAULT 0.0,
            timestamp       TEXT  NOT NULL,
            FOREIGN KEY (mac_dispositivo) REFERENCES Dispositivos(mac)
        );

        CREATE TABLE IF NOT EXISTS PruebasVelocidad (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            download_mbps       REAL    NOT NULL,
            upload_mbps         REAL    NOT NULL,
            ping_ms             REAL    NOT NULL,
            velocidad_contratada REAL   NOT NULL,
            desviacion          INTEGER NOT NULL DEFAULT 0,
            timestamp           TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS HistorialVelocidad (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            bajada_mbps         REAL    NOT NULL,
            subida_mbps         REAL    NOT NULL,
            ping_ms             REAL    NOT NULL,
            desviacion_detectada INTEGER NOT NULL DEFAULT 0,
            timestamp           TEXT    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_consumo_mac
            ON HistorialConsumo(mac_dispositivo);

        CREATE INDEX IF NOT EXISTS idx_consumo_timestamp
            ON HistorialConsumo(timestamp);

        CREATE INDEX IF NOT EXISTS idx_pruebas_timestamp
            ON PruebasVelocidad(timestamp);

        CREATE INDEX IF NOT EXISTS idx_historial_velocidad_timestamp
            ON HistorialVelocidad(timestamp);
    """)

    conn.commit()
    return conn


# ──────────────────────────────────────────────
#  Dispositivos — CRUD
# ──────────────────────────────────────────────

def registrar_dispositivo(
    conn: sqlite3.Connection,
    mac: str,
    ip: str = "",
    nombre: str = "",
) -> Dict[str, Any]:
    """
    Añade un dispositivo nuevo o actualiza su IP y nombre si ya existe.

    Args:
        conn:   Conexión activa a SQLite.
        mac:    Dirección MAC (se normaliza a mayúsculas, llave primaria).
        ip:     Última dirección IP observada.
        nombre: Nombre personalizado (ej. "Mi Laptop").

    Retorna:
        Diccionario con los datos del dispositivo insertado/actualizado.
    """
    mac = mac.upper()
    ahora = datetime.now().strftime(_FORMATO_FECHA)
    nombre_final = nombre or f"Dispositivo_{mac[-8:]}"

    if nombre:
        # Usuario proporcionó nombre → actualizar ambos campos
        conn.execute(
            """
            INSERT INTO Dispositivos (mac, ip_actual, nombre_personalizado, fecha_registro)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(mac) DO UPDATE SET
                ip_actual            = COALESCE(NULLIF(excluded.ip_actual, ''), ip_actual),
                nombre_personalizado = excluded.nombre_personalizado
            """,
            (mac, ip, nombre_final, ahora),
        )
    else:
        # Solo auto-registro → no sobrescribir nombre existente
        conn.execute(
            """
            INSERT INTO Dispositivos (mac, ip_actual, nombre_personalizado, fecha_registro)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(mac) DO UPDATE SET
                ip_actual = COALESCE(NULLIF(excluded.ip_actual, ''), ip_actual)
            """,
            (mac, ip, nombre_final, ahora),
        )
    conn.commit()

    return dict(
        conn.execute("SELECT * FROM Dispositivos WHERE mac = ?", (mac,)).fetchone()
    )


def obtener_dispositivo(
    conn: sqlite3.Connection, mac: str
) -> Optional[Dict[str, Any]]:
    """Retorna un dispositivo por su MAC, o None si no existe."""
    fila = conn.execute(
        "SELECT * FROM Dispositivos WHERE mac = ?", (mac.upper(),)
    ).fetchone()
    return dict(fila) if fila else None


def listar_dispositivos(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Retorna todos los dispositivos registrados."""
    return [
        dict(f)
        for f in conn.execute(
            "SELECT * FROM Dispositivos ORDER BY fecha_registro"
        ).fetchall()
    ]


# ──────────────────────────────────────────────
#  HistorialConsumo — Registro y consultas
# ──────────────────────────────────────────────

def guardar_muestra_consumo(
    conn: sqlite3.Connection,
    mac: str,
    mb_bajada: float,
    mb_subida: float,
) -> Dict[str, Any]:
    """
    Inserta un registro de consumo de ancho de banda para un dispositivo.

    Si el dispositivo no existe en la tabla Dispositivos, lo crea
    automáticamente como "Dispositivo Desconocido".

    Args:
        conn:      Conexión activa a SQLite.
        mac:       Dirección MAC del dispositivo.
        mb_bajada: Megabytes descargados en el período.
        mb_subida: Megabytes subidos en el período.

    Retorna:
        Diccionario con la fila recién insertada en HistorialConsumo.
    """
    mac = mac.upper()
    ahora = datetime.now().strftime(_FORMATO_FECHA)

    # Asegurar que el dispositivo existe (lo crea si no)
    registrar_dispositivo(conn, mac=mac)

    cursor = conn.execute(
        """
        INSERT INTO HistorialConsumo (mac_dispositivo, megas_bajada, megas_subida, timestamp)
        VALUES (?, ?, ?, ?)
        """,
        (mac, mb_bajada, mb_subida, ahora),
    )
    conn.commit()

    return dict(
        conn.execute(
            "SELECT * FROM HistorialConsumo WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    )


def obtener_historial_por_mac(
    conn: sqlite3.Connection, mac: str, limite: int = 100
) -> List[Dict[str, Any]]:
    """Retorna las últimas N muestras de consumo de un dispositivo."""
    return [
        dict(f)
        for f in conn.execute(
            """
            SELECT * FROM HistorialConsumo
            WHERE mac_dispositivo = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (mac.upper(), limite),
        ).fetchall()
    ]


def obtener_historial_completo(
    conn: sqlite3.Connection, limite: int = 500
) -> List[Dict[str, Any]]:
    """Retorna las últimas N muestras de todos los dispositivos."""
    return [
        dict(f)
        for f in conn.execute(
            """
            SELECT h.*, d.nombre_personalizado, d.ip_actual
            FROM HistorialConsumo h
            JOIN Dispositivos d ON d.mac = h.mac_dispositivo
            ORDER BY h.timestamp DESC
            LIMIT ?
            """,
            (limite,),
        ).fetchall()
    ]


# ──────────────────────────────────────────────
#  PruebasVelocidad — Consultas
# ──────────────────────────────────────────────

def listar_pruebas_velocidad(
    conn: sqlite3.Connection, limite: int = 50
) -> List[Dict[str, Any]]:
    """Retorna las últimas N pruebas de velocidad realizadas."""
    return [
        dict(f)
        for f in conn.execute(
            """
            SELECT * FROM PruebasVelocidad
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limite,),
        ).fetchall()
    ]


def obtener_ultima_prueba(
    conn: sqlite3.Connection,
) -> Optional[Dict[str, Any]]:
    """Retorna la prueba de velocidad más reciente."""
    fila = conn.execute(
        "SELECT * FROM PruebasVelocidad ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()
    return dict(fila) if fila else None


def obtener_promedio_desviaciones(
    conn: sqlite3.Connection, ultimas_n: int = 10
) -> Dict[str, Any]:
    """Calcula estadísticas de las últimas N pruebas de velocidad."""
    fila = conn.execute(
        """
        SELECT
            COUNT(*)                                 AS total_pruebas,
            ROUND(AVG(download_mbps), 2)             AS download_promedio,
            ROUND(AVG(upload_mbps), 2)               AS upload_promedio,
            ROUND(AVG(ping_ms), 1)                   AS ping_promedio,
            SUM(desviacion)                          AS total_desviaciones
        FROM (
            SELECT * FROM PruebasVelocidad
            ORDER BY timestamp DESC
            LIMIT ?
        )
        """,
        (ultimas_n,),
    ).fetchone()
    return dict(fila) if fila else {}


# ──────────────────────────────────────────────
#  Gestión de conexión
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
#  HistorialVelocidad — Registro y consultas
# ──────────────────────────────────────────────

def guardar_prueba_velocidad(
    conn: sqlite3.Connection,
    bajada_mbps: float,
    subida_mbps: float,
    ping_ms: float,
    desviacion_detectada: bool,
) -> Dict[str, Any]:
    """
    Guarda el resultado de una prueba de velocidad en HistorialVelocidad.

    Args:
        conn:               Conexión activa a SQLite.
        bajada_mbps:        Velocidad de descarga en Mbps.
        subida_mbps:        Velocidad de subida en Mbps.
        ping_ms:            Latencia en milisegundos.
        desviacion_detectada: True si hubo desviación de línea.

    Retorna:
        Diccionario con la fila recién insertada.
    """
    timestamp = datetime.now().strftime(_FORMATO_FECHA)

    cursor = conn.execute(
        """
        INSERT INTO HistorialVelocidad
            (bajada_mbps, subida_mbps, ping_ms, desviacion_detectada, timestamp)
        VALUES (?, ?, ?, ?, ?)
        """,
        (bajada_mbps, subida_mbps, ping_ms, int(desviacion_detectada), timestamp),
    )
    conn.commit()

    return dict(
        conn.execute(
            "SELECT * FROM HistorialVelocidad WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    )


def listar_historial_velocidad(
    conn: sqlite3.Connection, limite: int = 50
) -> List[Dict[str, Any]]:
    """Retorna las últimas N pruebas de velocidad registradas."""
    return [
        dict(f)
        for f in conn.execute(
            """
            SELECT * FROM HistorialVelocidad
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limite,),
        ).fetchall()
    ]


def cerrar_db(conn: sqlite3.Connection) -> None:
    """Guarda cambios pendientes y cierra la conexión."""
    conn.commit()
    conn.close()
