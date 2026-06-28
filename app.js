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
    apiKey: ''
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

  async function sendMessage() {
    const message = chatInput.value.trim();
    if (!message) return;

    appendUserMessage(message);
    chatInput.value = '';
    chatInput.disabled = true;
    sendBtn.disabled = true;
    typingIndicator.style.display = 'flex';
    scrollToBottom();

    const payload = { content: message, author: 'WebClient' };
    const headers = { 'Content-Type': 'application/json' };
    if (settings.apiKey) headers['X-API-Key'] = settings.apiKey;

    try {
      const response = await fetch(settings.url, {
        method: 'POST', headers, body: JSON.stringify(payload)
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();

      const reply = data.reply || 'Strategy processed.';
      const actionItems = data.action_items || [];
      const sources = data.sources || { memory: [], web: [] };

      appendAIMessage(reply, actionItems, sources);

      // Push action items to Kanban
      if (actionItems.length > 0) {
        actionItems.forEach(item => {
          kanbanData.todo.push({ id: Date.now() + Math.random(), text: item, time: new Date().toISOString() });
        });
        saveState(LS_KEYS.kanban, kanbanData);
      }

      // Update stats
      statsData.queries++;
      statsData.actions += actionItems.length;
      statsData.sources += (sources.memory?.length || 0) + (sources.web?.length || 0);
      saveState(LS_KEYS.stats, statsData);

      // Track recent query
      recentQueries.unshift({ text: message, time: new Date().toISOString() });
      if (recentQueries.length > 20) recentQueries.pop();
      saveState(LS_KEYS.queries, recentQueries);

    } catch (err) {
      appendError(err.message + '. Check Settings to configure your API connection.');
    } finally {
      typingIndicator.style.display = 'none';
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
  }

  // ── SETTINGS ─────────────────────────────────────
  function loadSettings() {
    $('settings-url').value = settings.url;
    $('settings-apikey').value = settings.apiKey;
  }

  $('settings-save').addEventListener('click', () => {
    settings.url = $('settings-url').value.trim() || settings.url;
    settings.apiKey = $('settings-apikey').value.trim();
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

  // ── BACKGROUND ANIMATION ─────────────────────────
  document.addEventListener('mousemove', e => {
    document.documentElement.style.setProperty('--mouse-x', `${e.clientX}px`);
    document.documentElement.style.setProperty('--mouse-y', `${e.clientY}px`);
  });

})();
