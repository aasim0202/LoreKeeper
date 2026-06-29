// LoreKeeper 3.0 — Application Logic
// ═══════════════════════════════════════════════════════

(function() {
  'use strict';

  // ── STATE ────────────────────────────────────────
  const LS_KEYS = {
    kanban: 'lk_kanban',
    stats: 'lk_stats',
    queries: 'lk_queries',
    settings: 'lk_settings'
  };

  function loadState(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) || fallback; }
    catch { return fallback; }
  }
  function saveState(key, val) { localStorage.setItem(key, JSON.stringify(val)); }

  let kanbanData = loadState(LS_KEYS.kanban, { todo: [], doing: [], done: [] });
  let statsData = loadState(LS_KEYS.stats, { queries: 0, actions: 0, sources: 0, completed: 0 });
  let recentQueries = loadState(LS_KEYS.queries, []);
  let settings = loadState(LS_KEYS.settings, {
    url: 'http://127.0.0.1:8080/discord-bot-receiver',
    apiKey: '',
    enableJina: false
  });

  // ── DOM REFS ─────────────────────────────────────
  const $ = id => document.getElementById(id);
  const chatHistory = $('chat-history');
  const chatInput = $('chat-input');
  const sendBtn = $('send-btn');
  const typingIndicator = $('typing-indicator');

  // ── PAGE ROUTING ─────────────────────────────────
  document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', () => {
      document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
      document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
      link.classList.add('active');
      $('page-' + link.dataset.page).classList.add('active');
      if (link.dataset.page === 'tasks') renderKanban();
      if (link.dataset.page === 'insights') renderInsights();
      if (link.dataset.page === 'settings') loadSettings();
      if (link.dataset.page === 'memory') loadMemory();
    });
  });

  // ── CHAT ─────────────────────────────────────────
  function scrollToBottom() { chatHistory.scrollTop = chatHistory.scrollHeight; }

  function appendUserMessage(text) {
    const row = document.createElement('div');
    row.className = 'message-row user';
    row.innerHTML = `<div class="bubble user">${escapeHtml(text)}</div>`;
    chatHistory.appendChild(row);
    scrollToBottom();
  }

  function appendAIMessage(reply, actionItems, sources) {
    const row = document.createElement('div');
    row.className = 'message-row ai';
    const bubble = document.createElement('div');
    bubble.className = 'bubble ai';

    const formatted = escapeHtml(reply).replace(/\n/g, '<br>');
    bubble.innerHTML = `<p>${formatted}</p>`;

    // Action items checklist
    if (actionItems && actionItems.length > 0) {
      const container = document.createElement('div');
      container.className = 'action-items-container';
      actionItems.forEach((item, i) => {
        const id = `cb-${Date.now()}-${i}`;
        const div = document.createElement('div');
        div.className = 'action-item';
        div.innerHTML = `<input type="checkbox" class="action-checkbox" id="${id}" style="position:relative;">
          <label class="action-text" for="${id}">${escapeHtml(item)}</label>`;
        container.appendChild(div);
      });
      bubble.appendChild(container);
    }

    // Sources expandable card
    if (sources && (sources.memory?.length || sources.web?.length)) {
      const totalSources = (sources.memory?.length || 0) + (sources.web?.length || 0);
      const toggleId = `src-${Date.now()}`;
      const toggle = document.createElement('button');
      toggle.className = 'sources-toggle';
      toggle.innerHTML = `<span class="arrow">▸</span> ${totalSources} source${totalSources !== 1 ? 's' : ''}`;

      const panel = document.createElement('div');
      panel.className = 'sources-panel';
      let panelHtml = '';

      if (sources.memory?.length) {
        panelHtml += '<div class="source-label">Memory (Qdrant)</div>';
        sources.memory.forEach(s => {
          panelHtml += `<div class="source-item">
            <span class="source-badge memory">${s.score}</span>
            <span class="source-text">${escapeHtml(s.text)}</span>
          </div>`;
        });
      }
      if (sources.web?.length) {
        panelHtml += '<div class="source-label">Web (Tavily)</div>';
        sources.web.forEach(s => {
          panelHtml += `<div class="source-item">
            <span class="source-badge web">WEB</span>
            <span class="source-text"><a href="${escapeHtml(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.title)}</a></span>
          </div>`;
        });
      }
      if (sources.fallback) {
        panelHtml += '<div class="source-label">System</div>';
        panelHtml += `<div class="source-item"><span class="source-badge" style="background:rgba(251,191,36,0.1); color:var(--warn);">OSS Fallback</span><div class="source-text">Generated via Smart Switch</div></div>`;
      }
      panel.innerHTML = panelHtml;

      toggle.addEventListener('click', () => {
        toggle.classList.toggle('open');
        panel.classList.toggle('open');
      });

      bubble.appendChild(toggle);
      bubble.appendChild(panel);
    }

    row.appendChild(bubble);
    chatHistory.appendChild(row);
    scrollToBottom();
  }

  function appendError(text) {
    const row = document.createElement('div');
    row.className = 'message-row ai';
    row.innerHTML = `<div class="bubble ai" style="border-color:rgba(248,113,113,0.3);color:#fca5a5;">
      <p>Error: ${escapeHtml(text)}</p>
    </div>`;
    chatHistory.appendChild(row);
    scrollToBottom();
  }

  // ── PIPELINE TIMELINE HELPERS ────────────────────
  const STAGE_LABELS = {
    'qdrant_retrieval_started': 'Searching Memory (Qdrant)',
    'qdrant_retrieval_done': 'Memory Retrieved',
    'tavily_fetch_started': 'Searching Web (Tavily)',
    'tavily_fetch_done': 'Web Results Fetched',
    'jina_scrape_started': 'Scraping URLs (Jina)',
    'jina_scrape_done': 'URLs Scraped',
    'gemini_generation_started': 'Generating Response (Gemini)',
    'fallback_llm_started': 'Switching to OSS Fallback LLM'
  };

  function showTimeline() {
    const tl = $('pipeline-timeline');
    const stages = $('pipeline-stages');
    stages.innerHTML = '';
    tl.classList.add('active');
  }

  function hideTimeline() {
    $('pipeline-timeline').classList.remove('active');
  }

  function addTimelineStage(stageName, status, latencyMs, extra) {
    const stages = $('pipeline-stages');
    const existing = stages.querySelector(`[data-stage="${stageName}"]`);

    if (existing) {
      // Update existing stage (started → done)
      const icon = existing.querySelector('.stage-icon');
      icon.className = 'stage-icon done';
      icon.textContent = '✓';
      const label = existing.querySelector('.stage-label');
      label.textContent = STAGE_LABELS[stageName] || stageName;
      if (extra) label.textContent += ` (${extra})`;
      if (latencyMs !== undefined) {
        const badge = document.createElement('span');
        badge.className = 'stage-latency';
        badge.textContent = `${latencyMs}ms`;
        existing.appendChild(badge);
      }
      return existing;
    }

    const div = document.createElement('div');
    div.className = 'pipeline-stage';
    div.dataset.stage = stageName;
    const iconClass = status === 'done' ? 'stage-icon done' : 'stage-icon spinning';
    const iconText = status === 'done' ? '✓' : '';
    let labelText = STAGE_LABELS[stageName] || stageName;
    if (extra) labelText += ` (${extra})`;

    div.innerHTML = `<div class="${iconClass}">${iconText}</div><span class="stage-label">${labelText}</span>`;

    if (latencyMs !== undefined) {
      div.innerHTML += `<span class="stage-latency">${latencyMs}ms</span>`;
    }

    stages.appendChild(div);
    return div;
  }

  // ── CHAT (STREAMING) ────────────────────────────
  async function sendMessage() {
    const message = chatInput.value.trim();
    if (!message) return;

    appendUserMessage(message);
    chatInput.value = '';
    chatInput.disabled = true;
    sendBtn.disabled = true;
    showTimeline();
    scrollToBottom();

    const streamUrl = settings.url.replace('/discord-bot-receiver', '/stream');
    const payload = { content: message, author: 'WebClient', enable_jina: settings.enableJina };
    const headers = { 'Content-Type': 'application/json' };
    if (settings.apiKey) headers['X-API-Key'] = settings.apiKey;

    let geminiText = '';
    let finalData = null;

    try {
      const response = await fetch(streamUrl, {
        method: 'POST', headers, body: JSON.stringify(payload)
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep incomplete line in buffer

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const jsonStr = line.slice(6);
          if (!jsonStr) continue;

          try {
            const evt = JSON.parse(jsonStr);

            if (evt.event === 'stage') {
              const name = evt.stage;
              if (name.endsWith('_started')) {
                addTimelineStage(name, 'running');
              } else if (name.endsWith('_done')) {
                // Mark the corresponding _started as done
                const startedName = name.replace('_done', '_started');
                const extra = evt.chunks !== undefined ? `${evt.chunks} chunks`
                  : evt.results !== undefined ? `${evt.results} results`
                  : evt.urls !== undefined ? `${evt.urls} urls` : '';
                addTimelineStage(startedName, 'done', evt.latency_ms, extra);
              }
            } else if (evt.event === 'gemini_chunk') {
              geminiText += evt.text;
              // Show the Gemini stage as active on first chunk
              if (geminiText === evt.text) {
                addTimelineStage('gemini_generation_started', 'running');
              }
            } else if (evt.event === 'complete') {
              finalData = evt.data;
            } else if (evt.event === 'error') {
              appendError(evt.message || 'Pipeline error');
            }
          } catch {}
        }
        scrollToBottom();
      }

      // Finalize
      if (finalData) {
        // Mark gemini as done (will mark as error if it failed, but we just set it to done visually)
        const gemLatency = finalData.latency?.gemini;
        addTimelineStage('gemini_generation_started', 'done', gemLatency);
        
        if (finalData.sources && finalData.sources.fallback) {
          const icon = $('pipeline-stages').querySelector(`[data-stage="gemini_generation_started"] .stage-icon`);
          if (icon) {
            icon.className = 'stage-icon error';
            icon.textContent = '!';
          }
          addTimelineStage('fallback_llm_started', 'done', gemLatency);
        }

        const reply = finalData.reply || geminiText || 'Strategy processed.';
        const actionItems = finalData.action_items || [];
        const sources = finalData.sources || { memory: [], web: [], jina: [] };
        const latency = finalData.latency || null;

        appendAIMessage(reply, actionItems, sources);

        if (latency) saveState('lk_last_latency', latency);

        if (actionItems.length > 0) {
          actionItems.forEach(item => {
            kanbanData.todo.push({ id: Date.now() + Math.random(), text: item, time: new Date().toISOString() });
          });
          saveState(LS_KEYS.kanban, kanbanData);
        }

        statsData.queries++;
        statsData.actions += actionItems.length;
        statsData.sources += (sources.memory?.length || 0) + (sources.web?.length || 0);
        saveState(LS_KEYS.stats, statsData);

        recentQueries.unshift({ text: message, time: new Date().toISOString() });
        if (recentQueries.length > 20) recentQueries.pop();
        saveState(LS_KEYS.queries, recentQueries);
      } else {
        appendError('No response received from the pipeline.');
      }

    } catch (err) {
      appendError(err.message + '. Check Settings to configure your API connection.');
    } finally {
      setTimeout(hideTimeline, 3000);
      chatInput.disabled = false;
      sendBtn.disabled = false;
      chatInput.focus();
      scrollToBottom();
    }
  }

  sendBtn.addEventListener('click', sendMessage);
  chatInput.addEventListener('keypress', e => { if (e.key === 'Enter') sendMessage(); });

  // ── KANBAN ───────────────────────────────────────
  function renderKanban() {
    ['todo', 'doing', 'done'].forEach(col => {
      const container = $('col-' + col);
      container.innerHTML = '';
      const items = kanbanData[col] || [];
      if (items.length === 0) {
        container.innerHTML = '<div class="kanban-empty">No items</div>';
      } else {
        items.forEach((item, idx) => {
          const card = document.createElement('div');
          card.className = 'kanban-card';
          card.draggable = true;
          card.dataset.col = col;
          card.dataset.idx = idx;

          const timeStr = item.time ? new Date(item.time).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
          card.innerHTML = `<button class="kanban-card-delete" title="Delete">✕</button>
            ${escapeHtml(item.text)}
            <div class="kanban-card-time">${timeStr}</div>`;

          card.querySelector('.kanban-card-delete').addEventListener('click', e => {
            e.stopPropagation();
            kanbanData[col].splice(idx, 1);
            if (col === 'done') statsData.completed = Math.max(0, statsData.completed - 1);
            saveState(LS_KEYS.kanban, kanbanData);
            saveState(LS_KEYS.stats, statsData);
            renderKanban();
          });

          // Drag events
          card.addEventListener('dragstart', e => {
            e.dataTransfer.setData('text/plain', JSON.stringify({ col, idx }));
            card.classList.add('dragging');
          });
          card.addEventListener('dragend', () => card.classList.remove('dragging'));

          container.appendChild(card);
        });
      }

      // Drop zone events
      container.addEventListener('dragover', e => { e.preventDefault(); container.classList.add('drag-over'); });
      container.addEventListener('dragleave', () => container.classList.remove('drag-over'));
      container.addEventListener('drop', e => {
        e.preventDefault();
        container.classList.remove('drag-over');
        try {
          const { col: fromCol, idx: fromIdx } = JSON.parse(e.dataTransfer.getData('text/plain'));
          const toCol = col;
          if (fromCol === toCol) return;
          const [item] = kanbanData[fromCol].splice(fromIdx, 1);
          kanbanData[toCol].push(item);
          if (toCol === 'done') statsData.completed++;
          if (fromCol === 'done') statsData.completed = Math.max(0, statsData.completed - 1);
          saveState(LS_KEYS.kanban, kanbanData);
          saveState(LS_KEYS.stats, statsData);
          renderKanban();
        } catch {}
      });

      // Update counts
      $('count-' + col).textContent = items.length;
    });

    const total = kanbanData.todo.length + kanbanData.doing.length + kanbanData.done.length;
    $('kanban-total').textContent = total;
    $('kanban-active').textContent = kanbanData.doing.length;
    $('kanban-done').textContent = kanbanData.done.length;
  }

  // ── INSIGHTS ─────────────────────────────────────
  function renderInsights() {
    $('stat-queries').textContent = statsData.queries;
    $('stat-actions').textContent = statsData.actions;
    $('stat-sources').textContent = statsData.sources;
    $('stat-completed').textContent = statsData.completed;

    const list = $('recent-queries');
    list.innerHTML = '';
    if (recentQueries.length === 0) {
      list.innerHTML = '<div style="color:var(--tx-3);font-size:0.8125rem;padding:12px;">No queries yet. Start chatting!</div>';
    } else {
      recentQueries.slice(0, 10).forEach(q => {
        const timeStr = new Date(q.time).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        const div = document.createElement('div');
        div.className = 'recent-item';
        div.innerHTML = `<div class="recent-dot"></div>${escapeHtml(q.text)}<span class="recent-time">${timeStr}</span>`;
        list.appendChild(div);
      });
    }

    const latencyEl = $('latency-breakdown');
    if (latencyEl) {
      const lat = loadState('lk_last_latency', null);
      if (!lat) {
        latencyEl.innerHTML = '<div style="color:var(--tx-3);font-size:0.875rem;">No data yet.</div>';
      } else {
        latencyEl.innerHTML = `
          <div style="display:flex; justify-content:space-between; margin-bottom:8px;"><span>Qdrant (Memory):</span> <span>${lat.qdrant || 0} ms</span></div>
          <div style="display:flex; justify-content:space-between; margin-bottom:8px;"><span>Tavily (Web):</span> <span>${lat.tavily || 0} ms</span></div>
          <div style="display:flex; justify-content:space-between; margin-bottom:8px;"><span>Jina (Scraping):</span> <span>${lat.jina || 0} ms</span></div>
          <div style="display:flex; justify-content:space-between; margin-bottom:8px;"><span>Gemini (LLM):</span> <span>${lat.gemini || 0} ms</span></div>
          <div style="display:flex; justify-content:space-between; font-weight:bold; color:var(--accent); border-top:1px solid rgba(255,255,255,0.1); padding-top:8px;"><span>Total:</span> <span>${lat.total || 0} ms</span></div>
        `;
      }
    }
  }

  // ── SETTINGS ─────────────────────────────────────
  function loadSettings() {
    $('settings-url').value = settings.url;
    $('settings-apikey').value = settings.apiKey;
    if ($('settings-jina')) $('settings-jina').checked = settings.enableJina;
  }

  $('settings-save').addEventListener('click', () => {
    settings.url = $('settings-url').value.trim() || settings.url;
    settings.apiKey = $('settings-apikey').value.trim();
    if ($('settings-jina')) settings.enableJina = $('settings-jina').checked;
    saveState(LS_KEYS.settings, settings);
    alert('Configuration saved.');
  });

  $('settings-clear').addEventListener('click', () => {
    if (!confirm('Clear all local data? This will reset your Kanban board, stats, and query history.')) return;
    kanbanData = { todo: [], doing: [], done: [] };
    statsData = { queries: 0, actions: 0, sources: 0, completed: 0 };
    recentQueries = [];
    Object.values(LS_KEYS).forEach(k => localStorage.removeItem(k));
    renderKanban();
    renderInsights();
    alert('All local data cleared.');
  });

  // ── UTILS ────────────────────────────────────────
  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // ── INIT ─────────────────────────────────────────
  loadSettings();
  chatInput.focus();

  // ── NEW FEATURES HANDLERS ────────────────────────
  
  // Notion Sync
  const btnSyncNotion = $('btn-sync-notion');
  if (btnSyncNotion) {
    btnSyncNotion.addEventListener('click', async () => {
      btnSyncNotion.textContent = 'Syncing...';
      const headers = { 'Content-Type': 'application/json' };
      if (settings.apiKey) headers['X-API-Key'] = settings.apiKey;
      try {
        const res = await fetch(settings.url.replace('/discord-bot-receiver', '/tasks'), { headers });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        const list = $('notion-tasks-list');
        list.innerHTML = '';
        if (data.tasks && data.tasks.length > 0) {
          data.tasks.forEach(task => {
            const props = task.properties;
            const title = props['Task / Project']?.title?.[0]?.plain_text || 'Untitled';
            const status = props['Status']?.status?.name || 'Unknown';
            const html = `
              <div style="border-bottom:1px solid rgba(255,255,255,0.05); padding:12px 0;">
                <div style="font-weight:600; color:var(--tx-1)">${escapeHtml(title)}</div>
                <div style="font-size:var(--t-xs); color:var(--tx-3)">Status: <span style="color:var(--accent)">${escapeHtml(status)}</span></div>
              </div>
            `;
            list.innerHTML += html;
          });
        } else {
          list.innerHTML = '<div style="color:var(--tx-3);font-size:0.875rem;">No active tasks found in Notion.</div>';
        }
      } catch (err) {
        $('notion-tasks-list').innerHTML = `<div style="color:var(--warn);font-size:0.875rem;">Error: ${err.message}</div>`;
      } finally {
        btnSyncNotion.textContent = 'Sync from Notion';
      }
    });
  }

  // Memory Explorer
  async function loadMemory() {
    const list = $('memory-explorer-list');
    list.innerHTML = '<div style="color:var(--tx-3);font-size:0.875rem;">Loading memory chunks...</div>';
    const headers = { 'Content-Type': 'application/json' };
    if (settings.apiKey) headers['X-API-Key'] = settings.apiKey;
    try {
      const res = await fetch(settings.url.replace('/discord-bot-receiver', '/memory'), { headers });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      list.innerHTML = '';
      if (data.memory && data.memory.length > 0) {
        data.memory.forEach(mem => {
          const text = mem.text || 'No text content';
          const html = `
            <div style="border-bottom:1px solid rgba(255,255,255,0.1); padding:12px 0;">
              <div style="font-size:var(--t-sm); color:var(--tx-2); line-height:1.5;">${escapeHtml(text)}</div>
            </div>
          `;
          list.innerHTML += html;
        });
      } else {
        list.innerHTML = '<div style="color:var(--tx-3);font-size:0.875rem;">Memory DB is empty.</div>';
      }
    } catch (err) {
      list.innerHTML = `<div style="color:var(--warn);font-size:0.875rem;">Error: ${err.message}</div>`;
    }
  }
  const btnRefreshMemory = $('btn-refresh-memory');
  if (btnRefreshMemory) {
    btnRefreshMemory.addEventListener('click', loadMemory);
  }

  // Health Check
  const btnCheckHealth = $('btn-check-health');
  if (btnCheckHealth) {
    btnCheckHealth.addEventListener('click', async () => {
      btnCheckHealth.textContent = 'Pinging...';
      const spans = ['qdrant', 'tavily', 'notion', 'gemini'];
      spans.forEach(s => $(`health-${s}`).textContent = 'Pinging...');
      
      const headers = { 'Content-Type': 'application/json' };
      if (settings.apiKey) headers['X-API-Key'] = settings.apiKey;
      try {
        const res = await fetch(settings.url.replace('/discord-bot-receiver', '/health'), { headers });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        spans.forEach(s => {
          const el = $(`health-${s}`);
          if (data[s]) {
            el.textContent = `${data[s].status.toUpperCase()} (${data[s].latency_ms}ms)`;
            el.style.color = data[s].status === 'up' ? 'var(--pass)' : 'var(--warn)';
          } else {
            el.textContent = 'N/A';
          }
        });
      } catch (err) {
        spans.forEach(s => {
          $(`health-${s}`).textContent = 'FAILED';
          $(`health-${s}`).style.color = 'var(--warn)';
        });
      } finally {
        btnCheckHealth.textContent = 'Ping Services';
      }
    });
  }

  // History Explorer
  const btnLoadHistory = $('btn-load-history');
  if (btnLoadHistory) {
    btnLoadHistory.addEventListener('click', async () => {
      btnLoadHistory.textContent = 'Loading...';
      const list = $('history-list');
      const chart = $('history-chart');
      
      const headers = { 'Content-Type': 'application/json' };
      if (settings.apiKey) headers['X-API-Key'] = settings.apiKey;
      try {
        const res = await fetch(settings.url.replace('/discord-bot-receiver', '/history?limit=30'), { headers });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        
        list.innerHTML = '';
        chart.innerHTML = '';
        
        if (data.entries && data.entries.length > 0) {
          // Render List
          data.entries.forEach(entry => {
            const timeStr = new Date(entry.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
            const totalMs = entry.latency?.total || 0;
            const srcColor = entry.source === 'discord' ? 'var(--info)' : 'var(--accent)';
            const html = `
              <div style="border-bottom:1px solid rgba(255,255,255,0.05); padding:12px 0;">
                <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                  <span style="font-weight:600; color:var(--tx-1); font-size:0.875rem;">${escapeHtml(entry.user_message)}</span>
                  <span style="font-family:var(--mono); font-size:0.6875rem; color:var(--tx-3)">${totalMs}ms</span>
                </div>
                <div style="font-size:var(--t-xs); color:var(--tx-3); display:flex; justify-content:space-between;">
                  <span>Source: <span style="color:${srcColor}">${entry.source}</span></span>
                  <span>${timeStr}</span>
                </div>
              </div>
            `;
            list.innerHTML += html;
          });

          // Render Chart (Bar chart for latency of last N queries)
          // We reverse to chronological order for the chart
          const chartData = [...data.entries].reverse();
          const maxLatency = Math.max(...chartData.map(e => e.latency?.total || 0), 100);
          
          chartData.forEach(entry => {
            const ms = entry.latency?.total || 0;
            const heightPct = Math.max((ms / maxLatency) * 100, 2);
            const bar = document.createElement('div');
            bar.style.flex = '1';
            bar.style.backgroundColor = 'var(--accent)';
            bar.style.height = `${heightPct}%`;
            bar.style.minWidth = '4px';
            bar.style.borderRadius = '2px 2px 0 0';
            bar.style.opacity = '0.7';
            bar.title = `${ms}ms`;
            
            // Hover effect
            bar.addEventListener('mouseenter', () => bar.style.opacity = '1');
            bar.addEventListener('mouseleave', () => bar.style.opacity = '0.7');
            chart.appendChild(bar);
          });
          
        } else {
          list.innerHTML = '<div style="color:var(--tx-3);font-size:0.875rem;">No history found on server.</div>';
        }
      } catch (err) {
        list.innerHTML = `<div style="color:var(--warn);font-size:0.875rem;">Error: ${err.message}</div>`;
      } finally {
        btnLoadHistory.textContent = 'Load History';
      }
    });
  }

  // ── BACKGROUND ANIMATION ─────────────────────────
  document.addEventListener('mousemove', e => {
    document.documentElement.style.setProperty('--mouse-x', `${e.clientX}px`);
    document.documentElement.style.setProperty('--mouse-y', `${e.clientY}px`);
  });

})();
