'use strict';
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const icon = (name) => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fragment = new URLSearchParams(location.hash.slice(1));
const token = fragment.get('token') || sessionStorage.getItem('offbeat-token') || '';
if (token) sessionStorage.setItem('offbeat-token', token);
history.replaceState(null, '', location.pathname);
let state, page = 'download', filter = 'all', previewId, dismissedId;
let selected = new Set(), toastTimer, settingsPromise = Promise.resolve();
let queueSignature = '', librarySignature = '', previewSignature = '', playlistSignature = '';
const activeStates = new Set(['queued', 'downloading', 'converting', 'retrying']);

async function api(path, data) {
  const response = await fetch('/api/' + path, {method: data === undefined ? 'GET' : 'POST', headers: {'X-Offbeat-Token': token, 'Content-Type': 'application/json'}, ...(data === undefined ? {} : {body: JSON.stringify(data)})});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Something went wrong. Try again.');
  return result;
}
function toast(message) {
  $('#toast').textContent = message;
  $('#toast').classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('#toast').classList.remove('visible'), 5000);
}
function handle(task) { return async (event) => { try { await task(event); } catch (error) { toast(error.message); } }; }
function showPage(next) {
  page = next;
  $$('.page').forEach(el => el.hidden = el.id !== 'page-' + next);
  $$('.nav-item').forEach(el => { el.classList.toggle('active', el.dataset.page === next); el.setAttribute('aria-current', el.dataset.page === next ? 'page' : 'false'); });
  $('#page-name').textContent = {download:'Download', queue:'Queue', library:'My library', playlists:'Playlists', settings:'Settings'}[next];
  if (next === 'settings' && state) {
    $('#folder-path').value = state.settings.folder;
    $('#settings-skip').checked = state.settings.skip_duplicates;
    $('#concurrent-downloads').value = state.settings.concurrent_downloads;
    $('#settings-feedback').textContent = '';
  }
  window.scrollTo({top:0, behavior:'instant'});
  if (state) render();
}
function duration(value) {
  if (!Number.isFinite(value)) return '';
  const s = Math.round(value);
  return s >= 3600 ? `${Math.floor(s/3600)}:${String(Math.floor(s%3600/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}` : `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;
}
function qualityLabel(item) { return item.mode === 'audio' ? `MP3 · ${item.quality} kbps` : `MP4 · ${item.quality === 'best' ? 'Best available' : item.quality + 'p'}`; }
function sizeLabel(size) { return size >= 1073741824 ? (size/1073741824).toFixed(1) + ' GB' : (size/1048576).toFixed(1) + ' MB'; }
function thumb(item) { return `<img class="thumb" src="https://i.ytimg.com/vi/${encodeURIComponent(item.video_id)}/mqdefault.jpg" alt="" loading="lazy" referrerpolicy="no-referrer">`; }
function saveSettings(changes) {
  settingsPromise = settingsPromise.catch(() => {}).then(() => api('settings', changes));
  return settingsPromise.then(settings => { if (state) state.settings = settings; renderSettings(); return settings; });
}
function renderSettings() {
  if (!state) return;
  const settings = state.settings;
  $$('[data-mode]').forEach(button => { const on = button.dataset.mode === settings.mode; button.classList.toggle('selected', on); button.setAttribute('aria-pressed', String(on)); });
  const quality = $('#quality');
  if (quality.dataset.mode !== settings.mode) {
    quality.innerHTML = settings.mode === 'audio' ? '<option value="320">320 kbps · High</option><option value="192">192 kbps · Standard</option><option value="128">128 kbps · Small</option>' : '<option value="1080">1080p · Full HD</option><option value="720">720p · HD</option><option value="2160">2160p · 4K</option><option value="best">Best available</option>';
    quality.dataset.mode = settings.mode;
  }
  quality.value = settings[settings.mode + '_quality'];
  $('#skip-duplicates').checked = settings.skip_duplicates;
  const folder = settings.folder.replace(/[\\/]+$/, '').split(/[\\/]/).pop();
  $('#destination-name').textContent = folder || settings.folder;
  $('#destination').title = settings.folder;
}
function renderPreview() {
  const preview = state.preview;
  const loading = preview.status === 'loading';
  $('#preview-loading').hidden = !loading;
  $('#preview-loading-text').textContent = `Checked ${preview.checked || 0} of ${preview.link_count || 1} links. Large playlists can take a moment.`;
  $('#inspect').disabled = loading;
  $('#inspect').innerHTML = loading ? 'Checking…' : 'Check links' + icon('arrow');
  $('#preview-error').hidden = preview.status !== 'error';
  $('#preview-error').textContent = preview.error || '';
  const visible = preview.status === 'ready' && preview.id !== dismissedId;
  $('#preview-panel').hidden = !visible;
  $('#how-it-works').hidden = visible || loading;
  if (!visible) return;
  if (preview.id !== previewId) {
    previewId = preview.id;
    selected = new Set(preview.items.filter(item => !item.unavailable).map(item => item.video_id));
    previewSignature = '';
  }
  const signature = JSON.stringify([preview.id, state.settings.mode, state.library.map(i => [i.video_id, i.mode, i.exists])]);
  if (signature !== previewSignature) {
    previewSignature = signature;
    $('#preview-type').textContent = (preview.sources || []).length > 1 ? 'COMBINED PREVIEW' : preview.is_playlist ? 'PLAYLIST PREVIEW' : 'VIDEO PREVIEW';
    $('#preview-title').textContent = preview.title;
    const unavailable = preview.items.filter(i => i.unavailable).length + (preview.unavailable || 0);
    $('#preview-summary').textContent = `${preview.items.length} ${preview.items.length === 1 ? 'item' : 'items'} found${unavailable ? ` · ${unavailable} live/upcoming or missing entries` : ''}${preview.duplicates ? ` · ${preview.duplicates} repeated entries combined` : ''}`;
    $('#preview-items').innerHTML = preview.items.map(item => {
      const saved = state.library.some(record => record.video_id === item.video_id && record.mode === state.settings.mode && record.exists);
      return `<div class="item-row"><input type="checkbox" data-video="${escapeHTML(item.video_id)}" aria-label="Select ${escapeHTML(item.title)}" ${selected.has(item.video_id) ? 'checked' : ''} ${item.unavailable ? 'disabled' : ''}>${thumb(item)}<div class="item-info"><div class="item-title" title="${escapeHTML(item.title)}">${escapeHTML(item.title)}</div><div class="item-meta">${escapeHTML(item.channel)}${item.duration ? ' · ' + duration(item.duration) : ''}</div></div>${item.unavailable ? '<span class="pill">Live / upcoming</span>' : saved ? '<span class="pill">Already saved</span>' : item.availability_note ? '<span class="pill">Check on download</span>' : ''}</div>`;
    }).join('');
  }
  const playlistSources = (preview.sources || []).filter(source => source.is_playlist && source.url.includes('/playlist?list='));
  $('#save-playlists').hidden = !playlistSources.length;
  $('#save-playlists').innerHTML = icon('bookmark') + (playlistSources.length > 1 ? `Save ${playlistSources.length} playlists` : 'Save playlist');
  const errors = preview.errors || [];
  $('#preview-warnings').hidden = !errors.length;
  $('#preview-warnings').innerHTML = errors.length ? `<details><summary>${errors.length} link${errors.length === 1 ? '' : 's'} could not be read. The other items are ready.</summary>${errors.map(error => `<p><strong>${escapeHTML(error.url)}</strong><br>${escapeHTML(error.error)}</p>`).join('')}</details>` : '';
  renderSelection();
}
function renderSelection() {
  if (!state || state.preview.status !== 'ready') return;
  const available = new Set(state.preview.items.filter(item => !item.unavailable).map(item => item.video_id));
  $('#selected-count').textContent = `${selected.size} selected`;
  $('#select-all').checked = selected.size > 0 && selected.size === available.size;
  $('#select-all').indeterminate = selected.size > 0 && selected.size < available.size;
  $('#add-downloads').disabled = !selected.size;
  $('#add-downloads span').textContent = `Download ${selected.size || ''} ${selected.size === 1 ? 'item' : 'items'}`;
  $('#preview-footnote').textContent = state.settings.skip_duplicates ? 'Already saved or queued? We’ll skip it.' : 'Repeat downloads will be saved as new copies.';
}
function emptyState(type, title, message, action = true) {
  return `<div class="empty-state"><div class="empty-icon">${icon(type)}</div><h3>${title}</h3><p>${message}</p>${action ? '<button class="secondary" data-go-download>Find your next favorite '+icon('arrow')+'</button>' : ''}</div>`;
}
function renderQueue() {
  const signature = JSON.stringify([state.jobs, state.paused, state.settings.concurrent_downloads, state.cooldown_seconds, state.overview, state.updater.status, filter]);
  if (signature === queueSignature) return;
  queueSignature = signature;
  const jobs = state.jobs;
  const counts = [jobs.filter(j => activeStates.has(j.status)).length, jobs.filter(j => j.status === 'done').length, jobs.filter(j => j.status === 'skipped').length, jobs.filter(j => ['error','interrupted'].includes(j.status)).length];
  $('#queue-stats').innerHTML = counts.map((count, i) => `<div class="stat"><strong>${count}</strong><span>${['In the queue','Downloaded','Duplicates skipped','Need attention'][i]}</span></div>`).slice(1).join('');
  renderOverview();
  $('#pause-queue').innerHTML = icon(state.paused ? 'play' : 'pause') + (state.paused ? 'Resume queue' : 'Pause queue');
  $('#paused-notice').hidden = !state.paused;
  const runningCount = jobs.filter(j => ['downloading','converting','retrying'].includes(j.status)).length;
  $('#parallel-status').textContent = `${runningCount} active · Up to ${state.settings.concurrent_downloads} downloads at once`;
  $('#retry-failed').hidden = !counts[3];
  $('#cooldown-notice').hidden = !state.cooldown_seconds;
  $('#cooldown-notice').textContent = `YouTube is limiting requests. New downloads will wait ${state.cooldown_seconds}s.`;
  $$('#queue-filters button').forEach(b => b.classList.toggle('active', b.dataset.filter === filter));
  const filtered = jobs.filter(j => filter === 'all' || (filter === 'active' ? activeStates.has(j.status) : filter === 'error' ? ['error','interrupted'].includes(j.status) : j.status === filter)).slice().reverse();
  if (!filtered.length) {
    $('#queue-items').innerHTML = emptyState('download', jobs.length ? 'Nothing in this view' : 'Your queue is taking a breather', jobs.length ? 'Your other downloads are in the All tab.' : 'Add a link and your downloads will appear here.', !jobs.length);
    return;
  }
  const names = {queued:'Queued', downloading:'Downloading', converting:'Finishing', retrying:'Retrying', done:'Saved', skipped:'Skipped', cancelled:'Cancelled', error:'Needs attention', interrupted:'Interrupted'};
  $('#queue-items').innerHTML = filtered.map(job => {
    const running = ['downloading','converting','retrying'].includes(job.status);
    const retry = ['error','cancelled','interrupted'].includes(job.status);
    return `<article class="item-row">${thumb(job)}<div class="item-info"><div class="item-title" title="${escapeHTML(job.title)}">${escapeHTML(job.title)}</div><div class="item-meta">${escapeHTML(qualityLabel(job))} · ${escapeHTML(job.channel)}</div>${running ? `<div class="progress-track ${job.progress === 0 || job.status === 'converting' ? 'busy' : ''}"><span style="width:${Math.max(0, Math.min(100, Number(job.progress) || 0))}%"></span></div>` : ''}<div class="item-meta ${job.status === 'error' ? 'error-detail' : ''}">${escapeHTML(job.detail)}</div></div><div class="item-actions"><span class="pill ${job.status}">${names[job.status]}</span>${activeStates.has(job.status) ? `<button class="icon-button" data-action="cancel" data-id="${job.id}" aria-label="Cancel ${escapeHTML(job.title)}">${icon('close')}</button>` : ''}${retry ? `<button class="icon-button" data-action="retry" data-id="${job.id}" aria-label="Retry ${escapeHTML(job.title)}">${icon('retry')}</button>` : ''}${job.status === 'done' ? `<button class="icon-button" data-open="${job.id}" aria-label="Show ${escapeHTML(job.title)} in folder">${icon('folder')}</button>` : ''}</div></article>`;
  }).join('');
}
function renderOverview() {
  const overview = state.overview;
  $('#overview-completed').textContent = `${overview.completed + overview.skipped} of ${overview.total} saved or skipped`;
  $('#overview-percent').textContent = Math.round(overview.progress) + '%';
  $('#overview-bar').style.width = overview.progress + '%';
  $('.overview-track').setAttribute('aria-valuenow', overview.progress);
  $('#overview-speed').textContent = overview.speed_bps >= 1048576 ? (overview.speed_bps / 1048576).toFixed(1) + ' MB/s' : overview.speed_bps > 0 ? Math.round(overview.speed_bps / 1024) + ' KB/s' : '0 MB/s';
  let eta = 'Calculating…';
  if (!overview.remaining) eta = overview.needs_attention ? 'Review failures' : overview.total ? 'Finished' : '—';
  else if (state.updater.status === 'installing') eta = 'Updating…';
  else if (state.paused && state.jobs.some(job => job.status === 'queued')) eta = 'Queue paused';
  else if (state.cooldown_seconds) eta = 'Waiting…';
  else if (overview.eta_seconds !== null) {
    const seconds = Math.max(1, overview.eta_seconds);
    eta = seconds >= 3600 ? `~${Math.floor(seconds / 3600)}h ${Math.ceil(seconds % 3600 / 60)}m` : seconds >= 60 ? `~${Math.ceil(seconds / 60)} min` : `~${Math.ceil(seconds)} sec`;
  }
  $('#overview-eta').textContent = eta;
  $('#overview-eta').title = 'Approximate queue time, based on current transfers and recently completed files. Conversion and connection delays may change it.';
  $('#overview-remaining').textContent = overview.remaining;
  const free = overview.disks.map(disk => disk.free).filter(value => value !== null);
  const disk = $('#overview-disk');
  disk.textContent = free.length ? sizeLabel(Math.min(...free)) : 'Unavailable';
  disk.title = overview.disks.map(disk => `${disk.folder}: ${disk.free === null ? 'Unavailable' : sizeLabel(disk.free) + ' free'}`).join('\n');
  disk.classList.toggle('low-space', free.length > 0 && Math.min(...free) < 1073741824);
}
function renderPlaylists() {
  $('#playlists-paused').hidden = !state.paused;
  const signature = JSON.stringify([state.playlists, state.preview.status, state.updater.status]);
  if (signature === playlistSignature) return;
  playlistSignature = signature;
  if (!state.playlists.length) {
    $('#saved-playlists').innerHTML = emptyState('bookmark', 'Your favorites, ready for next time', 'Check a playlist link, then choose Save playlist.');
    return;
  }
  const checking = state.preview.status === 'loading' || state.updater.status === 'installing';
  $('#saved-playlists').innerHTML = state.playlists.map(playlist => `<article class="saved-playlist"><div class="playlist-icon">${icon('bookmark')}</div><div class="item-info"><h2 class="playlist-title">${escapeHTML(playlist.title)}</h2><div class="item-meta">${escapeHTML(qualityLabel(playlist))} · ${playlist.item_count} items</div><div class="playlist-folder" title="${escapeHTML(playlist.folder)}">${escapeHTML(playlist.folder)}</div><p class="playlist-message ${playlist.sync_status === 'error' ? 'error-detail' : ''}">${escapeHTML(playlist.message)}${playlist.last_checked ? `<span class="last-checked">Checked ${escapeHTML(new Date(playlist.last_checked * 1000).toLocaleString())}</span>` : ''}</p></div><div class="playlist-actions"><button class="primary" data-playlist-action="download_new" data-playlist-id="${playlist.id}" ${checking ? 'disabled' : ''}>${icon('download')}${playlist.sync_status === 'loading' ? 'Checking…' : 'Download new'}</button><button class="icon-button" data-playlist-action="remove" data-playlist-id="${playlist.id}" aria-label="Remove saved playlist ${escapeHTML(playlist.title)}" ${playlist.sync_status === 'loading' ? 'disabled' : ''}>${icon('close')}</button></div></article>`).join('');
}
function renderUpdater() {
  const update = state.updater;
  const busy = ['checking','installing'].includes(update.status);
  const downloadsActive = state.jobs.some(job => ['downloading','converting','retrying'].includes(job.status));
  const blocked = downloadsActive || state.preview.status === 'loading';
  $('#check-update').disabled = busy;
  $('#check-update').textContent = update.status === 'checking' ? 'Checking…' : 'Check for updates';
  $('#install-update').hidden = update.status !== 'available';
  $('#install-update').disabled = busy || blocked;
  $('#update-version').textContent = update.current ? `Installed: ${update.current}${update.latest ? ' · Latest: ' + update.latest : ''}` : 'yt-dlp · Check to see the installed and latest versions.';
  $('#update-message').textContent = update.message + (update.status === 'available' && blocked ? ' Pause the queue and wait for active downloads and link checks to finish before installing.' : '');
  $('#update-message').classList.toggle('error-detail', update.status === 'error');
  $('#update-progress').hidden = update.status !== 'installing';
  $('#update-progress span').style.width = update.progress + '%';
}
function renderLibrary() {
  const search = $('#library-search').value.trim().toLowerCase();
  const signature = JSON.stringify([state.library, search]);
  if (signature === librarySignature) return;
  librarySignature = signature;
  const items = state.library.filter(i => (i.title + ' ' + i.channel).toLowerCase().includes(search)).slice().reverse();
  if (!items.length) {
    $('#library-items').innerHTML = emptyState('music', search ? 'No matches this time' : 'A collection starts with one favorite', search ? 'Try another title or channel.' : 'Your completed downloads will feel right at home here.', !search);
    return;
  }
  $('#library-items').innerHTML = items.map(item => `<article class="item-row">${thumb(item)}<div class="item-info"><div class="item-title" title="${escapeHTML(item.title)}">${escapeHTML(item.title)}</div><div class="item-meta">${escapeHTML(item.channel)} · ${qualityLabel(item)} · ${sizeLabel(item.size)}</div><div class="item-meta">Saved ${new Date(item.saved * 1000).toLocaleDateString()}${item.exists ? '' : ' · File moved or deleted'}</div></div><button class="icon-button" data-open="${item.id}" aria-label="Open folder for ${escapeHTML(item.title)}">${icon('folder')}</button></article>`).join('');
}
function render() {
  if (!state) return;
  const setup = $('#first-run');
  if (!state.setup_complete && !setup.open) {
    $('#setup-folder').value = state.settings.folder;
    $('#setup-error').hidden = true;
    setup.showModal();
  } else if (state.setup_complete && setup.open) {
    setup.close();
    $('#url').focus();
  }
  $('#queue-count').textContent = state.jobs.filter(j => activeStates.has(j.status)).length;
  $('#library-count').textContent = state.library.length;
  $('#playlist-count').textContent = state.playlists.length;
  $('#engine-status').innerHTML = '<span class="status-dot"></span>' + (state.health.ready ? 'Ready when you are' : 'Download engine needs setup');
  $('#engine-status').title = state.health.missing.join(', ');
  renderSettings();
  if (page === 'download') renderPreview();
  if (page === 'queue') renderQueue();
  if (page === 'library') renderLibrary();
  if (page === 'playlists') renderPlaylists();
  if (page === 'settings') renderUpdater();
}
async function refresh() {
  try {
    state = await api('state');
    $('#connection-error').hidden = true;
    render();
  } catch (error) {
    $('#connection-error').hidden = false;
    $('#connection-error').textContent = token ? 'Connection lost. Keep Offbeat open. Trying to reconnect…' : 'Open this page from the Offbeat app to connect securely.';
  }
}
$$('[data-page]').forEach(b => b.addEventListener('click', () => showPage(b.dataset.page)));
$('.brand').addEventListener('click', event => { event.preventDefault(); showPage('download'); });
$$('[data-mode]').forEach(b => b.addEventListener('click', handle(async () => { await saveSettings({mode:b.dataset.mode}); renderPreview(); })));
$('#quality').addEventListener('change', handle(async event => { await saveSettings({[state.settings.mode + '_quality']:event.target.value}); }));
$('#skip-duplicates').addEventListener('change', handle(async event => { await saveSettings({skip_duplicates:event.target.checked}); renderSelection(); }));
$('#destination').addEventListener('click', () => showPage('settings'));
$('#paste').addEventListener('click', handle(async () => {
  try { $('#url').value = await navigator.clipboard.readText(); $('#url').focus(); }
  catch { $('#url').focus(); toast('Press Ctrl+V to paste your link.'); }
}));
$('#link-form').addEventListener('submit', handle(async event => {
  event.preventDefault();
  $('#inspect').disabled = true;
  try { await api('preview', {url:$('#url').value, whole_playlist:$('#whole-playlist').checked}); dismissedId = null; await refresh(); }
  finally { if (state?.preview.status !== 'loading') $('#inspect').disabled = false; }
}));
$('#dismiss-preview').addEventListener('click', () => { dismissedId = state.preview.id; renderPreview(); });
$('#save-playlists').addEventListener('click', handle(async () => { await settingsPromise; const result = await api('playlists', {action:'save', preview_id:state.preview.id}); await refresh(); toast(`${result.saved} playlist${result.saved === 1 ? '' : 's'} saved. Find them in Playlists.`); }));
$('#preview-items').addEventListener('change', event => {
  const input = event.target.closest('[data-video]');
  if (!input) return;
  if (input.checked) selected.add(input.dataset.video); else selected.delete(input.dataset.video);
  $$('#preview-items [data-video]').filter(i => i.dataset.video === input.dataset.video).forEach(i => i.checked = input.checked);
  renderSelection();
});
$('#select-all').addEventListener('change', event => {
  selected = event.target.checked ? new Set(state.preview.items.filter(i => !i.unavailable).map(i => i.video_id)) : new Set();
  $$('#preview-items [data-video]').forEach(i => i.checked = selected.has(i.dataset.video));
  renderSelection();
});
$('#add-downloads').addEventListener('click', handle(async () => {
  const button = $('#add-downloads'); button.disabled = true;
  try {
    await settingsPromise;
    const result = await api('queue', {preview_id:state.preview.id, video_ids:[...selected]});
    await refresh(); showPage('queue');
    toast(`${result.added} added to queue${result.skipped ? ` · ${result.skipped} duplicates skipped` : ''}${state.paused ? ' · Resume the queue to start' : ''}`);
  } finally { button.disabled = false; }
}));
$('#queue-filters').addEventListener('click', event => { const b = event.target.closest('[data-filter]'); if (b) { filter = b.dataset.filter; renderQueue(); } });
$('#pause-queue').addEventListener('click', handle(async () => { await api('action', {action:state.paused ? 'resume' : 'pause'}); await refresh(); }));
$('#retry-failed').addEventListener('click', handle(async () => { await api('action', {action:'retry_failed'}); await refresh(); toast(state.paused ? 'Failed items queued. Resume the queue to start.' : 'Failed items queued for another try.'); }));
$('#clear-queue').addEventListener('click', handle(async () => { await api('action', {action:'clear'}); await refresh(); }));
document.addEventListener('click', handle(async event => {
  const action = event.target.closest('[data-action]');
  const open = event.target.closest('[data-open]');
  if (action) { await api('action', {action:action.dataset.action, id:action.dataset.id}); await refresh(); }
  if (open) await api('open-folder', {id:open.dataset.open});
  if (event.target.closest('[data-go-download]')) { showPage('download'); $('#url').focus(); }
}));
$('#library-search').addEventListener('input', () => renderLibrary());
$('#open-library').addEventListener('click', handle(() => api('open-folder', {})));
$('#browse-folder').addEventListener('click', handle(async () => {
  if (state?.desktop) {
    const button = $('#browse-folder'); button.disabled = true;
    try { const result = await api('choose-folder', {}); if (result.folder) $('#folder-path').value = result.folder; }
    finally { button.disabled = false; }
  } else { $('#folder-path').focus(); toast('Enter the full folder path. Browse is available in the desktop app.'); }
}));
$('#settings-form').addEventListener('submit', handle(async event => {
  event.preventDefault();
  await saveSettings({folder:$('#folder-path').value, skip_duplicates:$('#settings-skip').checked, concurrent_downloads:Number($('#concurrent-downloads').value)});
  $('#settings-feedback').textContent = 'Changes saved.';
  toast('Your preferences are saved.');
}));
$('#first-run').addEventListener('cancel', event => event.preventDefault());
$('#setup-browse').addEventListener('click', async () => {
  const button = $('#setup-browse');
  const confirm = $('#setup-confirm');
  $('#setup-error').hidden = true;
  if (!state?.desktop) { $('#setup-folder').focus(); return; }
  button.disabled = confirm.disabled = true;
  try {
    const result = await api('choose-folder', {});
    if (result.folder) $('#setup-folder').value = result.folder;
  } catch (error) {
    $('#setup-error').textContent = error.message;
    $('#setup-error').hidden = false;
  } finally { button.disabled = confirm.disabled = false; }
});
$('#setup-form').addEventListener('submit', async event => {
  event.preventDefault();
  $('#setup-error').hidden = true;
  $('#setup-confirm').disabled = $('#setup-browse').disabled = true;
  try {
    await saveSettings({folder:$('#setup-folder').value});
    await refresh();
  } catch (error) {
    $('#setup-error').textContent = error.message;
    $('#setup-error').hidden = false;
  } finally { $('#setup-confirm').disabled = $('#setup-browse').disabled = false; }
});
$('#saved-playlists').addEventListener('click', handle(async event => {
  const button = event.target.closest('[data-playlist-action]');
  if (!button) return;
  button.disabled = true;
  try { await api('playlists', {action:button.dataset.playlistAction, id:button.dataset.playlistId}); dismissedId = null; await refresh(); }
  finally { button.disabled = false; }
}));
$('#check-update').addEventListener('click', handle(async () => { await api('update', {action:'check'}); await refresh(); }));
$('#install-update').addEventListener('click', handle(async () => { await api('update', {action:'install'}); await refresh(); }));
(async function poll() { await refresh(); setTimeout(poll, 1200); })();
