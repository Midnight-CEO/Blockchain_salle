const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const titles = {dashboard:'Resumen general',lots:'Gestión de lotes',register:'Registrar un lote',verify:'Consultar trazabilidad',ledger:'Libro Blockchain'};
let allLots = [];

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}
function shortDate(value) {
  if (!value) return '—';
  return String(value).slice(0, 10);
}
function notify(message) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.classList.add('show');
  window.clearTimeout(notify.timer);
  notify.timer = window.setTimeout(() => toast.classList.remove('show'), 3000);
}
async function api(url, options = {}) {
  const response = await fetch(url, {headers:{'Content-Type':'application/json'}, ...options});
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || body.message || 'No fue posible completar la solicitud.');
  return body;
}
function showView(name) {
  if (!titles[name]) return;
  $$('.view').forEach(view => view.classList.toggle('active', view.id === `view-${name}`));
  $$('.nav-link').forEach(link => link.classList.toggle('active', link.dataset.view === name));
  $('#page-title').textContent = titles[name];
  if (name === 'lots') loadLots();
  if (name === 'ledger') loadLedger();
  if (name === 'dashboard') loadDashboard();
}
function lotProductIcon(product) { return product === 'Cacao' ? '◆' : '☕'; }
function renderLotRow(lot, compact = false) {
  const lotId = escapeHtml(lot.lot_id);
  const status = escapeHtml(lot.status || 'Lote creado');
  const firstCell = `<div class="lot-cell"><span class="product-symbol">${lotProductIcon(lot.product)}</span><span><strong>${escapeHtml(lot.lot_code)}</strong><small>${lotId}</small></span></div>`;
  if (compact) return `<tr class="clickable-row" data-lot="${lotId}"><td>${firstCell}</td><td>${escapeHtml(lot.producer)}</td><td>${escapeHtml(lot.origin)}</td><td><span class="status-pill">${status}</span></td></tr>`;
  return `<tr class="clickable-row" data-lot="${lotId}"><td><span class="block-index">${lotId}</span></td><td>${lotProductIcon(lot.product)} &nbsp;${escapeHtml(lot.product)}</td><td>${escapeHtml(lot.producer)}</td><td>${escapeHtml(lot.origin)}</td><td>${Number(lot.weight_kg).toLocaleString('es-CO')} kg</td><td><span class="status-pill">${status}</span></td><td><button class="text-button" data-open-lot="${lotId}">Ver →</button></td></tr>`;
}
function bindLotRows(root = document) {
  $$('tr[data-lot]', root).forEach(row => row.addEventListener('click', event => {
    if (event.target.closest('button')) return;
    openTrace(row.dataset.lot);
  }));
  $$('[data-open-lot]', root).forEach(button => button.addEventListener('click', () => openTrace(button.dataset.openLot)));
}
async function loadDashboard() {
  try {
    const summary = await api('/api/summary');
    $('#metric-lots').textContent = summary.lots;
    $('#metric-events').textContent = summary.events;
    $('#metric-blocks').textContent = summary.blocks;
    $('#metric-integrity').textContent = summary.integrity.valid ? 'Íntegro' : 'Revisar';
    $('#integrity-caption').textContent = summary.integrity.valid ? `${summary.integrity.checked} bloques verificados` : summary.integrity.message;
    $('#recent-lots-body').innerHTML = summary.recent_lots.length ? summary.recent_lots.map(lot => renderLotRow(lot, true)).join('') : '<tr><td colspan="4" class="empty-state">Aún no hay lotes registrados.</td></tr>';
    bindLotRows($('#recent-lots-body'));
    $('#updated-label').textContent = `Actualizado ${new Date().toLocaleTimeString('es-CO',{hour:'2-digit',minute:'2-digit'})}`;
  } catch (error) { notify(error.message); }
}
async function loadLots(search = '') {
  try {
    const result = await api(`/api/lots${search ? `?search=${encodeURIComponent(search)}` : ''}`);
    allLots = result.lots;
    $('#all-lots-body').innerHTML = allLots.length ? allLots.map(lot => renderLotRow(lot)).join('') : '<tr><td colspan="7" class="empty-state">No hay coincidencias para esa búsqueda.</td></tr>';
    $('#lot-counter').textContent = `${allLots.length} ${allLots.length === 1 ? 'lote' : 'lotes'}`;
    bindLotRows($('#all-lots-body'));
  } catch (error) { notify(error.message); }
}
function renderTrace(lot) {
  const events = [...(lot.events || [])].reverse();
  const timeline = events.map((event, index) => `<article class="timeline-item"><span class="timeline-marker">${index === events.length - 1 ? '⌂' : '✓'}</span><div class="timeline-content"><div class="timeline-top"><strong>${escapeHtml(event.type)}</strong><time>${escapeHtml(String(event.timestamp).slice(0,16).replace('T',' '))} UTC</time></div><p>${escapeHtml(event.description)}</p><div class="timeline-meta"><span>${escapeHtml(event.location)}</span><span>${escapeHtml(event.role)} · ${escapeHtml(event.actor)}</span></div><small class="block-hash">Bloque #${event.block_index} · ${escapeHtml(event.hash.slice(0,28))}…</small></div></article>`).join('');
  const publicUrl = `${window.location.origin}/public/trace/${encodeURIComponent(lot.lot_id)}`;
  $('#trace-result').innerHTML = `<div class="trace-card panel"><div class="trace-details"><div class="trace-heading"><div><span class="eyebrow">HISTORIAL DE TRAZABILIDAD</span><h3>${escapeHtml(lot.product)} · ${escapeHtml(lot.lot_code)}</h3><span class="trace-subtitle">${escapeHtml(lot.lot_id)} · ${escapeHtml(lot.origin)}</span></div><span class="integrity-chip ok">✓ Registrado</span></div><div class="trace-facts"><div class="trace-fact"><span>PRODUCTOR</span><strong>${escapeHtml(lot.producer)}</strong></div><div class="trace-fact"><span>COSECHA</span><strong>${escapeHtml(shortDate(lot.harvest_date))}</strong></div><div class="trace-fact"><span>PESO</span><strong>${Number(lot.weight_kg).toLocaleString('es-CO')} kg</strong></div></div><span class="eyebrow">RECORRIDO DEL LOTE</span><div class="timeline">${timeline}</div></div><aside class="trace-qr"><img src="/qr/${encodeURIComponent(lot.lot_id)}.png" alt="Código QR para consultar ${escapeHtml(lot.lot_id)}"><strong>Consulta pública</strong><p>Escanea el código para abrir el historial del lote.</p><a href="${publicUrl}" target="_blank" rel="noopener">Abrir ficha ↗</a></aside></div><form class="panel add-event-panel" id="event-form"><h3>＋ Añadir un evento al recorrido</h3><div class="event-form-grid"><select name="event_type" required><option>Recepción</option><option>Despacho</option><option>Control de calidad</option><option>Transformación</option><option>Entrega confirmada</option></select><input name="location" required maxlength="120" placeholder="Ubicación del evento"><input name="actor" required maxlength="100" placeholder="Responsable"><select name="role"><option>Cooperativa</option><option>Transportador</option><option>Procesador</option><option>Exportador</option><option>Tostador</option><option>Productor</option></select><input class="event-desc" name="description" required maxlength="300" placeholder="Descripción del movimiento"><button class="button button-primary" type="submit">Guardar evento →</button></div><div class="form-message" id="event-message" role="status"></div></form><div class="demo-disclaimer"><span>ⓘ</span><p>La huella demuestra que este historial coincide con el contenido registrado. La verificación física del producto requiere controles externos.</p></div>`;
  $('#event-form').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form).entries());
    try {
      const result = await api(`/api/lots/${encodeURIComponent(lot.lot_id)}/events`, {method:'POST', body:JSON.stringify(payload)});
      notify(`Evento incorporado en el bloque #${result.block_index}.`);
      await openTrace(lot.lot_id);
      loadDashboard();
    } catch (error) { $('#event-message').textContent = error.message; $('#event-message').classList.add('error'); }
  });
}
async function openTrace(query) {
  showView('verify');
  $('#verify-query').value = query;
  try {
    let lot;
    if (String(query).startsWith('OC-')) {
      const result = await api(`/api/lots/${encodeURIComponent(query)}`);
      lot = result.lot;
    } else {
      const result = await api(`/api/lots?search=${encodeURIComponent(query)}`);
      lot = result.lots.find(item => item.lot_code.toLowerCase() === String(query).toLowerCase() || item.lot_id.toLowerCase() === String(query).toLowerCase());
    }
    if (!lot) throw new Error('No encontramos un lote con ese identificador o código.');
    renderTrace(lot);
  } catch (error) {
    $('#trace-result').innerHTML = `<div class="empty-illustration">⌕</div><h3>No encontramos ese lote.</h3><p>${escapeHtml(error.message)}</p>`;
  }
}
async function loadLedger() {
  try {
    const [verification, result] = await Promise.all([api('/api/chain/verify'), api('/api/chain/blocks')]);
    const banner = $('#ledger-integrity');
    banner.classList.toggle('bad', !verification.valid);
    banner.innerHTML = `<div class="integrity-symbol">${verification.valid ? '✓' : '!'}</div><div><strong>${verification.valid ? 'Integridad confirmada' : 'Se detectó una inconsistencia'}</strong><p>${escapeHtml(verification.message)} · ${verification.checked} bloques revisados.</p></div>`;
    $('#block-counter').textContent = `${result.blocks.length} bloques visibles`;
    $('#blocks-body').innerHTML = result.blocks.length ? result.blocks.map(block => {
      const data = block.data || {};
      const type = data.type === 'LOT_CREATED' ? 'Creación de lote' : data.type === 'TRACE_EVENT' ? data.event_type : 'Bloque inicial';
      return `<tr><td><span class="block-index">#${block.index}</span></td><td>${escapeHtml(type)}</td><td>${escapeHtml(data.lot_id || '—')}</td><td class="hash-cell">${escapeHtml(block.hash.slice(0,34))}…</td><td>${escapeHtml(String(block.timestamp).slice(0,16).replace('T',' '))}</td></tr>`;
    }).join('') : '<tr><td colspan="5" class="empty-state">No hay bloques.</td></tr>';
  } catch (error) { notify(error.message); }
}

// Sidebar, cards and contextual navigation.
$$('[data-view]').forEach(button => button.addEventListener('click', () => showView(button.dataset.view)));
$('#refresh-button').addEventListener('click', () => { loadDashboard(); if ($('#view-lots').classList.contains('active')) loadLots(); if ($('#view-ledger').classList.contains('active')) loadLedger(); notify('Datos actualizados.'); });
$('#lot-search').addEventListener('input', event => loadLots(event.target.value.trim()));
$('#lot-form').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  const message = $('#lot-form-message');
  message.textContent = '';
  message.classList.remove('error');
  try {
    const result = await api('/api/lots', {method:'POST', body:JSON.stringify(payload)});
    message.textContent = `Lote creado correctamente: ${result.lot.lot_id}`;
    notify('Lote añadido al libro Blockchain.');
    form.reset();
    loadDashboard();
    window.setTimeout(() => openTrace(result.lot.lot_id), 400);
  } catch (error) { message.textContent = error.message; message.classList.add('error'); }
});
$('#verify-form').addEventListener('submit', event => { event.preventDefault(); openTrace($('#verify-query').value.trim()); });
$('#verify-chain-button').addEventListener('click', async () => { await loadLedger(); const result = await api('/api/chain/verify'); notify(result.message); });
$$('[data-example]').forEach(button => button.addEventListener('click', () => openTrace(button.dataset.example)));

loadDashboard();
