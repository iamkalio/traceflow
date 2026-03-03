/**
 * API, polling, tracing list/detail, monitoring charts.
 */

const API = window.API_BASE ?? '';
const POLL_INTERVAL_MS = 3000;
const CHART_COLORS = ['#7c9eff', '#5dd68a', '#fbbf24', '#f472b6'];

let sinceHours = 0;
let pollTimer = null;
let chartInstances = [];
let selectedTraceId = null;
let tracePage = 1;
let tracePageSize = 50;
let traceTotal = 0;
let filterName = '';
let filterStatus = '';
let filterModel = '';
let filterErrorOnly = false;

function closeTraceDetail() {
  selectedTraceId = null;
  const overlay = document.getElementById('trace-detail-overlay');
  const content = document.getElementById('detail-content');
  const list = document.getElementById('list');
  if (overlay) {
    overlay.classList.remove('is-open');
    overlay.setAttribute('aria-hidden', 'true');
  }
  if (content) content.innerHTML = '';
  if (list) {
    const rows = list.querySelectorAll('.table-wrap tbody tr.selected');
    rows.forEach((r) => r.classList.remove('selected'));
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(() => {
    if (document.getElementById('tracing').classList.contains('active')) loadTraces(true);
    else loadMonitoring();
  }, POLL_INTERVAL_MS);
}

function escapeHtml(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function tracesQueryParams() {
  const nameEl = document.getElementById('filter-name');
  const statusEl = document.getElementById('filter-status');
  const modelEl = document.getElementById('filter-model');
  const errorOnlyEl = document.getElementById('filter-error-only');
  const name = nameEl ? nameEl.value.trim() : filterName;
  const status = statusEl ? statusEl.value : filterStatus;
  const model = modelEl ? modelEl.value.trim() : filterModel;
  const errorOnly = errorOnlyEl ? errorOnlyEl.checked : filterErrorOnly;
  const params = new URLSearchParams();
  params.set('limit', String(tracePageSize));
  params.set('offset', String((tracePage - 1) * tracePageSize));
  if (sinceHours != null && sinceHours !== '' && Number(sinceHours) > 0) params.set('since_hours', String(sinceHours));
  if (name) params.set('name', name);
  if (status) params.set('status', status);
  if (model) params.set('model', model);
  if (errorOnly) params.set('error_only', 'true');
  return params.toString();
}

function bindTabsAndRange() {
  document.getElementById('since').addEventListener('change', (e) => {
    const v = e.target.value;
    sinceHours = v === '' ? 0 : parseInt(v, 10);
    if (document.getElementById('tracing').classList.contains('active')) { tracePage = 1; loadTraces(false); }
    else loadMonitoring();
  });
  const nameEl = document.getElementById('filter-name');
  const statusEl = document.getElementById('filter-status');
  const modelEl = document.getElementById('filter-model');
  const errorOnlyEl = document.getElementById('filter-error-only');
  const pageSizeEl = document.getElementById('page-size');
  if (nameEl) nameEl.addEventListener('input', () => { filterName = nameEl.value; tracePage = 1; loadTraces(false); });
  if (statusEl) statusEl.addEventListener('change', () => { filterStatus = statusEl.value; tracePage = 1; loadTraces(false); });
  if (modelEl) modelEl.addEventListener('input', () => { filterModel = modelEl.value; tracePage = 1; loadTraces(false); });
  if (errorOnlyEl) errorOnlyEl.addEventListener('change', () => { filterErrorOnly = errorOnlyEl.checked; tracePage = 1; loadTraces(false); });
  if (pageSizeEl) pageSizeEl.addEventListener('change', () => { tracePageSize = parseInt(pageSizeEl.value, 10); tracePage = 1; loadTraces(false); });

  document.querySelectorAll('.tabs button').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tabs button').forEach((b) => b.classList.remove('active'));
      document.querySelectorAll('#tracing, #monitoring').forEach((el) => el.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(btn.dataset.tab).classList.add('active');
      if (btn.dataset.tab === 'monitoring') loadMonitoring();
      else loadTraces(false);
      startPolling();
    });
  });
}

const TRACE_COLUMNS = [
  { key: 'status', label: 'Status', width: 90 },
  { key: 'kind', label: 'Kind', width: 70 },
  { key: 'name', label: 'Name', width: 180 },
  { key: 'model', label: 'Model', width: 120 },
  { key: 'input', label: 'Input', width: 140 },
  { key: 'output', label: 'Output', width: 140 },
  { key: 'error', label: 'Error', width: 100 },
  { key: 'start_time', label: 'Start Time', width: 160 },
  { key: 'latency', label: 'Latency', width: 100 },
  { key: 'tokens', label: 'Tokens', width: 80 },
  { key: 'cost', label: 'Cost', width: 80 },
  { key: 'first_token', label: 'First Token', width: 90 },
  { key: 'tags', label: 'Tags', width: 100 },
  { key: 'metadata', label: 'Metadata', width: 120 },
];

function truncate(str, max = 40) {
  if (str == null || str === '') return '—';
  const s = String(str);
  return s.length > max ? s.slice(0, max) + '…' : s;
}

function renderTraceRow(t) {
  const status = t.status || 'success';
  const statusIcon = status === 'success' ? '✓' : '!';
  const name = truncate(t.name || '—', 50);
  const model = t.model || '—';
  const startTime = t.created_at ? new Date(t.created_at).toLocaleString() : '—';
  const latencyMs = t.latency_ms != null ? t.latency_ms : null;
  const latencyStr = latencyMs != null ? (latencyMs >= 1000 ? (latencyMs / 1000).toFixed(2) + 's' : latencyMs + ' ms') : '—';
  const costStr = t.cost_usd != null ? '$' + t.cost_usd.toFixed(4) : '—';
  const tags = (t.attributes && typeof t.attributes === 'object') ? Object.keys(t.attributes).slice(0, 2).join(', ') || '—' : '—';
  const metadata = (t.attributes && typeof t.attributes === 'object') ? Object.entries(t.attributes).map(([k, v]) => k + '=' + v).slice(0, 1).join(' ') || '—' : '—';
  const kind = (t.kind || 'llm').toLowerCase();
  return `
    <tr data-id="${t.trace_id}">
      <td><span class="status ${status}">${statusIcon} ${status}</span></td>
      <td><span class="kind-badge kind-${kind}">${escapeHtml(kind)}</span></td>
      <td><span class="cell-content" title="${escapeHtml(t.name || '')}">${escapeHtml(name)}</span></td>
      <td><span class="cell-content">${escapeHtml(model)}</span></td>
      <td><span class="cell-content" title="${escapeHtml(t.prompt || '')}">${escapeHtml(truncate(t.prompt, 30))}</span></td>
      <td><span class="cell-content" title="${escapeHtml(t.completion || '')}">${escapeHtml(truncate(t.completion, 30))}</span></td>
      <td><span class="cell-content">${escapeHtml(truncate(t.error, 20))}</span></td>
      <td><span class="cell-content">${escapeHtml(startTime)}</span></td>
      <td>${latencyMs != null ? `<span class="latency-pill">⏱ ${latencyStr}</span>` : '—'}</td>
      <td>${t.total_tokens ?? '—'}</td>
      <td>${costStr}</td>
      <td>—</td>
      <td><span class="cell-content">${escapeHtml(truncate(tags, 15))}</span></td>
      <td><span class="meta-pill cell-content" title="${escapeHtml(metadata)}">${escapeHtml(truncate(metadata, 18))}</span></td>
    </tr>
  `;
}

function buildTableHtml(traces) {
  const colgroup = TRACE_COLUMNS.map((c, i) => `<col data-col="${i}" style="width: ${c.width}px">`).join('');
  const headerCells = TRACE_COLUMNS.map((c, i) =>
    `<th data-col="${i}" style="width: ${c.width}px"><span class="th-inner">${c.label}</span><span class="resize-handle" aria-label="Resize column"></span></th>`
  ).join('');
  const bodyRows = traces.map(renderTraceRow).join('');
  return `
    <div class="table-wrap">
      <table>
        <colgroup>${colgroup}</colgroup>
        <thead><tr>${headerCells}</tr></thead>
        <tbody>${bodyRows}</tbody>
      </table>
    </div>
  `;
}

function bindResizeHandles(listEl) {
  const wrap = listEl.querySelector('.table-wrap');
  if (!wrap) return;
  const cols = wrap.querySelectorAll('colgroup col');
  const headers = wrap.querySelectorAll('thead th');
  let activeCol = null;
  let startX = 0;
  let startW = 0;

  function onMove(e) {
    if (activeCol == null) return;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    const dx = e.pageX - startX;
    const newW = Math.max(40, startW + dx);
    cols[activeCol].style.width = newW + 'px';
    headers[activeCol].style.width = newW + 'px';
  }
  function onUp() {
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    activeCol = null;
  }

  headers.forEach((th, i) => {
    const handle = th.querySelector('.resize-handle');
    if (!handle) return;
    handle.addEventListener('mousedown', (e) => {
      e.preventDefault();
      activeCol = i;
      startX = e.pageX;
      startW = parseInt(cols[i].style.width, 10) || TRACE_COLUMNS[i].width;
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  });
}

function renderPagination(total, page, pageSize) {
  const paginationEl = document.getElementById('pagination');
  if (!paginationEl) return;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (total === 0) {
    paginationEl.innerHTML = '';
    return;
  }
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  paginationEl.innerHTML = `
    <span class="pagination-info">${start}–${end} of ${total}</span>
    <button type="button" class="pagination-btn" data-page="prev" ${page <= 1 ? 'disabled' : ''}>Previous</button>
    <span class="pagination-page">Page ${page} of ${totalPages}</span>
    <button type="button" class="pagination-btn" data-page="next" ${page >= totalPages ? 'disabled' : ''}>Next</button>
  `;
  paginationEl.querySelectorAll('.pagination-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (btn.disabled) return;
      if (btn.dataset.page === 'prev') tracePage--;
      else tracePage++;
      loadTraces(false);
    });
  });
}

async function loadTraces(skipDetailHide = false) {
  const url = API + '/api/traces?' + tracesQueryParams();
  const res = await fetch(url);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const list = document.getElementById('list');
    if (list) list.innerHTML = '<p class="empty">Failed to load traces: ' + (data.detail || res.status) + '</p>';
    renderPagination(0, 1, tracePageSize);
    return;
  }
  const traces = Array.isArray(data) ? data : (data.items || []);
  traceTotal = Array.isArray(data) ? data.length : (data.total ?? 0);
  const maxPage = Math.max(1, Math.ceil(traceTotal / tracePageSize));
  if (tracePage > maxPage) tracePage = maxPage;
  const list = document.getElementById('list');
  if (!traces.length) {
    list.innerHTML = '<p class="empty">No traces match the current filters.</p>';
    if (!skipDetailHide) closeTraceDetail();
    renderPagination(0, tracePage, tracePageSize);
    return;
  }
  list.innerHTML = buildTableHtml(traces);
  bindResizeHandles(list);
  const overlay = document.getElementById('trace-detail-overlay');
  const content = document.getElementById('detail-content');

  function showTraceInSidePanel(traceData) {
    const traceId = traceData.trace_id;
    const spans = Array.isArray(traceData.spans) ? traceData.spans : [traceData];
    selectedTraceId = traceId;
    if (overlay) overlay.classList.add('is-open');
    if (overlay) overlay.setAttribute('aria-hidden', 'false');
    const title = spans[0] ? (spans[0].name || traceId) : traceId;
    const titleShort = title.length > 24 ? title.slice(0, 24) + '…' : title;
    const spansHtml = spans.map((s, i) => {
      const skind = (s.kind || 'llm').toLowerCase();
      const sstatus = s.status || 'success';
      return `
        <div class="span-card" data-span-index="${i}">
          <div class="span-card-header">
            <span class="kind-badge kind-${skind}">${escapeHtml(skind)}</span>
            <strong>${escapeHtml(s.name || 'span ' + (i + 1))}</strong>
            <span class="status ${sstatus}">${sstatus}</span>
            ${s.model ? `<span class="span-meta">${escapeHtml(s.model)}</span>` : ''}
            ${s.latency_ms != null ? `<span class="span-meta">${s.latency_ms} ms</span>` : ''}
            ${s.cost_usd != null && s.cost_usd > 0 ? `<span class="span-meta">$${s.cost_usd.toFixed(4)}</span>` : ''}
          </div>
          ${s.error ? `<div class="span-error">${escapeHtml(s.error)}</div>` : ''}
          <div class="span-body">
            ${s.prompt ? `<div><label>Prompt</label><pre>${escapeHtml(s.prompt)}</pre></div>` : ''}
            ${s.completion ? `<div><label>Completion</label><pre>${escapeHtml(s.completion)}</pre></div>` : ''}
          </div>
        </div>
      `;
    }).join('');
    content.innerHTML = `
      <div class="detail-header">
        <h2 id="detail-title" title="${escapeHtml(traceId)}">${escapeHtml(titleShort)}</h2>
        <button type="button" class="detail-close" aria-label="Close">✕</button>
      </div>
      <div class="detail-meta">Trace: <code>${escapeHtml(traceId)}</code> · ${spans.length} span${spans.length !== 1 ? 's' : ''}</div>
      <div class="spans-list">${spansHtml}</div>
    `;
    content.querySelector('.detail-close').addEventListener('click', closeTraceDetail);
  }

  list.querySelector('.table-wrap tbody').addEventListener('click', async (e) => {
    const row = e.target.closest('tr');
    if (!row) return;
    const id = row.dataset.id;
    list.querySelectorAll('.table-wrap tbody tr.selected').forEach((r) => r.classList.remove('selected'));
    row.classList.add('selected');
    const r = await fetch(API + '/api/traces/' + encodeURIComponent(id));
    const data = await r.json();
    showTraceInSidePanel(data);
  });

  if (selectedTraceId) {
    const sel = list.querySelector('.table-wrap tbody tr[data-id="' + selectedTraceId + '"]');
    if (sel) sel.classList.add('selected');
    else if (!skipDetailHide) closeTraceDetail();
  }
  renderPagination(traceTotal, tracePage, tracePageSize);
}

function destroyCharts() {
  chartInstances.forEach((c) => { if (c) c.destroy(); });
  chartInstances = [];
}

function drawChart(id, labels, series, opts = {}) {
  const el = document.getElementById(id);
  if (!el || !labels.length) return;
  const data = [labels, series[0]];
  const stroke = opts.stroke || CHART_COLORS[0];
  const options = {
    width: el.offsetWidth || 500,
    height: 240,
    series: [{}, { stroke: stroke, width: 2.5 }],
    axes: [
      { stroke: '#2d3139', grid: { stroke: '#252830' }, ticks: { stroke: '#2d3139' }, font: '11px DM Sans, system-ui, sans-serif', fontColor: '#9aa0a6' },
      { stroke: '#2d3139', grid: { stroke: '#252830' }, ticks: { stroke: '#2d3139' }, font: '11px DM Sans, system-ui, sans-serif', fontColor: '#9aa0a6' }
    ],
    ...opts
  };
  try {
    const u = new uPlot(options, data, el);
    chartInstances.push(u);
  } catch (_) {}
}

async function loadMonitoring() {
  const res = await fetch(API + '/api/stats?since_hours=' + sinceHours);
  const s = await res.json();
  document.getElementById('summary').innerHTML = `
    <div class="panel"><h3>Trace count</h3><div class="value">${s.trace_count ?? 0}</div></div>
    <div class="panel"><h3>Error rate</h3><div class="value">${s.error_rate_pct ?? 0}%</div></div>
    <div class="panel"><h3>Total cost</h3><div class="value">$${(s.total_cost_usd ?? 0).toFixed(4)}</div></div>
    <div class="panel"><h3>P50 latency</h3><div class="value">${s.p50_latency_ms != null ? s.p50_latency_ms + ' ms' : '—'}</div></div>
  `;
  destroyCharts();
  const buckets = s.buckets || [];
  const chartIds = ['chart-count', 'chart-cost', 'chart-errors', 'chart-latency'];
  if (buckets.length === 0) {
    chartIds.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = '<p class="empty" style="margin:0;padding:0.5rem;">No data</p>';
    });
    return;
  }
  const labels = buckets.map((b) => new Date(b.date).getTime() / 1000);
  const seriesData = [
    buckets.map((b) => b.count),
    buckets.map((b) => b.cost_usd),
    buckets.map((b) => (b.count ? (b.error_count / b.count) * 100 : 0)),
    buckets.map((b) => b.avg_latency_ms || 0)
  ];
  const chartStrokes = [CHART_COLORS[0], CHART_COLORS[2], CHART_COLORS[1], CHART_COLORS[3]];
  setTimeout(() => {
    chartIds.forEach((id, i) => {
      const el = document.getElementById(id);
      if (el && el.offsetWidth) {
        el.innerHTML = '';
        drawChart(id, labels, [seriesData[i]], { stroke: chartStrokes[i] });
      }
    });
  }, 50);
}

bindTabsAndRange();
const overlayEl = document.getElementById('trace-detail-overlay');
const backdropEl = overlayEl && overlayEl.querySelector('.detail-overlay-backdrop');
if (backdropEl) backdropEl.addEventListener('click', closeTraceDetail);
loadTraces(false);
startPolling();
