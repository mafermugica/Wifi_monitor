/**
 * app.js  —  Lógica del Dashboard Wifi Monitor
 *
 * - Consulta la API REST cada 30 segundos
 * - Actualiza tarjetas de estado, gráfica Chart.js y tabla de dispositivos
 * - Detecta intrusos por el nombre "INTRUSO" y los resalta en rojo
 */

// ──────────────────────────────────────────────
//  Configuración
// ──────────────────────────────────────────────

const API_BASE = 'http://localhost:3000/api';
const INTERVALO_MS = 30_000;

let chartInstance = null;

// ──────────────────────────────────────────────
//  Helpers
// ──────────────────────────────────────────────

async function fetchJSON(endpoint) {
  const res = await fetch(`${API_BASE}/${endpoint}`);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} — ${res.statusText}`);
  }
  return res.json();
}

function extraerValor(selector) {
  const el = document.querySelector(selector);
  return el ? el.textContent.trim() : '';
}

// ──────────────────────────────────────────────
//  1. Tarjetas de estado
// ──────────────────────────────────────────────

async function actualizarTarjetas() {
  const [disp, vel] = await Promise.all([
    fetchJSON('dispositivos'),
    fetchJSON('velocidad/historial'),
  ]);

  /* ── Card 1: Dispositivos activos ── */
  document.getElementById('card-dispositivos').textContent =
    disp?.total ?? '—';

  /* ── Card 2: Estado de la red ── */
  const estadoEl = document.getElementById('card-estado');
  const ultimo = vel?.historial?.[0];

  if (!ultimo) {
    estadoEl.textContent = 'Sin datos';
    estadoEl.className = 'tarjeta-valor';
  } else if (ultimo.desviacion_detectada) {
    estadoEl.textContent = '🐢 Lenta';
    estadoEl.className = 'tarjeta-valor status-lenta';
  } else {
    estadoEl.textContent = '✅ OK';
    estadoEl.className = 'tarjeta-valor status-ok';
  }

  /* ── Card 3: Último test ── */
  const testEl = document.getElementById('card-ultimo-test');
  if (!ultimo) {
    testEl.innerHTML = `<span class="placeholder">Sin pruebas aún</span>`;
    return;
  }

  testEl.innerHTML = `
    <span class="metric">⬇ ${ultimo.bajada_mbps} Mbps</span>
    <span class="metric">⬆ ${ultimo.subida_mbps} Mbps</span>
    <span class="metric">📶 ${ultimo.ping_ms} ms</span>
  `;
}

// ──────────────────────────────────────────────
//  2. Gráfica de barras (Chart.js)
// ──────────────────────────────────────────────

async function actualizarGrafica() {
  const data = await fetchJSON('consumo/actual');

  const ctx = document.getElementById('consumoChart').getContext('2d');
  const filas = data?.consumo ?? [];

  const labels = filas.map(d => d.nombre || d.mac);
  const valores = filas.map(d => d.total_megas ?? 0);

  if (chartInstance) {
    chartInstance.destroy();
  }

  if (filas.length === 0) {
    // Mostrar un gráfico vacío en lugar de romper
    chartInstance = new Chart(ctx, {
      type: 'bar',
      data: { labels: ['Sin datos'], datasets: [{ label: 'MB', data: [0] }] },
      options: { responsive: true, plugins: { legend: { display: false } } },
    });
    return;
  }

  chartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Bajada (MB)',
          data: valores,
          backgroundColor: 'rgba(0, 255, 65, 0.75)',
          borderColor: 'rgba(0, 204, 51, 0.9)',
          borderWidth: 1,
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: {
          labels: { color: '#c8d6e5', font: { family: 'Courier New' } },
        },
        tooltip: {
          backgroundColor: '#111827',
          titleColor: '#00ff41',
          bodyColor: '#c8d6e5',
          borderColor: '#1e293b',
          borderWidth: 1,
        },
      },
      scales: {
        x: {
          ticks: { color: '#64748b', maxRotation: 45, font: { size: 10 } },
          grid: { color: 'rgba(30, 41, 59, 0.5)' },
        },
        y: {
          beginAtZero: true,
          ticks: { color: '#64748b', font: { size: 10 } },
          grid: { color: 'rgba(30, 41, 59, 0.5)' },
        },
      },
    },
  });
}

// ──────────────────────────────────────────────
//  3. Tabla de dispositivos
// ──────────────────────────────────────────────

async function actualizarTabla() {
  const data = await fetchJSON('dispositivos');
  const tbody = document.querySelector('#tabla-dispositivos tbody');
  const dispositivos = data?.dispositivos ?? [];

  if (dispositivos.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" class="tabla-vacia">Sin dispositivos registrados</td></tr>`;
    return;
  }

  tbody.innerHTML = '';

  for (const d of dispositivos) {
    const tr = document.createElement('tr');
    const esIntruso = /intruso/i.test(d.nombre_personalizado);

    if (esIntruso) {
      tr.className = 'fila-intruso';
    }

    tr.innerHTML = `
      <td>${d.mac}</td>
      <td>${d.ip_actual || '—'}</td>
      <td>${esIntruso ? '🚨 ' : ''}${d.nombre_personalizado}</td>
      <td>${d.fecha_registro || '—'}</td>
    `;

    tbody.appendChild(tr);
  }
}

// ──────────────────────────────────────────────
//  Orquestador: actualiza todo
// ──────────────────────────────────────────────

async function actualizarTodo() {
  try {
    await Promise.all([
      actualizarTarjetas(),
      actualizarGrafica(),
      actualizarTabla(),
    ]);

    const ahora = new Date().toLocaleTimeString('es-MX', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
    document.getElementById('ultima-actualizacion').textContent =
      `Última actualización: ${ahora}`;
  } catch (err) {
    console.error('[Wifi Monitor] Error en actualización:', err);
  }
}

// ──────────────────────────────────────────────
//  Arranque
// ──────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  actualizarTodo();
  setInterval(actualizarTodo, INTERVALO_MS);
});
