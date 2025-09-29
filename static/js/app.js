// ESMO 2025 – Filters, Table, AI (fixed layout + AI Action Bar)
document.addEventListener('DOMContentLoaded', function() {

  // ===== Shared refs =====
  const tableContainer = document.getElementById('tableContainer');
  const filterContext  = document.getElementById('filterContext');
  const exportBtn      = document.getElementById('exportBtn');

  // Explorer filter bar
  const searchInput    = document.getElementById('searchInput');
  const searchBtn      = document.getElementById('searchBtn');
  const clearSearchBtn = document.getElementById('clearSearchBtn');
  const filterSummary  = document.getElementById('filterSummary');

  // Explorer filter buttons (new toggle button system)
  const drugFilterButtons = document.querySelectorAll('.drug-filter-btn');
  const taFilterButtons   = document.querySelectorAll('.ta-filter-btn');
  const sessionFilterButtons = document.querySelectorAll('.session-filter-btn');
  const dateFilterButtons = document.querySelectorAll('.date-filter-btn');

  // AI filter buttons (no search on AI tab)
  const aiFilterSummary = document.getElementById('aiFilterSummary');
  const aiDrugFilterButtons = document.querySelectorAll('.ai-drug-filter-btn');
  const aiTaFilterButtons   = document.querySelectorAll('.ai-ta-filter-btn');
  const aiFilterContext     = document.getElementById('aiFilterContext');

  // Playbooks (chips)
  const playbookTriggers = document.querySelectorAll('.playbook-trigger');

  // Chat
  const chatContainer  = document.getElementById('chatContainer');
  const userInput      = document.getElementById('userInput');
  const sendChatBtn    = document.getElementById('sendChatBtn');

  // ===== State =====
  let currentFilters = { drug_filters: [], ta_filters: [], session_filters: [], date_filters: [] };
  let currentTableData = [];
  let sortState = { column: null, direction: 'asc' };

  // ===== Init =====
  loadData();

  // ===== Toggle Button Helpers =====
  function getSelectedButtonValues(nodeList) {
    return Array.from(nodeList).filter(btn => btn.classList.contains('active')).map(btn => btn.dataset.value);
  }
  function setButtonValues(nodeList, values) {
    nodeList.forEach(btn => {
      if (values.includes(btn.dataset.value)) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
  }
  function updateCurrentFilters() {
    currentFilters.drug_filters = getSelectedButtonValues(drugFilterButtons);
    currentFilters.ta_filters   = getSelectedButtonValues(taFilterButtons);
    currentFilters.session_filters = getSelectedButtonValues(sessionFilterButtons);
    currentFilters.date_filters = getSelectedButtonValues(dateFilterButtons);
  }
  function syncAIFilters() {
    setButtonValues(aiDrugFilterButtons, currentFilters.drug_filters);
    setButtonValues(aiTaFilterButtons,   currentFilters.ta_filters);
    updateFilterSummaries();
  }
  function syncExplorerFilters() {
    setButtonValues(drugFilterButtons, currentFilters.drug_filters);
    setButtonValues(taFilterButtons,   currentFilters.ta_filters);
    setButtonValues(sessionFilterButtons, currentFilters.session_filters);
    setButtonValues(dateFilterButtons, currentFilters.date_filters);
    updateFilterSummaries();
  }
  function updateFilterSummaries() {
    const drugs = currentFilters.drug_filters.length ? currentFilters.drug_filters.join(', ') : 'All Drugs';
    const tas   = currentFilters.ta_filters.length   ? currentFilters.ta_filters.join(', ')   : 'All Therapeutic Areas';
    const sessions = currentFilters.session_filters.length ? currentFilters.session_filters.join(', ') : 'All Session Types';
    const dates = currentFilters.date_filters.length ? currentFilters.date_filters.join(', ') : 'All Days';
    if (filterSummary)   filterSummary.textContent   = `${drugs} + ${tas} + ${sessions} + ${dates}`;
    if (aiFilterSummary) aiFilterSummary.textContent = `${drugs} + ${tas} + ${sessions} + ${dates}`;
    if (aiFilterContext) aiFilterContext.textContent = `Analyzing: ${drugs} + ${tas} + ${sessions} + ${dates}`;
  }

  // ===== Explorer filter button events =====
  drugFilterButtons.forEach(btn => btn.addEventListener('click', () => {
    btn.classList.toggle('active');
    updateCurrentFilters(); syncAIFilters(); loadData();
  }));
  taFilterButtons.forEach(btn => btn.addEventListener('click', () => {
    btn.classList.toggle('active');
    updateCurrentFilters(); syncAIFilters(); loadData();
  }));
  sessionFilterButtons.forEach(btn => btn.addEventListener('click', () => {
    btn.classList.toggle('active');
    updateCurrentFilters(); syncAIFilters(); loadData();
  }));
  dateFilterButtons.forEach(btn => btn.addEventListener('click', () => {
    btn.classList.toggle('active');
    updateCurrentFilters(); syncAIFilters(); loadData();
  }));

  // ===== AI filter button events (sync back) =====
  aiDrugFilterButtons.forEach(btn => btn.addEventListener('click', () => {
    btn.classList.toggle('active');
    currentFilters.drug_filters = getSelectedButtonValues(aiDrugFilterButtons);
    currentFilters.ta_filters   = getSelectedButtonValues(aiTaFilterButtons);
    syncExplorerFilters(); loadData();
  }));
  aiTaFilterButtons.forEach(btn => btn.addEventListener('click', () => {
    btn.classList.toggle('active');
    currentFilters.drug_filters = getSelectedButtonValues(aiDrugFilterButtons);
    currentFilters.ta_filters   = getSelectedButtonValues(aiTaFilterButtons);
    syncExplorerFilters(); loadData();
  }));

  // ===== Search (Explorer only) =====
  if (searchInput){
    searchInput.addEventListener('input', debounce(handleLiveSearch, 300));
    searchInput.addEventListener('input', toggleClearButton);
    searchInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') handleSearch(); });
  }
  if (searchBtn){ searchBtn.addEventListener('click', handleSearch); }
  if (clearSearchBtn){ clearSearchBtn.addEventListener('click', clearSearch); }

  function handleLiveSearch() {
    const q = (searchInput?.value || '').trim();
    if (q.length >= 3) handleSearch();
    else if (q.length === 0) loadData();
  }

  async function handleSearch() {
    const query = (searchInput?.value || '').trim();
    if (!query) { loadData(); return; }

    try {
      showLoading();
      const params = new URLSearchParams();
      params.append('keyword', query);
      currentFilters.drug_filters.forEach(f => params.append('drug_filters', f));
      currentFilters.ta_filters.forEach(f => params.append('ta_filters', f));
      currentFilters.session_filters.forEach(f => params.append('session_filters', f));
      currentFilters.date_filters.forEach(f => params.append('date_filters', f));

      const res = await fetch(`/api/search?${params}`);
      const data = await res.json();
      if (data.error) throw new Error(data.error);

      renderTable(data);

      const drugs = currentFilters.drug_filters.length ? currentFilters.drug_filters.join(', ') : 'All Drugs';
      const tas   = currentFilters.ta_filters.length   ? currentFilters.ta_filters.join(', ')   : 'All Therapeutic Areas';
      const sessions = currentFilters.session_filters.length ? currentFilters.session_filters.join(', ') : 'All Session Types';
      const dates = currentFilters.date_filters.length ? currentFilters.date_filters.join(', ') : 'All Days';

      // Search is always active here, so use purple color
      filterContext.innerHTML = `
        <span class="text-purple fw-bold">Showing ${data.length.toLocaleString()} of 4,686</span> •
        Filters: ${drugs} + ${tas} + ${sessions} + ${dates}`;
    } catch (err) {
      console.error(err);
      showError('Search failed. Please try again.');
    }
  }

  // ===== Clear Search =====
  function toggleClearButton() {
    const hasText = searchInput && searchInput.value.trim().length > 0;
    if (clearSearchBtn) {
      clearSearchBtn.style.display = hasText ? 'block' : 'none';
    }
  }

  function clearSearch() {
    if (searchInput) {
      searchInput.value = '';
      toggleClearButton();
      loadData(); // Return to filtered data view
    }
  }

  // ===== Data load =====
  async function loadData() {
    try {
      showLoading();
      const params = new URLSearchParams();
      currentFilters.drug_filters.forEach(f => params.append('drug_filters', f));
      currentFilters.ta_filters.forEach(f => params.append('ta_filters', f));
      currentFilters.session_filters.forEach(f => params.append('session_filters', f));
      currentFilters.date_filters.forEach(f => params.append('date_filters', f));

      const res = await fetch(`/api/data?${params}`);
      const payload = await res.json();
      if (payload.error) throw new Error(payload.error);

      renderTable(payload.data);
      updateFilterContext(payload.filter_context, payload.showing, payload.total);
      updateFilterSummaries();
    } catch (err) {
      console.error(err);
      showError('Failed to load ESMO data');
    }
  }

  function showLoading(){
    tableContainer.innerHTML = `
      <div class="text-center py-4">
        <div class="spinner-border" role="status"><span class="visually-hidden">Loading...</span></div>
        <p class="mt-2">Loading ESMO 2025 data...</p>
      </div>`;
  }
  function showError(message){
    tableContainer.innerHTML = `
      <div class="alert alert-danger" role="alert">
        <h4 class="alert-heading">Error</h4>
        <p>${message}</p>
      </div>`;
  }

  function updateFilterContext(context, showing, total){
    if (!context) return;
    const { total_sessions, total_available, filter_summary } = context;

    // Use the passed showing count if available, otherwise fall back to context
    const displayCount = showing !== undefined ? showing : total_sessions;
    const totalCount = total !== undefined ? total : total_available || 4686;

    // Check if any filters or search are active
    const hasActiveFilters = currentFilters.drug_filters.length > 0 ||
                            currentFilters.ta_filters.length > 0 ||
                            currentFilters.session_filters.length > 0 ||
                            currentFilters.date_filters.length > 0 ||
                            (searchInput && searchInput.value.trim().length > 0);

    const colorClass = hasActiveFilters ? 'text-purple fw-bold' : '';

    filterContext.innerHTML = `
      <span class="${colorClass}">Showing ${displayCount.toLocaleString()} of ${totalCount.toLocaleString()}</span> • ${filter_summary}`;
  }

  // ===== Table rendering (fixed layout + hover/tap expand) =====
  function renderTable(data, skipDataUpdate = false){
    if (!skipDataUpdate) {
      currentTableData = data || [];
    }

    if (!currentTableData || currentTableData.length === 0){
      tableContainer.innerHTML = `
        <div class="alert alert-info" role="alert">
          <h4 class="alert-heading">No Results</h4>
          <p>No sessions found with current filters. Try adjusting your selection.</p>
        </div>`;
      return;
    }

    const headers = ['Title','Speakers','Speaker Location','Affiliation','Identifier','Room','Date','Time','Session','Theme'];

    // Default column widths (sync with CSS col:nth-child)
    const colWidths = {
      'Title':'25%',
      'Speakers':'15%',
      'Speaker Location':'12%',
      'Affiliation':'15%',
      'Identifier':'8%',
      'Room':'10%',
      'Date':'8%',
      'Time':'7%',
      'Session':'12%',
      'Theme':'15%'
    };

    // Sort data if needed
    let sortedData = [...currentTableData];
    if (sortState.column) {
      sortedData = sortData(sortedData, sortState.column, sortState.direction);
    }

    let html = `
      <div id="tableViewport">
        <table class="table table-hover table-striped align-middle table-fixed" id="dataTable">
          <colgroup>${headers.map(h => `<col style="width:${colWidths[h]||'auto'}">`).join('')}</colgroup>
          <thead>
            <tr>
              ${headers.map(h => `
                <th class="sortable-header" data-column="${h}" style="cursor: pointer; user-select: none; position: relative;">
                  <span class="header-text">${h}</span>
                  <span class="sort-indicator">${getSortIcon(h)}</span>
                  <div class="resize-handle" style="position: absolute; right: 0; top: 0; bottom: 0; width: 5px; cursor: col-resize; background: transparent;"></div>
                </th>
              `).join('')}
            </tr>
          </thead>
          <tbody>
    `;

    sortedData.forEach(row => {
      html += '<tr>';
      headers.forEach(h => {
        const val = row[h] ?? '';
        html += `<td title="${escapeHtml(val)}">${escapeHtml(val)}</td>`;
      });
      html += '</tr>';
    });

    html += `</tbody></table></div>`;
    tableContainer.innerHTML = html;

    // Add event listeners for sorting and resizing
    addTableInteractivity();

    // Mobile: tap toggles expansion
    const supportsHover = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
    if (!supportsHover){
      const rows = tableContainer.querySelectorAll('#tableViewport tbody tr');
      rows.forEach(tr => tr.addEventListener('click', () => tr.classList.toggle('expanded')));
    }
  }

  // ===== Table Sorting & Resizing =====
  function getSortIcon(column) {
    if (sortState.column !== column) {
      return '<i class="bi bi-arrow-down-up" style="opacity: 0.3; margin-left: 5px;"></i>';
    }
    const icon = sortState.direction === 'asc' ? 'bi-arrow-up' : 'bi-arrow-down';
    return `<i class="bi ${icon}" style="margin-left: 5px; color: var(--brand);"></i>`;
  }

  function sortData(data, column, direction) {
    return data.sort((a, b) => {
      let aVal = a[column] ?? '';
      let bVal = b[column] ?? '';

      // Handle Date column specially
      if (column === 'Date') {
        aVal = new Date(aVal);
        bVal = new Date(bVal);
      }
      // Handle Time column specially
      else if (column === 'Time') {
        aVal = parseTime(aVal);
        bVal = parseTime(bVal);
      }
      // Handle Identifier column (numeric sorting for mixed content)
      else if (column === 'Identifier') {
        const aNum = extractNumber(aVal);
        const bNum = extractNumber(bVal);
        if (aNum !== null && bNum !== null) {
          aVal = aNum;
          bVal = bNum;
        } else {
          aVal = aVal.toString().toLowerCase();
          bVal = bVal.toString().toLowerCase();
        }
      }
      // Default: string comparison
      else {
        aVal = aVal.toString().toLowerCase();
        bVal = bVal.toString().toLowerCase();
      }

      let result;
      if (aVal < bVal) result = -1;
      else if (aVal > bVal) result = 1;
      else result = 0;

      return direction === 'desc' ? -result : result;
    });
  }

  function parseTime(timeStr) {
    if (!timeStr) return 0;
    const match = timeStr.match(/(\d{1,2}):(\d{2})/);
    if (match) {
      return parseInt(match[1]) * 60 + parseInt(match[2]);
    }
    return 0;
  }

  function extractNumber(str) {
    const match = str.toString().match(/(\d+)/);
    return match ? parseInt(match[1]) : null;
  }

  function addTableInteractivity() {
    // Add sorting click handlers
    const headers = tableContainer.querySelectorAll('.sortable-header');
    headers.forEach(header => {
      const headerText = header.querySelector('.header-text');
      const resizeHandle = header.querySelector('.resize-handle');

      // Sorting - click on entire header but exclude resize handle area
      header.addEventListener('click', (e) => {
        // Don't sort if clicking on resize handle area
        if (e.target.closest('.resize-handle')) {
          return;
        }
        e.stopPropagation();
        handleSort(header.dataset.column);
      });

      // Column resizing
      let isResizing = false;
      let startX = 0;
      let startWidth = 0;
      let colIndex = Array.from(header.parentElement.children).indexOf(header);

      resizeHandle.addEventListener('mousedown', (e) => {
        e.preventDefault();
        e.stopPropagation();
        isResizing = true;
        startX = e.clientX;
        startWidth = header.offsetWidth;

        // Add global event listeners
        document.addEventListener('mousemove', handleResize);
        document.addEventListener('mouseup', stopResize);

        // Prevent text selection during resize
        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'col-resize';
      });

      function handleResize(e) {
        if (!isResizing) return;
        e.preventDefault();

        const diff = e.clientX - startX;
        const newWidth = Math.max(50, startWidth + diff); // Min width 50px

        // Update the colgroup element
        const table = tableContainer.querySelector('#dataTable');
        const colGroup = table.querySelector('colgroup');
        const col = colGroup.children[colIndex];
        if (col) {
          col.style.width = newWidth + 'px';
        }
      }

      function stopResize(e) {
        if (!isResizing) return;

        isResizing = false;

        // Restore normal cursor and text selection
        document.body.style.userSelect = '';
        document.body.style.cursor = '';

        // Remove global event listeners
        document.removeEventListener('mousemove', handleResize);
        document.removeEventListener('mouseup', stopResize);
      }
    });
  }

  function handleSort(column) {
    if (sortState.column === column) {
      // Toggle direction
      sortState.direction = sortState.direction === 'asc' ? 'desc' : 'asc';
    } else {
      // New column
      sortState.column = column;
      sortState.direction = 'asc';
    }

    // Re-render table with new sort
    renderTable(null, true); // Skip data update, just re-sort current data
  }

  // ===== Export =====
  exportBtn.addEventListener('click', handleExport);
  async function handleExport() {
    try {
      exportBtn.disabled = true;
      const original = exportBtn.innerHTML;
      exportBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span>';
      const response = await fetch('/api/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          drug_filters: currentFilters.drug_filters,
          ta_filters: currentFilters.ta_filters,
          session_filters: currentFilters.session_filters,
          format: 'csv'
        })
      });
      if (!response.ok) throw new Error('Export failed');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const drugFilename = currentFilters.drug_filters.join('_').replace(/ /g, '_') || 'all_drugs';
      const taFilename = currentFilters.ta_filters.join('_').replace(/ /g, '_') || 'all_ta';
      const sessionFilename = currentFilters.session_filters.join('_').replace(/ /g, '_') || 'all_sessions';
      a.download = `esmo2025_${drugFilename}_${taFilename}_${sessionFilename}.csv`;
      a.click();
      window.URL.revokeObjectURL(url);
      exportBtn.innerHTML = original;
    } catch (err) {
      console.error('Export error:', err);
      alert('Export failed. Please try again.');
      exportBtn.innerHTML = 'Download table';
    } finally {
      exportBtn.disabled = false;
    }
  }

  // ===== Playbooks via Action Bar =====
  playbookTriggers.forEach(el => {
    el.addEventListener('click', () => handlePlaybook(el.getAttribute('data-playbook')));
  });

  async function handlePlaybook(playbookType) {
    try {
      // ensure AI tab is visible (defensive)
      const aiTabBtn = document.getElementById('ai-assistant-tab');
      if (window.bootstrap && aiTabBtn) new bootstrap.Tab(aiTabBtn).show();

      appendToChat(`
        <div class="d-flex justify-content-start mb-2">
          <div class="bg-primary text-white rounded p-2" style="max-width:80%;">
            <strong>🤖 Running ${getPlaybookTitle(playbookType)}...</strong>
            <span class="spinner-border spinner-border-sm ms-2" role="status"></span>
          </div>
        </div>`);

      const params = new URLSearchParams();
      currentFilters.drug_filters.forEach(f => params.append('drug_filters', f));
      currentFilters.ta_filters.forEach(f => params.append('ta_filters', f));
      currentFilters.session_filters.forEach(f => params.append('session_filters', f));

      const response = await fetch(`/api/playbook/${playbookType}/stream?${params}`);
      if (!response.ok) throw new Error('Playbook request failed');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      appendToChat(`
        <div class="d-flex justify-content-start mb-2">
          <div class="bg-light border rounded p-3" style="max-width:90%;">
            <div id="playbook-content"></div>
          </div>
        </div>`);

      const contentDiv = document.getElementById('playbook-content');

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6);
            if (dataStr === '[DONE]') continue;
            try {
              const parsed = JSON.parse(dataStr);
              if (parsed.text) {
                contentDiv.innerHTML += escapeHtml(parsed.text);
                chatContainer.scrollTop = chatContainer.scrollHeight;
              }
            } catch (e) {}
          }
        }
      }
    } catch (error) {
      console.error('Playbook error:', error);
      appendToChat(`
        <div class="d-flex justify-content-start mb-2">
          <div class="bg-danger text-white rounded p-2">Error: ${error.message}</div>
        </div>`);
    }
  }

  function getPlaybookTitle(type) {
    const titles = {
      competitor:'Competitor Intelligence',
      kol:'KOL Analysis',
      institution:'Institution Analysis',
      insights:'Insights & Trends',
      strategy:'Strategic Recommendations'
    };
    return titles[type] || type;
  }

  // ===== Chat (placeholder) =====
  sendChatBtn.addEventListener('click', handleChat);
  userInput.addEventListener('keypress', (e)=>{ if(e.key==='Enter') handleChat(); });

  async function handleChat(){
    const message = userInput.value.trim();
    if (!message) return;
    userInput.value = '';

    // Add user message to chat
    appendToChat(`
      <div class="d-flex justify-content-end mb-2">
        <div class="bg-primary text-white rounded p-2" style="max-width:80%;">${escapeHtml(message)}</div>
      </div>`);

    try {
      // Generate unique ID for this response
      const responseId = 'chat-content-' + Date.now();

      // Add loading message
      appendToChat(`
        <div class="d-flex justify-content-start mb-2">
          <div class="bg-light border rounded p-3" style="max-width:90%;">
            <span class="spinner-border spinner-border-sm me-2" role="status"></span>
            <div id="${responseId}">Thinking...</div>
          </div>
        </div>`);

      // Call streaming chat API
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: message,
          ta_filter: 'All', // For now, use All - will implement proper filtering later
          conversation_history: []
        })
      });

      if (!response.ok) throw new Error('Chat request failed');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      const contentDiv = document.getElementById(responseId);
      contentDiv.innerHTML = ''; // Clear loading message

      // Remove the spinner that's in the same parent div
      const spinnerEl = contentDiv.parentElement.querySelector('.spinner-border');
      if (spinnerEl) {
        spinnerEl.remove();
      }

      let currentEvent = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7);
          } else if (line.startsWith('data: ')) {
            const dataStr = line.slice(6);
            if (dataStr === '[DONE]') continue;

            try {
              if (currentEvent === 'table') {
                // Handle table events
                const tableData = JSON.parse(dataStr);
                const tableHtml = generateTableHtml(tableData.title, tableData.rows);
                contentDiv.insertAdjacentHTML('beforebegin', tableHtml);
                chatContainer.scrollTop = chatContainer.scrollHeight;
                currentEvent = null; // Reset event type
              } else {
                // Handle regular text events
                const parsed = JSON.parse(dataStr);
                if (parsed.text) {
                  contentDiv.innerHTML += escapeHtml(parsed.text);
                  chatContainer.scrollTop = chatContainer.scrollHeight;
                }
              }
            } catch (e) {
              // Skip malformed JSON
            }
          }
        }
      }
    } catch (error) {
      console.error('Chat error:', error);
      appendToChat(`
        <div class="d-flex justify-content-start mb-2">
          <div class="bg-danger text-white rounded p-2">Error: ${error.message}</div>
        </div>`);
    }
  }

  function appendToChat(html){
    chatContainer.insertAdjacentHTML('beforeend', html);
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }

  // ===== Utilities =====
  function escapeHtml(text){ const div = document.createElement('div'); div.textContent = text ?? ''; return div.innerHTML; }
  function debounce(fn, wait){ let t; return (...args)=>{ clearTimeout(t); t = setTimeout(()=>fn.apply(this,args), wait); }; }

  function generateTableHtml(title, rows) {
    if (!rows || rows.length === 0) return '';

    const headers = Object.keys(rows[0]);

    let html = `
      <div class="chat-table-container mb-3">
        <h6 class="mb-2">${escapeHtml(title)}</h6>
        <div class="table-responsive" style="max-height: 300px; overflow-y: auto;">
          <table class="table table-sm table-striped table-hover">
            <thead class="table-dark sticky-top">
              <tr>${headers.map(h => `<th style="white-space: nowrap;">${escapeHtml(h)}</th>`).join('')}</tr>
            </thead>
            <tbody>`;

    rows.forEach(row => {
      html += '<tr>';
      headers.forEach(header => {
        const value = row[header] || '';
        html += `<td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(value)}">${escapeHtml(value)}</td>`;
      });
      html += '</tr>';
    });

    html += `
            </tbody>
          </table>
        </div>
      </div>`;

    return html;
  }

  // ===== Chevron Toggle Functionality =====
  // Handle chevron rotation for Data Explorer filters
  const explorerFiltersElement = document.getElementById('explorerFilters');
  const explorerToggleBtn = document.querySelector('[data-bs-target="#explorerFilters"]');
  const explorerChevron = explorerToggleBtn?.querySelector('.chevron-icon');

  if (explorerFiltersElement && explorerChevron) {
    explorerFiltersElement.addEventListener('show.bs.collapse', function () {
      explorerChevron.textContent = '▲';
    });

    explorerFiltersElement.addEventListener('hide.bs.collapse', function () {
      explorerChevron.textContent = '▼';
    });
  }

  // Handle chevron rotation for AI Assistant filters
  const aiFiltersElement = document.getElementById('aiFilters');
  const aiToggleBtn = document.querySelector('[data-bs-target="#aiFilters"]');
  const aiChevron = aiToggleBtn?.querySelector('.chevron-icon');

  if (aiFiltersElement && aiChevron) {
    aiFiltersElement.addEventListener('show.bs.collapse', function () {
      aiChevron.textContent = '▲';
    });

    aiFiltersElement.addEventListener('hide.bs.collapse', function () {
      aiChevron.textContent = '▼';
    });
  }

});
