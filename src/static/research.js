/* Same-origin UI for the existing MCP research workflow. */
const $ = selector => document.querySelector(selector);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const citation = number => `<button class="citation" data-source="${Number(number)}" aria-label="Kaynak ${Number(number)}">${Number(number)}</button>`;
const numberFormat = new Intl.NumberFormat('tr-TR', {maximumFractionDigits: 6});
let jobs = [], activeId = null, activeSource = null, toastTimer, polling = false, composing = false, initialized = false;
let saved = [];
try { saved = JSON.parse(localStorage.getItem('finsight-saved') || '[]'); if (!Array.isArray(saved)) saved = []; } catch {}
const current = () => jobs.find(job => job.id === activeId);
function notify(message) {
  clearTimeout(toastTimer); $('#toast').textContent = message; $('#toast').classList.add('visible');
  toastTimer = setTimeout(() => $('#toast').classList.remove('visible'), 5000);
}
async function api(path, options = {}) {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'İstek tamamlanamadı.');
  return body;
}
function proseHTML(text) {
  // Escape first; only our small formatting vocabulary becomes markup.
  return String(text || '').split(/\n\s*\n/).map(paragraph => {
    const safe = escapeHTML(paragraph).replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\[Source (\d+)\]/g, (_, id) => citation(id)).replace(/\n/g, '<br>');
    return `<p>${safe}</p>`;
  }).join('');
}
function renderHistory(term = '') {
  const filtered = jobs.filter(job => `${job.company} ${job.question}`.toLocaleLowerCase('tr').includes(term.toLocaleLowerCase('tr')));
  const items = filtered.map(job => `<button class="history-item ${job.id === activeId ? 'current' : ''}" data-job="${job.id}"><b>${escapeHTML(job.company || job.question)}</b><small>${escapeHTML(job.company ? job.question : new Date(job.created_at).toLocaleDateString('tr-TR'))}</small><span>${job.status === 'running' ? 'İşleniyor…' : job.status === 'failed' ? 'Tamamlanamadı' : 'Araştırma tamamlandı'}${saved.includes(job.id) ? ' · Kaydedildi' : ''}</span></button>`).join('');
  $('#history').innerHTML = items || '<p class="empty-search">Henüz araştırma yok.</p>';
  $('#search-results').innerHTML = items || '<p class="empty-search">Araştırma bulunamadı.</p>';
  $('#research-count').textContent = String(jobs.length).padStart(2, '0');
}
function setTab(name) {
  ['note', 'data'].forEach(tab => {
    const selected = name === tab;
    $(`#tab-${tab}`).classList.toggle('selected', selected);
    $(`#tab-${tab}`).setAttribute('aria-selected', String(selected));
    $(`#tab-${tab}`).tabIndex = selected ? 0 : -1;
    $(`#panel-${tab}`).hidden = !selected;
  });
}
function renderReport(id) {
  if (id) {
    composing = false;
    $('#new-research').hidden = true;
    $('.document-toolbar').hidden = false;
    $('#research-layout').hidden = false;
  }
  activeId = id;
  const job = current(), result = job?.result;
  $('#breadcrumb-company').textContent = job?.company || 'Çalışma alanı';
  $('#company-name').textContent = job?.company || 'FinSight Research';
  $('#company-icon').textContent = 'F';
  $('#ticker').textContent = '';
  $('#period').textContent = '';
  $('#report-title').textContent = job ? 'Araştırma notunuz.' : 'Bir soru ile başlayın.';
  $('#report-date').textContent = job?.elapsed_seconds != null ? `${job.elapsed_seconds} saniye` : 'SEC raporlarından kaynaklı araştırma';
  $('#original-question').textContent = job?.question || 'Şirket adı, ticker veya CIK ile yeni bir araştırma başlatın.';
  $('#note-number').textContent = job ? `FS—${job.id.slice(0, 6)}` : 'FS';
  const status = $('.source-status');
  status.textContent = !job ? 'Hazır' : job.status === 'running' ? 'Araştırılıyor…' : job.status === 'failed' ? 'Bağlantı hatası' : result?.supported ? 'Kontroller tamamlandı' : 'Doğrulama tamamlanamadı';
  $('#bookmark').disabled = !result;
  $('#bookmark').setAttribute('aria-pressed', String(saved.includes(id)));
  $('#bookmark span').textContent = saved.includes(id) ? 'Kaydedildi' : 'Kaydet';
  $('#export').disabled = !result?.markdown;
  const rows = result?.rows || [];
  $('#metric-count').textContent = rows.length;
  const labels = {revenue:'Yıllık gelir', cost_of_revenue:'Satışların maliyeti', operating_expenses:'Faaliyet giderleri'};
  $('#metrics').innerHTML = rows.slice(0, 3).map(row => {
    const scaled = row.Birim === 'USD' && Math.abs(row.Değer) >= 1e9;
    return `<div class="metric"><div class="metric-label">${escapeHTML(labels[row.Metrik] || row.Metrik)}${citation(row.Kaynak)}</div><div class="metric-value">${escapeHTML(new Intl.NumberFormat('tr-TR', {maximumFractionDigits:2}).format(scaled ? row.Değer / 1e9 : row.Değer))}<small>${scaled ? 'milyar' : ''}</small></div><div class="metric-unit">${escapeHTML(row.Şirket)} · ${escapeHTML(row.Birim)} · ${escapeHTML(row['Dönem sonu'])}</div></div>`;
  }).join('');
  $('#metrics').hidden = !rows.length;
  $('#panel-data').innerHTML = rows.length ? `<div class="table-scroll"><table class="data-table"><thead><tr><th>Şirket / Gösterge</th><th>Değer / Birim</th><th>Dönem</th><th>Kaynak</th></tr></thead><tbody>${rows.map(row => `<tr><td>${escapeHTML(row.Şirket)}<br>${escapeHTML(labels[row.Metrik] || row.Metrik)}</td><td>${escapeHTML(numberFormat.format(row.Değer))} ${escapeHTML(row.Birim)}</td><td>${escapeHTML(row['Mali yıl'])}<br>${escapeHTML(row['Dönem sonu'])}</td><td>${citation(row.Kaynak)}</td></tr>`).join('')}</tbody></table></div><p class="table-note">Araçlardan alınan kaynak verileri. Farklı şirket ve dönemler ayrı satırlarda gösterilir.</p>` : '<p>Bu araştırmada finansal veri kaydı bulunmuyor.</p>';
  if (!job) $('#panel-note').innerHTML = '<h2>Rakamların arkasındaki hikâyeyi araştırın.</h2><p>Yıllık finansal sonuçları karşılaştırın, raporlardaki riskleri inceleyin ve her bulguyu kaynağından takip edin.</p><button class="primary-button" data-action="new">Yeni araştırma</button>';
  else if (job.status === 'running') $('#panel-note').innerHTML = '<div class="analysis-callout" role="status"><h2>Kaynaklar inceleniyor.</h2><p>Şirket verileri hazırlanıyor, araştırma yürütülüyor ve yanıt kontrol ediliyor. İlk kez incelenen şirketlerde işlem daha uzun sürebilir. Bu sayfayı yenileseniz de işlem sunucuda devam eder.</p></div>';
  else if (job.status === 'failed') $('#panel-note').innerHTML = `<div class="analysis-callout" role="alert"><h2>Araştırma tamamlanamadı.</h2><p>${escapeHTML(job.error)}</p><button class="text-button" data-action="retry">Soruyu yeniden aç</button></div>`;
  else if (result.supported) $('#panel-note').innerHTML = proseHTML(result.prose) + (result.details ? `<details><summary>Veri ve rapor ayrıntıları</summary>${proseHTML(result.details)}</details>` : '') + '<p class="table-note">Otomatik kontroller hata kaçırabilir. İddiaları kaynak metinleriyle karşılaştırın.</p>';
  else $('#panel-note').innerHTML = `<div class="analysis-callout" role="alert"><h2>Yanıt doğrulanamadı.</h2><p>Doğrulanmış bir araştırma notu oluşturulmadı. Varsa kaynak verilerini Finansal veriler sekmesinde inceleyebilirsiniz.</p>${result.issues.length ? `<details><summary>Kontrol sonucu</summary>${result.issues.map(issue => `<p>${escapeHTML(issue)}</p>`).join('')}</details>` : ''}<button class="text-button" data-action="retry">Soruyu yeniden aç</button></div>`;
  if (result?.usage) $('#report-date').textContent += ` · Tahmini API maliyeti $${Number(result.usage.estimated_cost_usd || 0).toFixed(6)}`;
  showSource(result?.sources?.[0]?.id, false);
  renderHistory();
}
function showSource(id, reveal = true) {
  activeSource = id;
  const sources = current()?.result?.sources || [];
  if (reveal) { $('#research-layout').classList.remove('sources-hidden'); $('#research-layout').classList.add('sources-open'); }
  $('#source-tabs').innerHTML = sources.map(source => `<button class="${source.id === id ? 'selected' : ''}" data-source="${source.id}" aria-pressed="${source.id === id}">${source.id}</button>`).join('');
  const source = sources.find(source => source.id === id);
  $('#source-content').innerHTML = source ? sourceCard(source) : '<p class="empty-search">Araştırmanızın kaynakları burada görünecek.</p>';
  document.querySelectorAll('.citation').forEach(button => button.classList.toggle('active', Number(button.dataset.source) === id));
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
function openResearch(question = '') {
  composing = true;
  $('#new-research').hidden = false;
  $('.document-toolbar').hidden = true;
  $('#research-layout').hidden = true;
  $('#sidebar').classList.remove('open');
  $('#breadcrumb-company').textContent = 'Yeni araştırma';
  $('#question-input').value = question;
  $('#form-error').textContent = '';
  $('#question-input').focus();
}
function openDialog(id) {
  if (id === 'new') { openResearch(); return; }
  if (id === 'library') {
    const sources = jobs.flatMap(job => job.result?.sources || []);
    $('#library-content').innerHTML = sources.map(source => sourceCard(source)).join('') || '<p>Henüz araştırma kaynağı yok.</p>';
  }
  const dialog = $(`#${id}-dialog`); if (!dialog.open) dialog.showModal();
  $('#sidebar').classList.remove('open');
  if (id === 'search') { $('#search-input').value = ''; renderHistory(); $('#search-input').focus(); }
}
async function refresh() {
  if (polling) return;
  polling = true;
  try {
    const previous = current();
    jobs = await api('/api/research');
    $('#connection-status').textContent = 'Yerel çalışma alanı';
    if (!initialized) {
      initialized = true;
      if (!composing && jobs.length) activeId = jobs[0].id;
      else if (!jobs.length) openResearch();
    }
    const next = current();
    if (!composing && (!previous || previous.status !== next?.status)) renderReport(activeId);
    else renderHistory();
  } catch (error) { $('#connection-status').textContent = 'Sunucuya ulaşılamıyor'; }
  finally { polling = false; }
}
document.addEventListener('click', event => {
  const button = event.target.closest('button'); if (!button) return;
  if (button.hasAttribute('data-close')) { button.closest('dialog').close(); return; }
  if (button.dataset.job) { button.closest('dialog')?.close(); renderReport(button.dataset.job); setTab('note'); return; }
  if (button.dataset.source) { showSource(Number(button.dataset.source)); return; }
  if (button.dataset.prompt) { $('#question-input').value = button.dataset.prompt; $('#question-input').focus(); return; }
  const action = button.dataset.action;
  if (['new', 'search', 'library', 'settings'].includes(action)) openDialog(action);
  if (action === 'research') openDialog('search');
  if (action === 'retry') openResearch(current().question);
  if (action === 'menu') $('#sidebar').classList.toggle('open');
  if (action === 'sources') showSource(activeSource);
  if (action === 'close-sources') { $('#research-layout').classList.add('sources-hidden'); $('#research-layout').classList.remove('sources-open'); }
});
$('#new-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.target.querySelector('[type=submit]'); button.disabled = true;
  $('#form-error').textContent = '';
  try {
    const job = await api('/api/research', {method:'POST', headers:{'Content-Type':'application/json', 'X-FinSight-Request':'research'}, body:JSON.stringify({question:$('#question-input').value.trim()})});
    jobs.unshift(job); activeId = job.id; event.target.reset(); renderReport(job.id); setTab('note');
  } catch (error) { $('#form-error').textContent = error.message; }
  finally { button.disabled = false; }
});
$('#bookmark').addEventListener('click', () => {
  saved = saved.includes(activeId) ? saved.filter(id => id !== activeId) : [...saved, activeId];
  try { localStorage.setItem('finsight-saved', JSON.stringify(saved)); } catch { notify('Tarayıcı depolamasına yazılamadı.'); }
  renderReport(activeId);
});
$('#export').addEventListener('click', () => {
  const markdown = current()?.result?.markdown; if (!markdown) return;
  const url = URL.createObjectURL(new Blob([markdown], {type:'text/markdown;charset=utf-8'}));
  const link = document.createElement('a'); link.href = url; link.download = `FinSight-${activeId.slice(0, 8)}.md`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$('#tab-note').addEventListener('click', () => setTab('note'));
$('#tab-data').addEventListener('click', () => setTab('data'));
$('.report-tabs').addEventListener('keydown', event => {
  if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
  event.preventDefault(); const next = event.key === 'Home' ? 'note' : event.key === 'End' ? 'data' : $('#tab-note').getAttribute('aria-selected') === 'true' ? 'data' : 'note';
  setTab(next); $(`#tab-${next}`).focus();
});
$('#search-input').addEventListener('input', event => renderHistory(event.target.value));
$('#reading-mode').addEventListener('change', event => document.body.classList.toggle('reading', event.target.checked));
document.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && !document.querySelector('dialog[open]')) { event.preventDefault(); openDialog('search'); }
});
$('.top-date').textContent = new Date().toLocaleDateString('tr-TR', {day:'2-digit', month:'long', year:'numeric'});
renderReport(null);
refresh();
setInterval(refresh, 2500);
