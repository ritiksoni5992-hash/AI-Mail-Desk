/**
 * MailDesk AI — Frontend JavaScript
 */

// ── State ─────────────────────────────────────────────────────────────────────
const State = {
  currentSection: 'all',
  currentCat: null,
  selectedId: null,
  activeDotMenu: null,
  settings: {},
};

// ── Utility ───────────────────────────────────────────────────────────────────
function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

function timeAgo(isoStr) {
  if (!isoStr) return '–';
  const d = new Date(isoStr);
  const now = new Date();
  const diff = Math.floor((now - d) / 1000);
  if (diff < 60)    return 'just now';
  if (diff < 3600)  return Math.floor(diff / 60) + ' min ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  if (diff < 604800)return Math.floor(diff / 86400) + 'd ago';
  return d.toLocaleDateString();
}

function avatarColor(str) {
  const colors = ['#5B5BD6','#7C3AED','#059669','#D97706','#DC2626','#0891B2','#BE185D','#EA580C'];
  let hash = 0;
  for (let c of str) hash = c.charCodeAt(0) + ((hash << 5) - hash);
  return colors[Math.abs(hash) % colors.length];
}

function catBadge(cat) {
  const m = { query: 'cat-query', feedback: 'cat-feedback', support: 'cat-support', general: 'cat-general' };
  const l = { query: 'Query', feedback: 'Feedback', support: 'Support', general: 'General' };
  return `<span class="cat-badge ${m[cat] || 'cat-general'}">${l[cat] || cat}</span>`;
}

async function api(url, opts = {}) {
  opts.headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (opts.body && typeof opts.body === 'object') opts.body = JSON.stringify(opts.body);
  const r = await fetch(url, opts);
  if (r.status === 401) { window.location.href = '/setup'; return null; }
  return r.json();
}

// ── Navigation ─────────────────────────────────────────────────────────────────
function showView(view) {
  document.querySelectorAll('.view-panel').forEach(p => p.classList.remove('active'));
  const panel = document.getElementById('view-' + view);
  if (panel) { panel.classList.add('active'); panel.style.display = 'flex'; }

  // Hide detail pane for non-inbox views
  if (view !== 'inbox') {
    document.getElementById('detail-pane').classList.add('hidden');
    State.selectedId = null;
  }

  if (view === 'summary') loadSummary();
  if (view === 'settings') loadSettings();
  if (view === 'inbox') loadEmails();
}

function navTo(el) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  el.classList.add('active');
  State.currentSection = el.dataset.section || 'all';
  State.currentCat = null;
  const titles = { all: 'All Emails', unread: 'Unread', starred: 'Starred', sent: 'Sent' };
  document.getElementById('inbox-title').innerHTML =
    `${titles[State.currentSection] || State.currentSection} <span class="title-count" id="inbox-count"></span>`;
  showView('inbox');
}

function navCat(el) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  el.classList.add('active');
  State.currentCat = el.dataset.cat;
  State.currentSection = 'all';
  const labels = { query: 'Queries', feedback: 'Feedback', support: 'Support', general: 'General' };
  document.getElementById('inbox-title').innerHTML =
    `${labels[State.currentCat]} <span class="title-count" id="inbox-count"></span>`;
  showView('inbox');
}

// ── Email List ─────────────────────────────────────────────────────────────────
async function loadEmails() {
  const params = new URLSearchParams();

  // section → status filter
  if (State.currentSection === 'unread')  params.set('status', 'unread');
  if (State.currentSection === 'starred') params.set('status', 'starred');
  if (State.currentSection === 'sent')    params.set('status', 'read');

  // sidebar filter selects
  const fStatus = document.getElementById('f-status')?.value;
  const fDate   = document.getElementById('f-date')?.value;
  const fLimit  = document.getElementById('f-limit')?.value || 25;
  const search  = document.getElementById('search-q')?.value?.trim();
  const sort    = document.getElementById('sort-sel')?.value || 'newest';

  if (fStatus) params.set('status', fStatus);
  if (fDate)   params.set('date', fDate);
  params.set('limit', fLimit);
  params.set('sort', sort);
  if (search)  params.set('q', search);
  if (State.currentCat) params.set('category', State.currentCat);

  const data = await api('/api/emails/?' + params.toString());
  if (!data) return;

  renderEmailList(data.emails);
  const countEl = document.getElementById('inbox-count');
  if (countEl) countEl.textContent = `(${data.total})`;

  // Also refresh counts
  loadCounts();
}

function renderEmailList(emails) {
  const el = document.getElementById('email-list');
  if (!emails.length) {
    el.innerHTML = '<div class="list-empty">No emails found.</div>';
    return;
  }
  el.innerHTML = emails.map(e => {
    const color = avatarColor(e.sender_email || '');
    const initial = (e.sender_name || e.sender_email || '?')[0].toUpperCase();
    const unread = !e.is_seen;
    const sel = State.selectedId === e.id;
    const preview = (e.body_text || '').replace(/\n/g, ' ').substring(0, 80);
    const isHighPriority = e.priority === 'high';

    return `
    <div class="email-item${unread ? ' unread' : ''}${sel ? ' selected' : ''}"
         id="eitem-${e.id}" onclick="openEmail(${e.id})">
      ${unread ? '<div class="unread-dot"></div>' : '<div class="read-spacer"></div>'}
      <div class="email-avatar" style="background:${color}">${initial}</div>
      <div class="email-meta">
        <div class="email-header">
          <span class="email-from">${e.sender_name || e.sender_email}</span>
          <span class="email-date">${timeAgo(e.received_at)}</span>
        </div>
        <div class="email-subject">${e.subject || '(no subject)'}</div>
        <div class="email-preview">${preview}…</div>
        <div class="email-badges">
          ${catBadge(e.category)}
          ${isHighPriority ? '<span class="priority-high">🔴 Urgent</span>' : ''}
          ${e.is_starred ? '<span class="starred-mark">⭐</span>' : ''}
          ${e.reply_sent ? '<span class="cat-badge" style="background:#ECFDF5;color:#065F46">✓ Replied</span>' : ''}
        </div>
      </div>
      <button class="dot-btn" onclick="toggleDotMenu(event,${e.id})">⋯</button>
      <div class="dot-menu" id="dot-${e.id}">
        <div class="dot-opt" onclick="markSeen(${e.id},${!e.is_seen})">${e.is_seen ? '○ Mark unread' : '✓ Mark read'}</div>
        <div class="dot-opt" onclick="openEmail(${e.id});setTimeout(generateReply,400)">✦ Generate AI reply</div>
        <div class="dot-opt" onclick="cycleCategory(${e.id})">📂 Move category</div>
        <div class="dot-opt" onclick="starEmailItem(${e.id})">⭐ ${e.is_starred ? 'Unstar' : 'Star'}</div>
        <div class="dot-opt" onclick="snoozeItem(${e.id})">⏰ Snooze 1h</div>
        <div class="dot-opt danger" onclick="archiveItem(${e.id})">🗑 Archive</div>
      </div>
    </div>`;
  }).join('');
}

// ── Dot menu ──────────────────────────────────────────────────────────────────
function toggleDotMenu(evt, id) {
  evt.stopPropagation();
  if (State.activeDotMenu && State.activeDotMenu !== id) {
    document.getElementById('dot-' + State.activeDotMenu)?.classList.remove('show');
  }
  const menu = document.getElementById('dot-' + id);
  menu?.classList.toggle('show');
  State.activeDotMenu = menu?.classList.contains('show') ? id : null;
}

document.addEventListener('click', () => {
  if (State.activeDotMenu) {
    document.getElementById('dot-' + State.activeDotMenu)?.classList.remove('show');
    State.activeDotMenu = null;
  }
});

// ── Email actions ──────────────────────────────────────────────────────────────
async function markSeen(id, seen) {
  await api(`/api/emails/${id}/seen`, { method: 'PATCH', body: { seen } });
  loadEmails();
}

async function starEmailItem(id) {
  await api(`/api/emails/${id}/star`, { method: 'PATCH' });
  loadEmails();
  if (State.selectedId === id) openEmail(id);
}

async function archiveItem(id) {
  await api(`/api/emails/${id}/archive`, { method: 'PATCH' });
  if (State.selectedId === id) closeDetail();
  loadEmails();
}

async function snoozeItem(id) {
  await api(`/api/emails/${id}/snooze`, { method: 'PATCH', body: { hours: 1 } });
  loadEmails();
}

async function cycleCategory(id) {
  const cats = ['query', 'feedback', 'support', 'general'];
  const el = document.getElementById('eitem-' + id);
  // find current category from DOM badge
  const badge = el?.querySelector('.cat-badge');
  const cur = badge?.className.replace('cat-badge cat-', '').trim() || 'general';
  const next = cats[(cats.indexOf(cur) + 1) % cats.length];
  await api(`/api/emails/${id}/category`, { method: 'PATCH', body: { category: next } });
  loadEmails();
}

async function markAllRead() {
  await api('/api/emails/mark-all-read', { method: 'PATCH' });
  loadEmails();
}

async function doSync() {
  const btn = document.getElementById('sync-btn');
  btn.innerHTML = '<span class="spin"></span> Syncing…';
  btn.disabled = true;
  const data = await api('/api/emails/sync', { method: 'POST' });
  btn.textContent = '⟳ Sync';
  btn.disabled = false;
  if (data?.ok) {
    loadEmails();
    if (data.new > 0) showToast(`✓ Synced ${data.new} new email(s)`);
    else showToast('✓ Already up to date');
  }
}

// ── Email detail ───────────────────────────────────────────────────────────────
async function openEmail(id) {
  State.selectedId = id;
  // Mark previous selection
  document.querySelectorAll('.email-item.selected').forEach(el => el.classList.remove('selected'));
  document.getElementById('eitem-' + id)?.classList.add('selected');

  const e = await api(`/api/emails/${id}`);
  if (!e) return;

  const color = avatarColor(e.sender_email || '');
  document.getElementById('d-subject').textContent = e.subject || '(no subject)';
  const av = document.getElementById('d-avatar');
  av.textContent = (e.sender_name || e.sender_email || '?')[0].toUpperCase();
  av.style.background = color;
  document.getElementById('d-name').textContent = e.sender_name || e.sender_email;
  document.getElementById('d-email-addr').textContent = e.sender_email;
  document.getElementById('d-badge').innerHTML = catBadge(e.category);
  document.getElementById('d-priority').innerHTML = e.priority === 'high'
    ? '<span class="priority-high">🔴 Urgent</span>' : '';
  document.getElementById('d-date').textContent = timeAgo(e.received_at);
  document.getElementById('d-body').textContent = e.body_text || '(no body)';

  // Pre-fill AI reply if already generated
  const replyEl = document.getElementById('d-reply');
  replyEl.textContent = e.ai_reply || 'Click "Generate" to create a smart AI reply for this email.';
  replyEl.style.color = '';
  replyEl.contentEditable = 'false';
  replyEl.style.border = '';

  document.getElementById('gen-btn').textContent = e.ai_reply ? '✦ Regenerate' : '✦ Generate';
  document.getElementById('gen-btn').disabled = false;

  // Hide summary
  document.getElementById('d-summary').style.display = 'none';

  document.getElementById('detail-pane').classList.remove('hidden');

  // Refresh list to reflect seen state
  setTimeout(loadEmails, 300);
}

function closeDetail() {
  document.getElementById('detail-pane').classList.add('hidden');
  State.selectedId = null;
  document.querySelectorAll('.email-item.selected').forEach(el => el.classList.remove('selected'));
}

// ── AI Reply ───────────────────────────────────────────────────────────────────
async function generateReply() {
  if (!State.selectedId) return;
  const btn = document.getElementById('gen-btn');
  btn.innerHTML = '<span class="spin"></span> Gemini thinking…';
  btn.disabled = true;

  // Key priority: settings page input → localStorage → server config
  const apiKey = document.getElementById('st-api-key')?.value || localStorage.getItem('gemini_key') || '';

  const data = await api(`/api/ai/generate-reply/${State.selectedId}`, {
    method: 'POST',
    body: { api_key: apiKey, tone: document.getElementById('st-tone')?.value || 'professional' },
  });

  if (data?.ok) {
    document.getElementById('d-reply').textContent = data.reply;
    document.getElementById('d-reply').style.color = '';
    btn.textContent = '✦ Regenerate';
  } else {
    document.getElementById('d-reply').textContent = '⚠ ' + (data?.error || 'Generation failed. Check your Gemini API key in Settings.');
    document.getElementById('d-reply').style.color = 'var(--danger)';
    btn.textContent = '✦ Generate';
  }
  btn.disabled = false;
}

function editReply() {
  const box = document.getElementById('d-reply');
  box.contentEditable = 'true';
  box.style.border = '1.5px solid var(--accent)';
  box.focus();
}

async function sendReply() {
  const box = document.getElementById('d-reply');
  const body = box.textContent.trim();
  if (!body || body.startsWith('Click')) {
    showToast('⚠ Generate a reply first!', 'warn');
    return;
  }
  const data = await api(`/api/emails/${State.selectedId}/send-reply`, {
    method: 'POST',
    body: { body },
  });
  if (data?.ok) {
    box.textContent = '✓ Reply sent successfully!';
    box.style.color = 'var(--success)';
    box.contentEditable = 'false';
    box.style.border = '';
    setTimeout(() => { box.style.color = ''; }, 3000);
    loadEmails();
  } else {
    showToast('✗ Send failed: ' + (data?.error || 'Unknown error'), 'error');
  }
}

// ── Detail actions ─────────────────────────────────────────────────────────────
async function summarizeEmail() {
  if (!State.selectedId) return;
  const data = await api(`/api/ai/summarize/${State.selectedId}`, { method: 'POST' });
  const summaryEl = document.getElementById('d-summary');
  if (data?.ok) {
    document.getElementById('d-summary-text').textContent = data.summary;
    summaryEl.style.display = 'block';
  }
}

async function reclassify() {
  if (!State.selectedId) return;
  const data = await api(`/api/ai/reclassify/${State.selectedId}`, { method: 'POST' });
  if (data?.ok) {
    document.getElementById('d-badge').innerHTML = catBadge(data.category);
    showToast(`✓ Reclassified as: ${data.category} / ${data.sentiment}`);
    loadEmails();
  }
}

async function toggleStar() {
  if (!State.selectedId) return;
  await starEmailItem(State.selectedId);
}

async function snoozeEmail() {
  if (!State.selectedId) return;
  await snoozeItem(State.selectedId);
  showToast('⏰ Snoozed for 1 hour');
  closeDetail();
  loadEmails();
}

async function archiveEmail() {
  if (!State.selectedId) return;
  await archiveItem(State.selectedId);
  closeDetail();
}

// ── Counts ─────────────────────────────────────────────────────────────────────
async function loadCounts() {
  const data = await api('/api/emails/stats/counts');
  if (!data) return;
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  set('b-all',      data.total);
  set('b-unread',   data.unread);
  set('b-starred',  data.starred);
  set('b-replied',  data.replied);
  set('b-query',    data.query);
  set('b-feedback', data.feedback);
  set('b-support',  data.support);
  set('b-general',  data.general);
}

// ── Summary Dashboard ──────────────────────────────────────────────────────────
async function loadSummary() {
  const data = await api('/api/dashboard/summary');
  if (!data) return;

  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  set('s-total',   data.total);
  set('s-unread',  data.unread);
  set('s-replied', data.replied);
  set('s-pending', data.pending);
  set('s-rrate',   data.response_rate + '%');
  set('s-avgt',    data.avg_response_hrs + 'h');
  set('sum-last-sync', data.last_sync ? 'Last synced ' + timeAgo(data.last_sync) : 'Not synced yet');

  // Category bars
  const cats = data.categories;
  const maxCat = Math.max(...Object.values(cats), 1);
  const catColors = { query: '#F59E0B', feedback: '#EC4899', support: '#059669', general: '#6B7280' };
  document.getElementById('cat-bars').innerHTML = Object.entries(cats).map(([cat, count]) => `
    <div class="cat-bar-row">
      <div class="cat-bar-lbl">${cat[0].toUpperCase() + cat.slice(1)}</div>
      <div class="cat-bar-track">
        <div class="cat-bar-fill" style="width:${(count/maxCat*100).toFixed(0)}%;background:${catColors[cat]}"></div>
      </div>
      <div class="cat-bar-n">${count}</div>
    </div>`).join('');

  // Daily chart
  const daily = data.daily_counts;
  const maxDay = Math.max(...daily.map(d => d.count), 1);
  document.getElementById('daily-chart').innerHTML = daily.map(d => `
    <div class="bar-w">
      <div class="bar-top">${d.count}</div>
      <div class="bar-fill" style="height:${(d.count/maxDay*100).toFixed(0)}%"></div>
    </div>`).join('');
  document.getElementById('daily-labels').innerHTML = daily.map(d =>
    `<span>${d.date}</span>`).join('');

  // Activity
  document.getElementById('activity-list').innerHTML = (data.activity || []).map(a => {
    const dotColors = { reply_sent: '#5B5BD6', sync: '#059669', archived: '#6B7280', negative_flagged: '#DC2626' };
    return `<div class="activity-item">
      <div class="act-dot" style="background:${dotColors[a.action] || '#8888aa'}"></div>
      <div><div class="act-text">${a.description}</div><div class="act-time">${timeAgo(a.created_at)}</div></div>
    </div>`;
  }).join('') || '<div class="act-text" style="color:var(--ink3)">No activity yet.</div>';

  // Keywords
  document.getElementById('keywords').innerHTML = (data.top_keywords || []).map(k =>
    `<span class="kw-tag">${k.word} <span style="color:var(--ink3)">${k.count}</span></span>`
  ).join('');

  // Suggestions
  document.getElementById('suggestions').innerHTML = (data.suggestions || []).map(s =>
    `<div>💡 ${s}</div>`).join('') || '<div style="color:var(--ink3)">All looks good! 🎉</div>';
}

// ── Settings ───────────────────────────────────────────────────────────────────
async function loadSettings() {
  const data = await api('/api/settings/');
  if (!data) return;
  State.settings = data;

  const setToggle = (id, val) => {
    const el = document.getElementById(id);
    if (el) { if (val) el.classList.add('on'); else el.classList.remove('on'); }
  };
  const setSel = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.value = val;
  };

  setSel('st-sync',    data.sync_interval);
  setSel('st-tone',    data.ai_tone);
  setSel('st-lang',    data.reply_language);
  setSel('st-limit',   data.email_limit);
  setSel('st-archive', data.auto_archive_days);
  setToggle('st-auto-draft',   data.auto_draft);
  setToggle('st-req-approve',  data.require_approval);
  setToggle('st-notif-new',    data.notif_new);
  setToggle('st-notif-neg',    data.notif_negative);
  setToggle('st-notif-sla',    data.notif_sla);
  setToggle('st-notif-digest', data.notif_digest);

  const savedKey = localStorage.getItem('gemini_key') || '';
  if (savedKey) document.getElementById('st-api-key').value = savedKey;
}

async function saveSetting(key, value) {
  await api('/api/settings/', { method: 'PATCH', body: { [key]: value } });
}

function toggleSetting(el, key) {
  el.classList.toggle('on');
  saveSetting(key, el.classList.contains('on'));
}

// ── Logout ─────────────────────────────────────────────────────────────────────
async function doLogout() {
  const data = await api('/api/auth/logout', { method: 'POST' });
  if (data?.ok) window.location.href = data.redirect;
}

// ── Toast ──────────────────────────────────────────────────────────────────────
function showToast(msg, type = 'success') {
  const t = document.createElement('div');
  t.style.cssText = `position:fixed;bottom:24px;right:24px;padding:10px 18px;
    border-radius:10px;font-size:13px;font-weight:500;z-index:9999;
    box-shadow:0 4px 16px rgba(0,0,0,.15);animation:fadeUp .25s ease;
    background:${type === 'error' ? '#FEF2F2' : type === 'warn' ? '#FFFBEB' : '#ECFDF5'};
    color:${type === 'error' ? '#DC2626' : type === 'warn' ? '#92400E' : '#059669'};
    border:1px solid ${type === 'error' ? '#FECACA' : type === 'warn' ? '#FDE68A' : '#A7F3D0'};`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

// ── Vision image analysis ──────────────────────────────────────────────────────
async function analyzeVisionImage() {
  if (!State.selectedId) return;
  const fileInput = document.getElementById('vision-file');
  const file = fileInput?.files?.[0];
  if (!file) { showToast('Select an image file first.', 'warn'); return; }

  const resultEl = document.getElementById('vision-result');
  resultEl.textContent = '🔍 Gemini Vision analyzing…';
  resultEl.style.display = 'block';
  resultEl.style.color = 'var(--ink3)';

  const formData = new FormData();
  formData.append('image', file);
  const apiKey = document.getElementById('st-api-key')?.value || localStorage.getItem('gemini_key') || '';
  if (apiKey) formData.append('api_key', apiKey);

  try {
    const resp = await fetch(`/api/ai/analyze-attachment/${State.selectedId}`, {
      method: 'POST', body: formData,
    });
    const data = await resp.json();
    if (data.ok) {
      resultEl.textContent = '👁 ' + data.analysis;
      resultEl.style.color = 'var(--ink2)';
    } else {
      resultEl.textContent = '⚠ ' + (data.error || 'Analysis failed');
      resultEl.style.color = 'var(--danger)';
    }
  } catch (e) {
    resultEl.textContent = '⚠ Network error';
    resultEl.style.color = 'var(--danger)';
  }
}

// ── Reply template suggestions ─────────────────────────────────────────────────
async function loadTemplates() {
  if (!State.selectedId) return;
  const zone = document.getElementById('templates-zone');
  const list = document.getElementById('templates-list');
  zone.style.display = 'block';
  list.innerHTML = '<span style="font-size:12px;color:var(--ink3)">Loading templates…</span>';

  const apiKey = document.getElementById('st-api-key')?.value || localStorage.getItem('gemini_key') || '';
  const data = await api(`/api/ai/templates/${State.selectedId}`, {
    method: 'POST', body: { api_key: apiKey },
  });
  if (data?.ok) {
    list.innerHTML = data.templates.map((t, i) => `
      <div onclick="applyTemplate(${i})" data-tpl="${t.replace(/"/g, '&quot;')}"
           style="padding:6px 10px;border:1px solid var(--border);border-radius:7px;
                  font-size:12px;color:var(--ink2);cursor:pointer;margin-bottom:5px;
                  transition:background .15s"
           onmouseover="this.style.background='var(--surface)'"
           onmouseout="this.style.background=''">
        ${t}
      </div>`).join('');
  } else {
    list.innerHTML = `<span style="font-size:12px;color:var(--danger)">${data?.error || 'Failed'}</span>`;
  }
}

function applyTemplate(idx) {
  const items = document.querySelectorAll('#templates-list [data-tpl]');
  const tpl = items[idx]?.dataset?.tpl;
  if (!tpl) return;
  const box = document.getElementById('d-reply');
  box.contentEditable = 'true';
  box.style.border = '1.5px solid var(--accent)';
  box.textContent = tpl + '\n\n';
  box.focus();
  document.getElementById('templates-zone').style.display = 'none';
}

// ── Gemini key save & test ─────────────────────────────────────────────────────
async function saveGeminiKey(val) {
  localStorage.setItem('gemini_key', val);
  // Also save to DB
  await api('/api/settings/', { method: 'PATCH', body: { gemini_api_key: val } });
  showToast('✓ Gemini API key saved');
}

async function testGeminiKey() {
  const key = document.getElementById('st-api-key')?.value || localStorage.getItem('gemini_key') || '';
  if (!key) { showToast('Enter a Gemini API key first.', 'warn'); return; }
  const data = await api('/api/ai/test-key', { method: 'POST', body: { api_key: key } });
  if (data?.ok) showToast('✓ ' + data.message);
  else showToast('✗ ' + (data?.error || 'Invalid key'), 'error');
}

// ── Init ───────────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  showView('inbox');
  loadCounts();

  // Auto-refresh counts every 30s
  setInterval(loadCounts, 30000);
});
