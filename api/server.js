/**
 * server.js  —  API REST para Wifi_monitor
 *
 * Endpoints:
 *   GET /api/dispositivos        → Lista de dispositivos registrados
 *   GET /api/consumo/actual       → Consumo agregado de la última hora
 *   GET /api/velocidad/historial  → Últimos 10 tests de velocidad
 *
 * La base de datos SQLite se encuentra en la raíz del proyecto
 * (../wifi_monitor.db) y es generada por el script Python.
 * Se usa sql.js (SQLite compilado a WebAssembly) para evitar
 * dependencias nativas de compilación.
 */

const express = require("express");
const cors = require("cors");
const fs = require("fs");
const path = require("path");
const initSqlJs = require("sql.js");

// ──────────────────────────────────────────────
//  Configuración
// ──────────────────────────────────────────────

const PUERTO = process.env.PORT || 3000;
const RUTA_BD = path.resolve(__dirname, "..", "wifi_monitor.db");

const app = express();

// ──────────────────────────────────────────────
//  Middleware
// ──────────────────────────────────────────────

app.use(cors());
app.use(express.json());

// ──────────────────────────────────────────────
//  Conexión a SQLite vía sql.js (puro JS, sin compilación)
// ──────────────────────────────────────────────

let SQL; // instancia de sql.js
let ultimaCarga = 0; // timestamp de la última recarga
let dbBuffer; // buffer con el archivo .db en memoria

async function inicializarSqlJs() {
  SQL = await initSqlJs();
  console.log("[✓] sql.js cargado correctamente.");
}

/**
 * Abre (o recarga) la base de datos desde el archivo en disco.
 * Como sql.js trabaja en memoria, recargamos el archivo en cada
 * llamada para obtener los datos más recientes del script Python.
 *
 * Retorna una instancia de base de datos sql.js.
 * Llamar a .close() cuando se termine de usar.
 */
function abrirBaseDeDatos() {
  if (!fs.existsSync(RUTA_BD)) {
    throw new Error(
      `Archivo no encontrado: ${RUTA_BD}. ` +
        "Ejecuta primero el monitor Python para generarlo.",
    );
  }

  const buffer = fs.readFileSync(RUTA_BD);
  return new SQL.Database(buffer);
}

// ──────────────────────────────────────────────
//  Endpoint 1: GET /api/dispositivos
// ──────────────────────────────────────────────

app.get("/api/dispositivos", (req, res) => {
  let db;
  try {
    db = abrirBaseDeDatos();

    const resultado = db.exec(`
      SELECT mac, ip_actual, nombre_personalizado, fecha_registro
      FROM Dispositivos
      ORDER BY nombre_personalizado ASC
    `);

    const dispositivos = extraerFilas(resultado);

    res.json({
      ok: true,
      total: dispositivos.length,
      dispositivos,
    });
  } catch (err) {
    console.error(`[ERROR] GET /api/dispositivos: ${err.message}`);
    res.status(500).json({
      ok: false,
      error: "Error al consultar dispositivos",
      detalle: err.message,
    });
  } finally {
    if (db) db.close();
  }
});

// ──────────────────────────────────────────────
//  Endpoint 2: GET /api/consumo/actual
// ──────────────────────────────────────────────
//
//  Suma los megas consumidos por cada dispositivo
//  en la última hora, ordenados de mayor a menor.

app.get("/api/consumo/actual", (req, res) => {
  let db;
  try {
    db = abrirBaseDeDatos();

    const resultado = db.exec(`
      SELECT
        h.mac_dispositivo AS mac,
        COALESCE(d.nombre_personalizado, 'Dispositivo Desconocido') AS nombre,
        ROUND(SUM(h.megas_bajada), 2)  AS total_megas_bajada,
        ROUND(SUM(h.megas_subida), 2)  AS total_megas_subida,
        ROUND(SUM(h.megas_bajada + h.megas_subida), 2) AS total_megas
      FROM HistorialConsumo h
      LEFT JOIN Dispositivos d ON d.mac = h.mac_dispositivo
      WHERE h.timestamp >= datetime('now', '-1 hour', 'localtime')
      GROUP BY h.mac_dispositivo
      ORDER BY total_megas_bajada DESC
    `);

    const consumo = extraerFilas(resultado);

    res.json({
      ok: true,
      total: consumo.length,
      consumo,
    });
  } catch (err) {
    console.error(`[ERROR] GET /api/consumo/actual: ${err.message}`);
    res.status(500).json({
      ok: false,
      error: "Error al consultar consumo actual",
      detalle: err.message,
    });
  } finally {
    if (db) db.close();
  }
});

// ──────────────────────────────────────────────
//  Endpoint 3: GET /api/velocidad/historial
// ──────────────────────────────────────────────

app.get("/api/velocidad/historial", (req, res) => {
  let db;
  try {
    db = abrirBaseDeDatos();

    const resultado = db.exec(`
      SELECT
        id,
        bajada_mbps,
        subida_mbps,
        ping_ms,
        desviacion_detectada,
        timestamp
      FROM HistorialVelocidad
      ORDER BY timestamp DESC
      LIMIT 10
    `);

    const filas = extraerFilas(resultado);

    // Convertir desviacion_detectada de 0/1 a booleano
    const historial = filas.map((f) => ({
      ...f,
      desviacion_detectada: f.desviacion_detectada === 1 || f.desviacion_detectada === "1",
    }));

    res.json({
      ok: true,
      total: historial.length,
      historial,
    });
  } catch (err) {
    console.error(`[ERROR] GET /api/velocidad/historial: ${err.message}`);
    res.status(500).json({
      ok: false,
      error: "Error al consultar historial de velocidad",
      detalle: err.message,
    });
  } finally {
    if (db) db.close();
  }
});

// ──────────────────────────────────────────────
//  Helper: convertir resultado de sql.js a objetos
// ──────────────────────────────────────────────

function extraerFilas(resultadoSqlJs) {
  // sql.js devuelve [{columns: [...], values: [[...], ...]}]
  if (!resultadoSqlJs || resultadoSqlJs.length === 0) return [];

  const { columns, values } = resultadoSqlJs[0];

  return values.map((fila) => {
    const obj = {};
    columns.forEach((col, i) => {
      obj[col] = fila[i];
    });
    return obj;
  });
}

// ──────────────────────────────────────────────
//  Inicio del servidor
// ──────────────────────────────────────────────

async function main() {
  await inicializarSqlJs();

  // Verificar que la BD existe al arrancar
  if (!fs.existsSync(RUTA_BD)) {
    console.warn(
      `[!] Advertencia: No se encontró ${RUTA_BD}. ` +
        "La API funcionará cuando el monitor Python genere la base de datos.",
    );
  }

  app.listen(PUERTO, () => {
    console.log("═".repeat(50));
    console.log("  🛜  WIFI MONITOR — API REST");
    console.log(`  Puerto:      ${PUERTO}`);
    console.log(`  Base de datos: ${RUTA_BD}`);
    console.log("═".repeat(50));
    console.log("  Endpoints:");
    console.log("  GET /api/dispositivos");
    console.log("  GET /api/consumo/actual");
    console.log("  GET /api/velocidad/historial");
    console.log("═".repeat(50));
  });
}

main().catch((err) => {
  console.error(`[FATAL] Error al iniciar: ${err.message}`);
  process.exit(1);
});
