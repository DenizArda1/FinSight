/* Persistent conversations; evidence and citations belong to an individual reply. */
const $ = selector => document.querySelector(selector);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const citation = id => `<button class="citation" data-source="${Number(id)}" aria-label="Kaynak ${Number(id)}">${Number(id)}</button>`;
const numberFormat = new Intl.NumberFormat('tr-TR', {maximumFractionDigits:6});
let jobs = [], conversationId = null, sourceJobId = null, polling = false, submitting = false, deleting = false, initialized = false, revision = 0;
const drafts = new Map();
let lastRender = '';
function conversationJobs() {
  return jobs.filter(job => job.conversation_id === conversationId).slice().reverse();
}
function rememberSelection() {
  try { localStorage.setItem('finsight-conversation', conversationId || ''); } catch {}
}
async function api(path, options = {}) {
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'İstek tamamlanamadı.');
  return result;
}
function proseHTML(text) {
  return String(text || '').split(/\n\s*\n/).map(paragraph => `<p>${escapeHTML(paragraph)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\[Source (\d+)\]/g, (_, id) => citation(id)).replace(/\n/g, '<br>')}</p>`).join('');
}
function conversations() {
  const groups = new Map();
  for (const job of jobs.slice().reverse()) {
    if (!groups.has(job.conversation_id)) groups.set(job.conversation_id, {id:job.conversation_id, title:job.question, messages:[]});
    groups.get(job.conversation_id).messages.push(job);
  }
  return [...groups.values()].sort((a,b) => b.messages.at(-1).created_at.localeCompare(a.messages.at(-1).created_at));
}
function renderHistory() {
  const groups = conversations();
  const search = $('#search-input').value.toLocaleLowerCase('tr');
  const markup = group => {
    const busy = group.messages.some(job => job.status === 'running');
    return `<div class="history-row"><button class="history-item ${group.id === conversationId ? 'current' : ''}" data-conversation="${escapeHTML(group.id)}" ${group.id === conversationId ? 'aria-current="page"' : ''}><b>${escapeHTML(group.title)}</b><small>${group.messages.length} mesaj · ${new Date(group.messages.at(-1).created_at).toLocaleDateString('tr-TR')}</small>${busy ? '<span>Yanıt hazırlanıyor…</span>' : ''}</button><button class="history-delete" data-delete-conversation="${escapeHTML(group.id)}" aria-label="${escapeHTML(group.title)} konuşmasını sil" title="${busy ? 'Yanıt tamamlandıktan sonra silebilirsiniz' : 'Konuşmayı sil'}" ${busy || submitting || deleting ? 'disabled' : ''}><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/></svg></button></div>`;
  };
  $('#history').innerHTML = groups.map(markup).join('') || '<p class="empty-search">İlk konuşmanı başlat.</p>';
  $('#search-results').innerHTML = groups.filter(group => group.messages.some(job => job.question.toLocaleLowerCase('tr').includes(search))).map(markup).join('') || '<p class="empty-search">Konuşma bulunamadı.</p>';
  $('#research-count').textContent = groups.length;
}
function financialTable(rows) {
  if (!rows?.length) return '';
  return `<details class="message-details"><summary>Finansal veriler · ${rows.length}</summary><div class="table-scroll"><table class="data-table"><thead><tr><th>Şirket / Metrik</th><th>Değer</th><th>Dönem</th><th>Kaynak</th></tr></thead><tbody>${rows.map(row => `<tr><td>${escapeHTML(row.Şirket)}<br>${escapeHTML(row.Metrik)}</td><td>${escapeHTML(numberFormat.format(row.Değer))} ${escapeHTML(row.Birim)}</td><td>${escapeHTML(row['Dönem sonu'])}</td><td>${citation(row.Kaynak)}</td></tr>`).join('')}</tbody></table></div></details>`;
}
function messageHTML(job) {
  let body;
  const result = job.result;
  if (job.status === 'running') body = '<p class="pending-message" role="status"><span class="status-dot"></span>Kaynakları inceliyorum, yanıtı hazırlıyorum…</p>';
  else if (job.status === 'failed') body = `<p role="alert">${escapeHTML(job.error)}</p><button class="text-button" data-retry="${job.id}">Yeniden dene</button>`;
  else if (!result?.supported) body = `<p>Bu yanıtın kaynaklarla tutarlılığı doğrulanamadı. Kaynak verilerini aşağıda inceleyebilir veya yeniden deneyebilirsin.</p>${financialTable(result?.rows)}<button class="text-button" data-retry="${job.id}">Yeniden dene</button>`;
  else body = proseHTML(result.prose) + financialTable(result.rows) + (result.details ? `<details class="message-details"><summary>Rapor ayrıntıları</summary>${proseHTML(result.details)}</details>` : '');
  if (result?.supported && result.coverage?.status === 'partial') {
    body = '<p class="table-note"><strong>Kısmi yanıt</strong> · İstenen bilgilerin bir kısmı kaynaklarla tamamlanamadı.</p>' + body;
  } else if (result?.supported && result.coverage?.status === 'unknown') {
    body = '<p class="table-note">Yanıtın araştırma kapsamı kontrol edilemedi.</p>' + body;
  }
  const actions = result ? `<div class="message-actions">${result.sources.length ? `<button class="text-button" data-sources="${job.id}">Kaynaklar · ${result.sources.length}</button>` : ''}${result.markdown ? `<button class="text-button" data-export="${job.id}">Markdown indir</button>` : ''}<small>${job.elapsed_seconds ?? ''} sn${result.usage ? ` · $${Number(result.usage.estimated_cost_usd || 0).toFixed(6)}` : ''}</small></div>` : '';
  return `<section class="chat-turn" data-message="${job.id}"><div class="user-message"><span class="sr-only">Sen:</span>${escapeHTML(job.question).replace(/\n/g, '<br>')}</div><article class="assistant-message"><div class="assistant-label">FinSight</div>${body}${actions}</article></section>`;
}
function updateSubmit() {
  $('#new-form [type=submit]').disabled = submitting || deleting || jobs.some(job => job.status === 'running') || !$('#question-input').value.trim();
}
function renderChat(forceScroll = false) {
  const messages = conversationJobs();
  const signature = JSON.stringify(messages.map(job => [job.id, job.status]));
  const nearBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 180;
  if (signature !== lastRender) {
    $('#chat-messages').innerHTML = messages.map(messageHTML).join('');
    lastRender = signature;
    if (forceScroll || nearBottom) requestAnimationFrame(() => window.scrollTo({top:document.documentElement.scrollHeight, behavior:'auto'}));
  }
  $('#chat-intro').hidden = messages.length > 0;
  $('.suggested-questions').hidden = messages.length > 0;
  $('#chat-main').classList.toggle('has-messages', messages.length > 0);
  $('#breadcrumb-company').textContent = messages[0]?.question || 'Yeni konuşma';
  updateSubmit();
  renderHistory();
}
function selectConversation(id) {
  drafts.set(conversationId || 'new', $('#question-input').value);
  conversationId = id;
  initialized = true;
  rememberSelection();
  $('#question-input').value = drafts.get(id || 'new') || '';
  $('#form-error').textContent = '';
  $('#sidebar').classList.remove('open');
  closeSources();
  lastRender = '';
  renderChat(true);
  $('#question-input').focus();
}
async function deleteConversation(id) {
  if (submitting || deleting || jobs.some(job => job.conversation_id === id && job.status === 'running')) return;
  if (!window.confirm('Bu konuşma ve içindeki tüm mesajlar geçmişten silinsin mi?')) return;
  deleting = true;
  revision += 1;
  updateSubmit();
  renderHistory();
  try {
    await api(`/api/conversations/${encodeURIComponent(id)}`, {method:'DELETE', headers:{'X-FinSight-Request':'research'}});
    jobs = jobs.filter(job => job.conversation_id !== id);
    if (sourceJobId && !jobs.some(job => job.id === sourceJobId)) { closeSources(); sourceJobId = null; }
    if (conversationId === id) selectConversation(null);
    drafts.delete(id);
    renderChat();
  } catch (error) { window.alert(error.message); }
  finally { deleting = false; revision += 1; updateSubmit(); renderHistory(); }
}
function closeSources() {
  $('#research-layout').classList.add('sources-hidden');
  $('#research-layout').classList.remove('sources-open');
}
function showSource(jobId, sourceId) {
  const job = jobs.find(job => job.id === jobId);
  const sources = job?.result?.sources || [];
  const selected = sources.find(source => source.id === sourceId) || sources[0];
  if (!selected) return;
  sourceJobId = jobId;
  $('#research-layout').classList.remove('sources-hidden');
  $('#research-layout').classList.add('sources-open');
  $('#source-tabs').innerHTML = sources.map(source => `<button data-source="${source.id}" aria-pressed="${source.id === selected.id}" class="${source.id === selected.id ? 'selected' : ''}">${source.id}</button>`).join('');
  $('#source-content').innerHTML = sourceCard(selected);
}
function sourceLinks(text) {
  const links = [...new Set(String(text).match(/https:\/\/(?:www\.sec\.gov|www\.federalreserve\.gov|api\.bls\.gov)\/[^\s|<>"']+/g) || [])];
  return links.map(url => `<a class="source-open" href="${escapeHTML(url)}" target="_blank" rel="noopener noreferrer">Kaynağı aç ↗</a>`).join('');
}
function sourceCard(source) {
  const references = String(source.reference || '').split('\n').filter(Boolean);
  return references.map(reference => {
    const parts = reference.replace(/\[Source \d+\]\s*/, '').split(' | ').map(part => part.trim());
    const company = parts[0] || 'SEC EDGAR';
    const form = parts.find(part => /^(10-K|10-Q|8-K|20-F|40-F)(\/A)?$/.test(part)) || (company === 'BLS' ? 'Ekonomik veri' : company === 'Federal Reserve' ? 'Para politikası açıklaması' : 'SEC raporu');
    const year = parts.find(part => /^FY\d{4}$/.test(part)) || parts.find(part => /^\d{4}-\d{2}(-\d{2})?$/.test(part)) || '';
    const section = parts.find(part => /^(Item|Part|Primary document|EX-99|Monetary policy)\b/i.test(part));
    return `<div class="source-card"><span class="small-label">KAYNAK ${source.id}</span><h3>${escapeHTML(company)}</h3><p>${escapeHTML([form, year].filter(Boolean).join(' · '))}</p><div class="source-location"><span>Rapor içindeki konum</span><strong>${escapeHTML(section || 'Bölüm bilgisi mevcut değil')}</strong><small>Bu kaynak için sabit sayfa numarası mevcut değil.</small></div>${sourceLinks(reference)}</div>`;
  }).join('');
}
function openDialog(name) {
  if (name === 'library') $('#library-content').innerHTML = jobs.flatMap(job => job.result?.sources || []).map(sourceCard).join('') || '<p>Henüz kaynak yok.</p>';
  const dialog = $(`#${name}-dialog`);
  if (!dialog.open) dialog.showModal();
}
async function refresh() {
  if (polling || submitting || deleting) return;
  polling = true;
  try {
    const startedRevision = revision;
    const incoming = await api('/api/research');
    if (submitting || deleting || revision !== startedRevision) return;
    jobs = incoming;
    $('#connection-status').textContent = 'Yerel çalışma alanı';
    if (!initialized) {
      initialized = true;
      let stored;
      try { stored = localStorage.getItem('finsight-conversation'); } catch {}
      conversationId = stored && jobs.some(job => job.conversation_id === stored) ? stored : null;
    }
    renderChat();
  } catch { $('#connection-status').textContent = 'Sunucuya ulaşılamıyor'; }
  finally { polling = false; }
}
$('#new-form').addEventListener('submit', async event => {
  event.preventDefault();
  const question = $('#question-input').value.trim();
  if (!question || submitting || deleting || jobs.some(job => job.status === 'running')) return;
  submitting = true;
  revision += 1;
  updateSubmit();
  const destination = conversationId;
  $('#form-error').textContent = '';
  try {
    const payload = {question};
    if (destination) payload.conversation_id = destination;
    const job = await api('/api/research', {method:'POST', headers:{'Content-Type':'application/json','X-FinSight-Request':'research'}, body:JSON.stringify(payload)});
    jobs.unshift(job);
    drafts.delete(destination || 'new');
    // Do not switch the user back if they opened another conversation while sending.
    if (conversationId === destination) {
      conversationId = job.conversation_id;
      rememberSelection();
      $('#question-input').value = '';
      renderChat(true);
    } else renderHistory();
  } catch (error) { $('#form-error').textContent = error.message; }
  finally { submitting = false; updateSubmit(); }
});
$('#question-input').addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    if (!$('#new-form [type=submit]').disabled) $('#new-form').requestSubmit();
  }
});
$('#question-input').addEventListener('input', updateSubmit);
document.addEventListener('click', event => {
  const button = event.target.closest('button');
  if (!button) return;
  if (button.hasAttribute('data-close')) { button.closest('dialog').close(); return; }
  if (button.dataset.deleteConversation) { deleteConversation(button.dataset.deleteConversation); return; }
  if (button.dataset.conversation) { button.closest('dialog')?.close(); selectConversation(button.dataset.conversation); return; }
  if (button.dataset.source) { showSource(button.closest('[data-message]')?.dataset.message || sourceJobId, Number(button.dataset.source)); return; }
  if (button.dataset.sources) { showSource(button.dataset.sources); return; }
  if (button.dataset.retry) {
    const job = jobs.find(job => job.id === button.dataset.retry);
    $('#question-input').value = job.question; updateSubmit(); $('#question-input').focus(); return;
  }
  if (button.dataset.export) {
    const job = jobs.find(job => job.id === button.dataset.export);
    if (!job?.result?.markdown) return;
    const url = URL.createObjectURL(new Blob([job.result.markdown], {type:'text/markdown;charset=utf-8'}));
    const link = document.createElement('a'); link.href = url; link.download = `FinSight-${job.id.slice(0,8)}.md`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000); return;
  }
  if (button.dataset.prompt) { $('#question-input').value = button.dataset.prompt; updateSubmit(); $('#question-input').focus(); return; }
  const action = button.dataset.action;
  if (action === 'new') selectConversation(null);
  if (action === 'research' || action === 'search') openDialog('search');
  if (action === 'library' || action === 'settings') openDialog(action);
  if (action === 'menu') $('#sidebar').classList.toggle('open');
  if (action === 'close-sources') closeSources();
});
$('#search-input').addEventListener('input', renderHistory);
$('#reading-mode').addEventListener('change', event => document.body.classList.toggle('reading', event.target.checked));
document.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && !document.querySelector('dialog[open]')) { event.preventDefault(); openDialog('search'); }
});
$('.top-date').textContent = new Date().toLocaleDateString('tr-TR', {day:'2-digit',month:'long',year:'numeric'});
renderChat();
refresh();
setInterval(refresh, 2500);
