(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let source = null;
  let clips = [];
  let aspect = 'vertical';
  let quality = '1080';
  let importing = false;
  let exporting = false;
  let previewEnd = null;
  let analyzing = false;
  let aiCandidates = [];

  const player = $('player');
  const fmt = (seconds, withHours = false) => {
    const s = Math.max(0, Math.floor(Number(seconds) || 0));
    const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60;
    return h || withHours ? [h, m, sec].map(n => String(n).padStart(2, '0')).join(':') :
      [m, sec].map(n => String(n).padStart(2, '0')).join(':');
  };
  const toSeconds = value => {
    const trimmed = String(value).trim();
    if (!/^\d+(?::\d{1,2}){0,2}(?:\.\d+)?$/.test(trimmed)) return NaN;
    const pieces = trimmed.split(':').map(Number);
    if (pieces.length > 1 && pieces.slice(1).some(n => n >= 60)) return NaN;
    let seconds = 0;
    for (const n of pieces) seconds = seconds * 60 + n;
    return seconds;
  };
  const escapeHtml = value => String(value).replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
  const notify = (message, kind = '') => {
    const el = $('sourceStatus');
    el.className = `notice-line ${kind}`;
    el.innerHTML = '<span class="mini-info">i</span><span></span>';
    el.lastChild.textContent = message;
  };
  const clipError = msg => {
    $('clipMessage').textContent = msg;
    $('clipMessage').classList.toggle('hidden', !msg);
  };
  async function parseResponse(response) {
    let payload;
    try { payload = await response.json(); } catch { throw new Error('Server mengembalikan respons tidak valid.'); }
    if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Proses gagal.');
    return payload;
  }

  const setTab = name => {
    $('tabYoutube').classList.toggle('active', name === 'youtube');
    $('tabUpload').classList.toggle('active', name === 'upload');
    $('youtubePane').classList.toggle('hidden', name !== 'youtube');
    $('uploadPane').classList.toggle('hidden', name !== 'upload');
    notify(name === 'youtube' ? 'Impor YouTube hanya untuk video yang Anda miliki atau punya izin penggunaan.' : 'Video diproses di server, dan hasilnya bisa diunduh ke HP.');
  };
  $('tabYoutube').addEventListener('click', () => setTab('youtube'));
  $('tabUpload').addEventListener('click', () => setTab('upload'));

  function updateVideo(s) {
    source = s;
    clips = [];
    previewEnd = null;
    $('placeholder').classList.add('hidden');
    player.classList.remove('hidden');
    player.src = `/api/sources/${encodeURIComponent(s.id)}/media`;
    player.load();
    $('videoBadge').textContent = 'Video siap ✓';
    $('sourceTitle').textContent = s.title;
    $('sourceMeta').textContent = `${s.origin === 'youtube' ? 'YouTube' : 'Upload lokal'} · ${s.width}×${s.height} · ${fmt(s.duration)}${s.heatmap_available ? ' · Most Replayed ✓' : ''}`;
    $('startTime').value = '00:00:00';
    $('endTime').value = fmt(Math.min(30, Math.floor(s.duration)), true);
    $('scrubber').disabled = false;
    $('scrubber').max = s.duration;
    $('scrubber').value = 0;
    $('clipTitle').value = 'Clip 01';
    $('resultsPanel').classList.add('hidden');
    $('aiResults').classList.add('hidden');
    $('aiWarnings').classList.add('hidden');
    $('aiProgressBox').classList.add('hidden');
    $('retentionStatus').textContent = s.heatmap_available ? '✓ Data YouTube Most Replayed ditemukan! Akan dipakai untuk menentukan momen yang sering diputar ulang.' : 'Most Replayed tidak tersedia; memakai prediksi audio/visual atau retensi CSV jika diunggah.';
    $('retentionFile').value = '';
    $('aiAnalyze').disabled = false;
    aiCandidates = [];
    renderClips();
    updateTimings();
    notify('Video berhasil dimuat. Silakan tentukan waktu potongan.', 'success');
  }
  const setImporting = value => {
    importing = value;
    $('youtubeButton').disabled = value;
    $('youtubeAuto').disabled = value;
    const auto = $('youtubeAuto').checked;
    $('youtubeButton').innerHTML = value ? '◌ Mengambil link YouTube…' :
      (auto ? '✦ Analisis dari Link &amp; Auto Clip <span>→</span>' : 'Ambil video <span>→</span>');
  };
  $('youtubeAuto').addEventListener('change', () => setImporting(false));
  $('youtubeForm').addEventListener('submit', async event => {
    event.preventDefault();
    if (importing) return;
    if (!$('rightsCheck').checked) { notify('Centang konfirmasi hak/izin video sebelum impor.', 'error'); return; }
    const url = $('youtubeUrl').value.trim();
    setImporting(true);
    notify('Mengambil video YouTube… Ini memerlukan koneksi internet.');
    try {
      // Web hosting: use a background job so cloud proxies do not time out.
      const response = await fetch('/api/imports/youtube', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,have_rights:true})});
      const queued = await parseResponse(response);
      let imported = null;
      for (let attempt = 0; attempt < 360; attempt++) {
        await sleep(1500);
        const status = await parseResponse(await fetch(`/api/imports/${encodeURIComponent(queued.import_id)}`));
        notify(status.message || 'Sedang mengambil video YouTube…');
        if (status.status === 'error') throw new Error(status.message || 'Impor gagal.');
        if (status.status === 'done') { imported = status.source; break; }
      }
      if (!imported) throw new Error('Impor terlalu lama. Coba link video yang lebih pendek.');
      updateVideo(imported);
      if ($('youtubeAuto').checked) {
        notify('✓ Video dari link berhasil diambil. Analisis momen menarik sedang berjalan…', 'success');
        $('aiPanel').scrollIntoView({behavior:'smooth',block:'start'});
        await analyzeCurrentSource();
      }
    } catch (err) { notify(err.message, 'error'); }
    finally { setImporting(false); }
  });
  async function uploadVideo(file) {
    if (!file || importing) return;
    if (file.size > 700 * 1024 * 1024) { notify('Ukuran file maksimal 700 MB.', 'error'); return; }
    const data = new FormData(); data.append('file', file);
    importing = true;
    notify(`Mengupload ${file.name}…`);
    try {
      const response = await fetch('/api/sources/upload', {method:'POST', body:data});
      updateVideo(await parseResponse(response));
    } catch (err) { notify(err.message, 'error'); }
    finally { importing = false; $('fileInput').value = ''; }
  }
  $('fileInput').addEventListener('change', event => uploadVideo(event.target.files[0]));
  const dz = $('dropzone');
  dz.addEventListener('click', () => $('fileInput').click());
  dz.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') {event.preventDefault(); $('fileInput').click();} });
  ['dragover','dragenter'].forEach(event => dz.addEventListener(event, e => {e.preventDefault();dz.classList.add('drag');}));
  ['dragleave','drop'].forEach(event => dz.addEventListener(event, e => {e.preventDefault();dz.classList.remove('drag');}));
  dz.addEventListener('drop', event => uploadVideo(event.dataTransfer.files[0]));

  function updateTimings() {
    const start = toSeconds($('startTime').value), end = toSeconds($('endTime').value);
    const d = end - start;
    $('clipLength').textContent = Number.isFinite(d) && d >= 0 ? `Durasi: ${fmt(d)}` : 'Durasi: —';
  }
  $('startTime').addEventListener('input', updateTimings);
  $('endTime').addEventListener('input', updateTimings);
  $('markStart').addEventListener('click', () => { if (!source) return clipError('Impor video terlebih dahulu.'); $('startTime').value=fmt(player.currentTime,true);updateTimings(); });
  $('markEnd').addEventListener('click', () => { if (!source) return clipError('Impor video terlebih dahulu.'); $('endTime').value=fmt(player.currentTime,true);updateTimings(); });
  $('scrubber').addEventListener('input', event => { if (source) {previewEnd=null;player.currentTime=Number(event.target.value);} });
  player.addEventListener('timeupdate', () => {
    $('timeReadout').innerHTML = `${fmt(player.currentTime)} <span>/</span> ${fmt(source?.duration || 0)}`;
    $('scrubber').value = String(player.currentTime);
    if (previewEnd !== null && player.currentTime >= previewEnd) {player.pause(); previewEnd=null;}
  });
  player.addEventListener('loadedmetadata', () => {if(source) $('timeReadout').innerHTML=`00:00 <span>/</span> ${fmt(source.duration)}`;});
  function renderClips() {
    const list = $('clipList');
    list.replaceChildren();
    if (!clips.length) {
      list.innerHTML = '<div class="empty-list"><span class="empty-list-icon">▤</span><strong>Belum ada clip</strong><span>Atur waktu di atas, lalu klik “Tambah clip”.</span></div>';
    } else {
      for (const [index, clip] of clips.entries()) {
        const wrapper = document.createElement('div'); wrapper.className='clip-item';
        wrapper.innerHTML = `<span class="clip-numeral">${String(index+1).padStart(2,'0')}</span><div class="clip-info"><strong>${escapeHtml(clip.title)}</strong><span>${fmt(clip.start)} – ${fmt(clip.end)} · ${fmt(clip.end-clip.start)}</span></div><div class="clip-actions"><button type="button" data-preview="${index}" title="Preview clip">▶</button><button type="button" class="delete" data-delete="${index}" title="Hapus clip">×</button></div>`;
        list.appendChild(wrapper);
      }
    }
    $('clipCount').textContent = String(clips.length);
    $('summaryCount').textContent = `${clips.length} video`;
    $('summaryLength').textContent = fmt(clips.reduce((t,c) => t+c.end-c.start,0));
    $('exportButton').disabled = !clips.length || exporting;
  }
  $('addClip').addEventListener('click', () => {
    clipError('');
    if (!source) return clipError('Impor video terlebih dahulu.');
    if (clips.length >= 10) return clipError('Maksimal 10 clip dalam satu ekspor.');
    const start = toSeconds($('startTime').value), end = toSeconds($('endTime').value);
    if (!Number.isFinite(start) || !Number.isFinite(end)) return clipError('Isi waktu dengan format HH:MM:SS, MM:SS, atau detik.');
    if (start < 0 || end > source.duration + 0.15) return clipError('Waktu harus berada dalam durasi video.');
    if (end-start < 0.5 || end-start > 180) return clipError('Panjang clip minimal 0,5 detik dan maksimal 180 detik.');
    const title = $('clipTitle').value.trim();
    if (!title) return clipError('Nama clip tidak boleh kosong.');
    clips.push({title,start,end});
    $('clipTitle').value=`Clip ${String(clips.length+1).padStart(2,'0')}`;
    renderClips();
  });
  $('clipList').addEventListener('click', async event => {
    const del = event.target.closest('[data-delete]');
    if (del) {clips.splice(Number(del.dataset.delete),1);renderClips();return;}
    const preview = event.target.closest('[data-preview]');
    if (preview && source) {
      const c = clips[Number(preview.dataset.preview)];
      player.currentTime=c.start;previewEnd=c.end;
      try {await player.play();} catch {clipError('Klik tombol play pada video untuk memutar preview.');}
    }
  });
  $('clearClips').addEventListener('click', () => {clips=[];renderClips();clipError('');});

  document.querySelectorAll('[data-aspect]').forEach(button => button.addEventListener('click', () => {
    aspect=button.dataset.aspect;
    document.querySelectorAll('[data-aspect]').forEach(b=>b.classList.toggle('selected',b===button));
    $('framingBlock').classList.toggle('hidden',aspect==='original');
    $('qualityBlock').classList.toggle('hidden',aspect==='original');
  }));
  document.querySelectorAll('[data-quality]').forEach(button=>button.addEventListener('click',()=>{
    quality=button.dataset.quality;
    document.querySelectorAll('[data-quality]').forEach(b=>b.classList.toggle('selected',b===button));
  }));
  const setExporting = value => {exporting=value;renderClips();$('exportButton').innerHTML=value?'<span>◌</span> Sedang mengekspor…':'<span>✦</span> Export Semua Clip <span>↗</span>';};
  const sleep = ms => new Promise(resolve=>setTimeout(resolve,ms));
  async function exportClips() {
    if (!source || !clips.length || exporting) return;
    setExporting(true);
    $('resultsPanel').classList.remove('hidden');
    $('downloads').replaceChildren();
    $('exportStatus').textContent='Mengirim clip ke engine FFmpeg…';
    $('exportProgress').style.width='4%';
    $('resultsPanel').scrollIntoView({behavior:'smooth',block:'nearest'});
    try {
      const framing = document.querySelector('input[name="framing"]:checked')?.value || 'crop';
      const response = await fetch('/api/exports', {method:'POST', headers:{'Content-Type':'application/json'},body:JSON.stringify({source_id:source.id, clips,aspect,framing,quality})});
      const result=await parseResponse(response);
      let job;
      for (let attempts=0; attempts<240; attempts++) {
        await sleep(2000);
        const resp=await fetch(`/api/jobs/${encodeURIComponent(result.job_id)}`);
        job=await parseResponse(resp);
        $('exportStatus').textContent=job.message;
        $('exportProgress').style.width=`${Math.max(4,job.progress||0)}%`;
        if (job.status==='done' || job.status==='error') break;
      }
      if (job?.status==='done') {
        const dl=document.createElement('div');dl.className='download-list';
        for (const file of job.files) {
          const link=document.createElement('a');link.className='download-link';link.href=file.url;link.setAttribute('download',file.name);
          link.innerHTML=`<span>▶ ${escapeHtml(file.name)}</span><small>↓ ${(file.size/1024/1024).toFixed(1)} MB</small>`;
          dl.appendChild(link);
        }
        const all=document.createElement('a');all.href=job.zip_url;all.className='download-link zip-link';all.setAttribute('download','semua-clips.zip');all.textContent='↓ Download semua clip (.ZIP)';dl.appendChild(all);
        $('downloads').appendChild(dl);
      } else { throw new Error(job?.message || 'Proses ekspor terlalu lama atau terhenti.'); }
    } catch(err) {$('exportStatus').textContent=`Gagal: ${err.message}`;}
    finally {setExporting(false);}
  }
  $('exportButton').addEventListener('click', exportClips);

  // AI AutoClip: rank candidate intervals, add them to the trim list, optionally auto-export.
  $('retentionFile').addEventListener('change', async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!source) {
      $('retentionStatus').textContent = 'Impor video terlebih dahulu.';
      event.target.value = '';
      return;
    }
    const sourceId = source.id;
    if (file.size > 1024*1024) {
      $('retentionStatus').textContent = 'CSV terlalu besar (maksimal 1 MB).';
      event.target.value = '';
      return;
    }
    const form = new FormData(); form.append('file', file);
    $('retentionStatus').textContent = 'Membaca data retensi…';
    try {
      const response = await fetch(`/api/sources/${encodeURIComponent(sourceId)}/retention`, {method:'POST',body:form});
      const result = await parseResponse(response);
      if (source?.id === sourceId) $('retentionStatus').textContent = `✓ ${result.points} titik retensi terpasang untuk video ini. Analisis akan memakai data channel asli.`;
    } catch (e) { $('retentionStatus').textContent = `Gagal impor retensi: ${e.message}`; }
    finally {event.target.value='';}
  });

  const aiLabels = {'retention+whisper':'Retensi asli + AI transkrip', 'retention+signals':'Retensi asli + sinyal video',
                    'whisper+signals':'AI Whisper + sinyal video', 'signals':'Sinyal audio + visual (tanpa transkrip AI)',
                    'heatmap+whisper':'YouTube Most Replayed + AI transkrip', 'heatmap+signals':'YouTube Most Replayed + sinyal video',
                    'retention+heatmap':'Retensi channel + Most Replayed', 'retention+heatmap+whisper':'Retensi + Most Replayed + AI Whisper'};

  function renderAiResults(result) {
    aiCandidates = result.clips || [];
    $('aiResults').classList.remove('hidden');
    $('aiMethod').textContent = aiLabels[result.method] || 'Analisis video';
    $('aiWarnings').classList.toggle('hidden', !(result.warnings || []).length);
    $('aiWarnings').textContent = (result.warnings || []).join(' • ');
    const list = $('aiSuggestions'); list.replaceChildren();
    for (const [idx, item] of aiCandidates.entries()) {
      const el = document.createElement('div'); el.className = 'ai-suggestion';
      const reasons = (item.reasons || []).map(escapeHtml).join(' · ');
      el.innerHTML = `<div class="ai-suggestion-header"><strong>#${idx+1} · ${fmt(item.start)} – ${fmt(item.end)}</strong><span class="ai-score">Skor ${item.score}/100</span></div>
        <div class="ai-score-track"><div class="ai-score-fill" style="width:${Math.min(100,Math.max(0,item.score))}%"></div></div>
        <div class="ai-suggestion-meta">${reasons}${item.retention_signal !== null ? ` · <span>Indeks retensi ${item.retention_signal}/100</span>` : ''}${item.replay_signal !== null ? ` · <span>Intensitas replay ${item.replay_signal}/100</span>` : ''}</div>
        ${item.excerpt ? `<blockquote>${escapeHtml(item.excerpt)}</blockquote>` : ''}
        <div class="ai-suggestion-actions"><button type="button" data-aipreview="${idx}">▶ Preview</button><button type="button" data-aiadd="${idx}">＋ Masukkan clip</button></div>`;
      list.appendChild(el);
    }
  }

  $('aiSuggestions').addEventListener('click', async event => {
    const preview = event.target.closest('[data-aipreview]');
    const add = event.target.closest('[data-aiadd]');
    if (preview && source) {
      const c = aiCandidates[Number(preview.dataset.aipreview)];
      if (!c) return;
      player.currentTime = c.start; previewEnd = c.end;
      try {await player.play();} catch {clipError('Tekan play pada video untuk melihat preview.');}
    }
    if (add && source) {
      const c = aiCandidates[Number(add.dataset.aiadd)];
      if (!c) return;
      if (clips.length >= 10) return clipError('Maksimal 10 clip per ekspor.');
      clips.push({title:c.title,start:c.start,end:c.end});
      renderClips();
      clipError('');
    }
  });

  async function analyzeCurrentSource() {
    if (!source || analyzing || exporting) return;
    const sourceId=source.id;
    analyzing=true;
    $('aiAnalyze').disabled=true;
    $('aiAnalyze').textContent='◌ AI sedang menganalisis video…';
    $('aiResults').classList.add('hidden');
    $('aiWarnings').classList.add('hidden');
    $('aiProgressBox').classList.remove('hidden');
    $('aiStage').textContent='Memulai analisis…';
    $('aiProgressBar').style.width='1%';
    $('aiPercent').textContent='1%';
    try {
      const response=await fetch('/api/analyses', {method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({source_id:sourceId,clip_length:Number($('aiDuration').value),max_clips:Number($('aiCount').value),use_speech:$('aiSpeech').checked})});
      const job=await parseResponse(response);
      let result=null;
      for(let attempt=0;attempt<1800;attempt++) {
        await sleep(1500);
        if(source?.id!==sourceId) throw new Error('Video telah berubah selama analisis.');
        const status=await parseResponse(await fetch(`/api/analyses/${encodeURIComponent(job.analysis_id)}`));
        $('aiStage').textContent=status.message;
        $('aiProgressBar').style.width=`${Math.max(1,status.progress||0)}%`;
        $('aiPercent').textContent=`${Math.max(1,status.progress||0)}%`;
        if(status.status==='error') throw new Error(status.message || 'Analisis gagal.');
        if(status.status==='done') {result=status.result;break;}
      }
      if(!result) throw new Error('Analisis belum selesai. Coba lagi atau gunakan mode tanpa transkrip.');
      if(!result.clips.length) throw new Error('Tidak ada potongan yang cocok. Gunakan video lebih panjang.');
      renderAiResults(result);
      clips = result.clips.slice(0,10).map(c=>({title:c.title,start:c.start,end:c.end}));
      renderClips();
      clipError('');
      $('aiStage').textContent = `${clips.length} momen terpilih. ${$('aiAutoExport').checked ? 'Membuat MP4 otomatis…' : 'Klik Ekspor Semua Clip jika sudah sesuai.'}`;
      if($('aiAutoExport').checked) await exportClips();
    } catch(err) {
      $('aiStage').textContent=`Gagal: ${err.message}`;
      $('aiWarnings').classList.remove('hidden');
      $('aiWarnings').textContent=err.message;
    } finally {
      analyzing=false;
      $('aiAnalyze').textContent='✦ Analisis & Auto-Clip Video →';
      $('aiAnalyze').disabled=!source;
    }
  }
  $('aiAnalyze').addEventListener('click', analyzeCurrentSource);

  const navigate = view => {
    $('studioPage').classList.toggle('hidden',view!=='studio');
    $('helpPage').classList.toggle('hidden',view!=='help');
    $('navStudio').classList.toggle('active',view==='studio');
    $('navHelp').classList.toggle('active',view==='help');
    window.scrollTo({top:0,behavior:'smooth'});
  };
  $('navStudio').addEventListener('click',()=>navigate('studio'));
  $('navHelp').addEventListener('click',()=>navigate('help'));
  $('backStudio').addEventListener('click',()=>navigate('studio'));
  fetch('/api/health').then(parseResponse).then(result => {
    $('engineStatus').textContent=result.ffmpeg ? 'Engine FFmpeg siap' : 'FFmpeg belum tersedia';
    $('statusDot').classList.toggle('bad',!result.ffmpeg);
    if (!result.ffmpeg) notify('FFmpeg belum terpasang. Ikuti instruksi README untuk mengaktifkan ekspor.', 'error');
    if (!result.youtube) notify('yt-dlp belum terpasang. Impor YouTube belum tersedia; upload lokal tetap bisa digunakan.','error');
  }).catch(()=>{$('engineStatus').textContent='Server tidak tersedia';$('statusDot').classList.add('bad');});
  renderClips();
  updateTimings();
})();
