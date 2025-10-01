// ESMO 2025 – Filters, Table, AI (Sidebar layout)
document.addEventListener('DOMContentLoaded', function() {

  // ===== Sidebar Toggle with Hover =====
  const filterSidebar = document.getElementById('filterSidebar');
  const sidebarToggle = document.getElementById('sidebarToggle');
  const sidebarOverlay = document.getElementById('sidebarOverlay');
  const sidebarHeader = filterSidebar?.querySelector('.sidebar-header');
  let isPinned = false; // Track if sidebar is pinned open

  function expandSidebar() {
    filterSidebar?.classList.remove('collapsed');
  }

  function collapseSidebar() {
    if (!isPinned) {
      filterSidebar?.classList.add('collapsed');
    }
  }

  function togglePin() {
    isPinned = !isPinned;
    if (isPinned) {
      expandSidebar();
    } else {
      collapseSidebar();
    }
  }

  // Hover to expand, leave to collapse
  if (filterSidebar) {
    filterSidebar.addEventListener('mouseenter', expandSidebar);
    filterSidebar.addEventListener('mouseleave', collapseSidebar);
  }

  // Click header to pin/unpin
  if (sidebarHeader) {
    sidebarHeader.addEventListener('click', (e) => {
      // Don't toggle if clicking Clear All button
      if (!e.target.closest('#clearAllFilters')) {
        togglePin();
      }
    });
  }

  // ===== Filter Section Collapse/Expand =====
  document.querySelectorAll('.filter-section-header').forEach(header => {
    header.addEventListener('click', (e) => {
      e.stopPropagation(); // Don't trigger sidebar toggle
      const section = header.closest('.filter-section');
      section.classList.toggle('collapsed');
    });
  });

  // ===== Quick Intelligence Sidebar - Click to toggle =====
  const quickIntelSidebar = document.getElementById('quickIntelSidebar');
  const quickIntelHeader = quickIntelSidebar?.querySelector('.quick-intel-header');

  if (quickIntelHeader) {
    quickIntelHeader.addEventListener('click', () => {
      quickIntelSidebar.classList.toggle('collapsed');
    });
  }

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

  // Chat (using chatInput for new Claude-style interface)
  const chatContainer  = document.getElementById('chatContainer');
  const userInput      = document.getElementById('chatInput'); // Changed from 'userInput' to 'chatInput'
  const sendChatBtn    = document.getElementById('chatSendBtn');

  // ===== State =====
  let currentFilters = { drug_filters: [], ta_filters: [], session_filters: [], date_filters: [] };
  let currentTableData = [];
  let sortState = { column: null, direction: 'asc' };
  let conversationHistory = []; // Store last 10 messages (5 user + 5 AI)

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

    // Don't show filter summary in Data Explorer tab (redundant with filter context)
    if (filterSummary)   filterSummary.textContent   = '';

    // Keep AI tab summaries
    if (aiFilterSummary) aiFilterSummary.textContent = `${drugs} + ${tas} + ${sessions} + ${dates}`;
    if (aiFilterContext) aiFilterContext.textContent = `Analyzing: ${drugs} + ${tas} + ${sessions} + ${dates}`;

    // Update filter count badge
    updateFilterCountBadge();
  }

  function updateFilterCountBadge() {
    const totalFilters = currentFilters.drug_filters.length +
                        currentFilters.ta_filters.length +
                        currentFilters.session_filters.length +
                        currentFilters.date_filters.length;
    const badge = document.getElementById('filterCountBadge');
    if (badge) {
      badge.textContent = totalFilters === 0 ? '0 active' : `${totalFilters} active`;
    }
  }

  // Clear All Filters functionality
  const clearAllFiltersBtn = document.getElementById('clearAllFilters');
  if (clearAllFiltersBtn) {
    clearAllFiltersBtn.addEventListener('click', (e) => {
      e.stopPropagation(); // Prevent sidebar toggle

      // Clear all filter arrays
      currentFilters.drug_filters = [];
      currentFilters.ta_filters = [];
      currentFilters.session_filters = [];
      currentFilters.date_filters = [];

      // Remove active class from all buttons
      document.querySelectorAll('.filter-toggle-btn').forEach(btn => btn.classList.remove('active'));

      // Update UI and reload data
      syncAIFilters();
      smartLoad();
    });
  }

  // Smart load: maintains search when filters change
  function smartLoad() {
    const query = (searchInput?.value || '').trim();
    if (query) {
      handleSearch(); // Maintain search with new filters
    } else {
      loadData();     // Just load filtered data
    }
  }

  // ===== Explorer filter button events =====
  drugFilterButtons.forEach(btn => btn.addEventListener('click', () => {
    btn.classList.toggle('active');
    updateCurrentFilters(); syncAIFilters(); smartLoad();
  }));
  taFilterButtons.forEach(btn => btn.addEventListener('click', () => {
    btn.classList.toggle('active');
    updateCurrentFilters(); syncAIFilters(); smartLoad();
  }));
  sessionFilterButtons.forEach(btn => btn.addEventListener('click', () => {
    btn.classList.toggle('active');
    updateCurrentFilters(); syncAIFilters(); smartLoad();
  }));
  dateFilterButtons.forEach(btn => btn.addEventListener('click', () => {
    btn.classList.toggle('active');
    updateCurrentFilters(); syncAIFilters(); smartLoad();
  }));

  // ===== AI filter button events (sync back) =====
  aiDrugFilterButtons.forEach(btn => btn.addEventListener('click', () => {
    btn.classList.toggle('active');
    currentFilters.drug_filters = getSelectedButtonValues(aiDrugFilterButtons);
    currentFilters.ta_filters   = getSelectedButtonValues(aiTaFilterButtons);
    syncExplorerFilters(); smartLoad();
  }));
  aiTaFilterButtons.forEach(btn => btn.addEventListener('click', () => {
    btn.classList.toggle('active');
    currentFilters.drug_filters = getSelectedButtonValues(aiDrugFilterButtons);
    currentFilters.ta_filters   = getSelectedButtonValues(aiTaFilterButtons);
    syncExplorerFilters(); smartLoad();
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
      const payload = await res.json();
      if (payload.error) throw new Error(payload.error);

      renderTable(payload.data);
      updateFilterContext(payload.filter_context, payload.showing, payload.total);
      updateFilterSummaries();
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

    // Build active filters string (only show non-"All" values)
    const activeFilters = [];
    if (currentFilters.drug_filters.length > 0) {
      activeFilters.push(currentFilters.drug_filters.join(', '));
    }
    if (currentFilters.ta_filters.length > 0) {
      activeFilters.push(currentFilters.ta_filters.join(', '));
    }
    if (currentFilters.session_filters.length > 0) {
      activeFilters.push(currentFilters.session_filters.join(', '));
    }
    if (currentFilters.date_filters.length > 0) {
      activeFilters.push(currentFilters.date_filters.join(', '));
    }

    // Only show filter summary if filters are active
    const filterDisplay = hasActiveFilters
      ? ` • <span class="text-purple fw-bold">${activeFilters.join(' + ')}</span>`
      : '';

    filterContext.innerHTML = `
      <span class="${hasActiveFilters ? 'text-purple fw-bold' : ''}">Showing ${displayCount.toLocaleString()} of ${totalCount.toLocaleString()}</span>${filterDisplay}`;
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
        const displayVal = renderCellContent(val);
        const titleVal = escapeHtml(val.replace(/<mark[^>]*>/g, '').replace(/<\/mark>/g, ''));
        html += `<td title="${titleVal}">${displayVal}</td>`;
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
  // REMOVED: Old direct playbook handler (now using modal-based flow at line ~1256)

  function createTableHTML(title, subtitle, columns, rows, tableId = 'playbookTable') {
    // Create table matching Data Explorer with sorting, resizing, and hover expansion

    // Define column widths based on common columns
    const getColWidth = (col) => {
      const widthMap = {
        'Drug': '10%', 'Company': '15%',
        'Title': '25%', 'Speakers': '15%', 'Speaker': '20%', 'Speaker Location': '12%',
        'Affiliation': '20%', 'Identifier': '8%', 'Room': '10%',
        'Date': '8%', 'Time': '7%', 'Session': '12%', 'Theme': '15%',
        'Threat Type': '12%', 'Location': '15%',
        '# Studies': '8%', 'Institution': '25%', '# Abstracts': '8%'
      };
      return widthMap[col] || 'auto';
    };

    let html = `<div class="playbook-table-container mb-3">`;
    if (title) html += `<h5 class="mb-2">${escapeHtml(title)}</h5>`;
    if (subtitle) html += `<p class="text-muted small mb-2">${escapeHtml(subtitle)}</p>`;

    // Wrap in viewport div with fixed height and scroll
    html += `<div class="playbook-table-viewport" style="max-height: 50vh; overflow: auto; border-radius: 12px; border: 1px solid var(--stroke); background: var(--card);">`;
    html += `<table class="table table-hover table-striped align-middle table-fixed" id="${tableId}">`;

    // Column widths
    html += `<colgroup>${columns.map(c => `<col style="width:${getColWidth(c)}">`).join('')}</colgroup>`;

    // Headers with sort indicators and resize handles
    html += `<thead><tr>`;
    columns.forEach(col => {
      html += `<th class="sortable-header" data-column="${escapeHtml(col)}" data-table="${tableId}" style="cursor: pointer; user-select: none; position: relative;">`;
      html += `<span class="header-text">${escapeHtml(col)}</span>`;
      html += `<span class="sort-indicator"><i class="bi bi-arrow-down-up" style="opacity: 0.3; margin-left: 5px;"></i></span>`;
      html += `<div class="resize-handle" style="position: absolute; right: 0; top: 0; bottom: 0; width: 5px; cursor: col-resize; background: transparent;"></div>`;
      html += `</th>`;
    });
    html += `</tr></thead><tbody>`;

    // Rows
    rows.forEach(row => {
      html += `<tr>`;
      columns.forEach(col => {
        const value = row[col] || '';
        const displayVal = escapeHtml(String(value));
        html += `<td title="${displayVal}">${displayVal}</td>`;
      });
      html += `</tr>`;
    });

    html += `</tbody></table></div></div>`;
    return html;
  }

  // Add sorting, resizing, and tap-to-expand interactivity to playbook tables
  function addPlaybookTableInteractivity(columns, rows) {
    const table = document.querySelector('#playbookTable');
    if (!table) return;

    const viewport = table.closest('.playbook-table-viewport');
    let sortState = { column: null, direction: 'asc' };
    let tableData = rows;

    // Add sorting
    const headers = table.querySelectorAll('.sortable-header');
    headers.forEach((header, colIndex) => {
      const headerText = header.querySelector('.header-text');
      const resizeHandle = header.querySelector('.resize-handle');
      const column = header.dataset.column;

      // Sorting - click on header (but not resize handle)
      header.addEventListener('click', (e) => {
        if (e.target.closest('.resize-handle')) return;
        e.stopPropagation();

        // Toggle sort direction
        if (sortState.column === column) {
          sortState.direction = sortState.direction === 'asc' ? 'desc' : 'asc';
        } else {
          sortState.column = column;
          sortState.direction = 'asc';
        }

        // Sort data
        tableData = sortPlaybookData(tableData, column, sortState.direction);

        // Update table body
        const tbody = table.querySelector('tbody');
        tbody.innerHTML = '';
        tableData.forEach(row => {
          let tr = document.createElement('tr');
          columns.forEach(col => {
            let td = document.createElement('td');
            const value = row[col] || '';
            td.textContent = String(value);
            td.title = String(value);
            tr.appendChild(td);
          });
          tbody.appendChild(tr);
        });

        // Update sort indicators
        headers.forEach(h => {
          const indicator = h.querySelector('.sort-indicator');
          if (h.dataset.column === column) {
            const icon = sortState.direction === 'asc' ? 'bi-arrow-up' : 'bi-arrow-down';
            indicator.innerHTML = `<i class="bi ${icon}" style="margin-left: 5px; color: var(--brand);"></i>`;
          } else {
            indicator.innerHTML = '<i class="bi bi-arrow-down-up" style="opacity: 0.3; margin-left: 5px;"></i>';
          }
        });

        // Re-add mobile tap handlers
        addMobileTapHandlers();
      });

      // Column resizing
      let isResizing = false;
      let startX = 0;
      let startWidth = 0;

      resizeHandle.addEventListener('mousedown', (e) => {
        e.preventDefault();
        e.stopPropagation();
        isResizing = true;
        startX = e.clientX;
        startWidth = header.offsetWidth;

        document.addEventListener('mousemove', handleResize);
        document.addEventListener('mouseup', stopResize);

        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'col-resize';
      });

      function handleResize(e) {
        if (!isResizing) return;
        e.preventDefault();

        const diff = e.clientX - startX;
        const newWidth = Math.max(50, startWidth + diff);

        const colGroup = table.querySelector('colgroup');
        const col = colGroup.children[colIndex];
        if (col) col.style.width = newWidth + 'px';
      }

      function stopResize() {
        isResizing = false;
        document.body.style.userSelect = '';
        document.body.style.cursor = '';
        document.removeEventListener('mousemove', handleResize);
        document.removeEventListener('mouseup', stopResize);
      }
    });

    // Mobile: tap toggles expansion
    function addMobileTapHandlers() {
      const supportsHover = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
      if (!supportsHover) {
        const rows = table.querySelectorAll('tbody tr');
        rows.forEach(tr => {
          tr.addEventListener('click', () => tr.classList.toggle('expanded'));
        });
      }
    }
    addMobileTapHandlers();
  }

  // Sort playbook table data
  function sortPlaybookData(data, column, direction) {
    return [...data].sort((a, b) => {
      let aVal = a[column] ?? '';
      let bVal = b[column] ?? '';

      // Handle Date column
      if (column === 'Date') {
        aVal = new Date(aVal);
        bVal = new Date(bVal);
      }
      // Handle Time column
      else if (column === 'Time') {
        aVal = parseTime(aVal);
        bVal = parseTime(bVal);
      }
      // Handle Identifier column (numeric)
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

  // Helper function to check if user is near bottom of scroll
  function isNearBottom(container, threshold = 150) {
    return container.scrollHeight - container.scrollTop - container.clientHeight < threshold;
  }

  // Smart auto-scroll: only scroll if user is near bottom
  function smartScroll(container) {
    if (isNearBottom(container)) {
      container.scrollTop = container.scrollHeight;
    }
  }

  // REMOVED: Old handlePlaybook() function (replaced by handlePlaybookWithFilters() at line ~1328)

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
  if (sendChatBtn) sendChatBtn.addEventListener('click', handleChat);
  if (userInput) {
    // Handle Enter key for textarea: Enter sends, Shift+Enter adds newline
    userInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleChat();
      }
    });

    // Auto-resize textarea as user types
    userInput.addEventListener('input', () => {
      userInput.style.height = 'auto';
      userInput.style.height = userInput.scrollHeight + 'px';
    });
  }

  async function handleChat(){
    const message = userInput.value.trim();
    if (!message) return;
    userInput.value = '';

    // Hide greeting on first message
    const aiGreeting = document.getElementById('aiGreeting');
    if (aiGreeting) {
      aiGreeting.style.display = 'none';
    }

    // Add user message to chat
    appendToChat(`
      <div class="d-flex justify-content-end mb-2">
        <div class="bg-primary text-white rounded p-2" style="max-width:80%;">${escapeHtml(message)}</div>
      </div>`);

    // Store user message temporarily (will be paired with AI response)
    const userMessage = message;

    try {
      // Generate unique ID for this response
      const responseId = 'chat-content-' + Date.now();

      // Add loading message
      appendToChat(`
        <div class="d-flex justify-content-start mb-2">
          <div class="bg-light border rounded p-3" style="max-width:90%;">
            <span class="spinner-border spinner-border-sm me-2" role="status"></span>
            <div id="${responseId}" class="chat-stream">Thinking...</div>
          </div>
        </div>`);

      // Build filters from chat scope selector
      const drugFilters = activeChatScope.type === 'drug' ? [activeChatScope.value] : [];
      const taFilters = activeChatScope.type === 'ta' ? [activeChatScope.value] : [];

      // Call streaming chat API with conversation history
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: message,
          drug_filters: drugFilters,
          ta_filters: taFilters,
          session_filters: [],
          date_filters: [],
          conversation_history: conversationHistory
        })
      });

      if (!response.ok) throw new Error('Chat request failed');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let out = '';            // accumulated assistant text

      const contentDiv = document.getElementById(responseId);
      contentDiv.textContent = '';  // clear "Thinking..." safely

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
              const parsed = JSON.parse(dataStr);

              if (parsed.table) {
                // Handle entity table (HTML already formatted) - insert INSIDE message bubble
                contentDiv.insertAdjacentHTML('beforeend', parsed.table);

                // Create a text div for the AI response AFTER the table
                if (!document.getElementById(responseId + '-text')) {
                  contentDiv.insertAdjacentHTML('beforeend', '<div id="' + responseId + '-text" class="mt-3"></div>');
                }
                chatContainer.scrollTop = chatContainer.scrollHeight;
              } else if (parsed.text) {
                // Handle regular text events
                out += parsed.text;

                // Check if we have a text div (created after table)
                const textDiv = document.getElementById(responseId + '-text');
                if (textDiv) {
                  // Text goes in dedicated div (after table)
                  textDiv.innerHTML = formatAIText(out);
                } else {
                  // No table, text goes directly in contentDiv
                  contentDiv.innerHTML = formatAIText(out);
                }
                chatContainer.scrollTop = chatContainer.scrollHeight;
              }
            } catch (e) {
              // Skip malformed JSON
              console.error('JSON parse error:', e);
            }
          }
        }
      }

      // Add conversation pair to history (backend expects {user: ..., assistant: ...} format)
      conversationHistory.push({ user: userMessage, assistant: out });

      // Limit conversation history to last 5 exchanges (10 messages total: 5 user + 5 AI)
      if (conversationHistory.length > 5) {
        conversationHistory = conversationHistory.slice(-5);
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

  // ===== Download Conversation =====
  const downloadChatBtn = document.getElementById('downloadChatBtn');
  if (downloadChatBtn) {
    downloadChatBtn.addEventListener('click', downloadConversation);
  }

  function downloadConversation() {
    // Extract conversation from chat container
    const chatMessages = chatContainer.querySelectorAll('.d-flex');
    if (chatMessages.length === 0) {
      alert('No conversation to download yet.');
      return;
    }

    let conversation = 'ESMO 2025 Conference Intelligence - Conversation Export\n';
    conversation += '=' .repeat(60) + '\n';
    conversation += `Date: ${new Date().toLocaleDateString()} ${new Date().toLocaleTimeString()}\n`;
    conversation += '=' .repeat(60) + '\n\n';

    chatMessages.forEach((msg, index) => {
      const isUser = msg.classList.contains('justify-content-end');
      const msgDiv = msg.querySelector('div:not(.spinner-border)');
      if (!msgDiv) return;

      const text = msgDiv.innerText || msgDiv.textContent;
      if (!text.trim()) return;

      if (isUser) {
        conversation += `USER:\n${text}\n\n`;
      } else {
        conversation += `AI ASSISTANT:\n${text}\n\n`;
      }
      conversation += '-'.repeat(60) + '\n\n';
    });

    // Create blob and download
    const blob = new Blob([conversation], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ESMO2025_Conversation_${new Date().toISOString().slice(0,10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // ===== Utilities =====
  function escapeHtml(text){ const div = document.createElement('div'); div.textContent = text ?? ''; return div.innerHTML; }
  function debounce(fn, wait){ let t; return (...args)=>{ clearTimeout(t); t = setTimeout(()=>fn.apply(this,args), wait); }; }

  // Format AI text with line breaks and basic formatting
  function formatAIText(text) {
    if (!text) return '';
    // Escape HTML first
    let formatted = escapeHtml(text);
    // Convert double line breaks to paragraphs
    formatted = formatted.replace(/\n\n/g, '<br><br>');
    // Convert single line breaks to br
    formatted = formatted.replace(/\n/g, '<br>');
    // Bold text (**text** → <strong>text</strong>)
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Italic text (*text* → <em>text</em>)
    formatted = formatted.replace(/\*(.*?)\*/g, '<em>$1</em>');
    return formatted;
  }

  function renderCellContent(val) {
    // Check if content contains search highlighting
    if (typeof val === 'string' && val.includes('<mark')) {
      // Sanitize: only allow mark tags with specific styling
      return val.replace(/<mark[^>]*>/g, '<mark style="background-color: yellow; padding: 1px 2px; border-radius: 2px;">').replace(/<\/mark>/g, '</mark>');
    }
    // Otherwise escape HTML
    return escapeHtml(val);
  }

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

  // ===== Quick Intelligence Modal & Chat Scope Selector =====

  const quickIntelModal = document.getElementById('quickIntelModal');
  const modalIcon = document.getElementById('modalIcon');
  const modalTitle = document.getElementById('modalTitle');
  const modalInstructions = document.getElementById('modalInstructions');
  const modalDrugSection = document.getElementById('modalDrugSection');
  const modalTASection = document.getElementById('modalTASection');
  const modalSelectedFilter = document.getElementById('modalSelectedFilter');
  const modalSelectedFilterText = document.getElementById('modalSelectedFilterText');
  const chatScopeDropdown = document.getElementById('chatScopeDropdown');

  let pendingPlaybookType = null;
  let selectedFilterType = null; // 'drug' or 'ta'
  let selectedFilterValue = null;

  // Button configurations: which filters to show for each playbook
  const playbookConfig = {
    competitor: {
      icon: '🏆',
      title: 'Competitor Intelligence',
      filters: ['drug'], // Drug only
      instruction: 'Select a drug to analyze:'
    },
    kol: {
      icon: '👥',
      title: 'KOL Analysis',
      filters: ['drug', 'ta'], // Drug OR TA (pick one)
      instruction: 'Select a drug or therapeutic area:'
    },
    institution: {
      icon: '🏥',
      title: 'Institution Analysis',
      filters: ['ta'], // TA only
      instruction: 'Select a therapeutic area:'
    },
    insights: {
      icon: '📈',
      title: 'Strategic Insights',
      filters: ['drug', 'ta'], // Drug OR TA (pick one)
      instruction: 'Select a drug or therapeutic area:'
    },
    strategy: {
      icon: '📋',
      title: 'Strategic Recommendations',
      filters: ['drug'], // Drug only
      instruction: 'Select a drug to analyze:'
    }
  };

  // Show modal when playbook button is clicked
  playbookTriggers.forEach(el => {
    el.addEventListener('click', () => {
      const playbookType = el.getAttribute('data-playbook');
      pendingPlaybookType = playbookType;
      selectedFilterType = null;
      selectedFilterValue = null;

      const config = playbookConfig[playbookType];

      // Update modal title/icon
      modalIcon.textContent = config.icon;
      modalTitle.textContent = config.title;
      modalInstructions.textContent = config.instruction;

      // Show/hide filter sections based on config
      modalDrugSection.style.display = config.filters.includes('drug') ? 'block' : 'none';
      modalTASection.style.display = config.filters.includes('ta') ? 'block' : 'none';
      modalSelectedFilter.style.display = 'none';

      // Reset active states
      document.querySelectorAll('.modal-filter-btn').forEach(btn => btn.classList.remove('active'));

      // Show modal
      const modal = new bootstrap.Modal(quickIntelModal);
      modal.show();
    });
  });

  // Handle filter button clicks (auto-run on selection)
  document.querySelectorAll('.modal-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const filterType = btn.dataset.type;
      const filterValue = btn.dataset.value;

      // Mark as selected
      document.querySelectorAll('.modal-filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      selectedFilterType = filterType;
      selectedFilterValue = filterValue;

      // Show selected filter
      modalSelectedFilter.style.display = 'block';
      modalSelectedFilterText.textContent = btn.textContent;

      // Auto-run analysis after brief delay (allows user to see selection)
      setTimeout(() => {
        runPlaybookAnalysis();
      }, 300);
    });
  });

  function runPlaybookAnalysis() {
    if (!pendingPlaybookType || !selectedFilterValue) return;

    // Build filter arrays
    const drugFilters = selectedFilterType === 'drug' ? [selectedFilterValue] : [];
    const taFilters = selectedFilterType === 'ta' ? [selectedFilterValue] : [];

    // Close modal
    const modal = bootstrap.Modal.getInstance(quickIntelModal);
    modal.hide();

    // Run playbook with filters
    handlePlaybookWithFilters(pendingPlaybookType, drugFilters, taFilters, []);

    // Reset state
    pendingPlaybookType = null;
    selectedFilterType = null;
    selectedFilterValue = null;
  }

  async function handlePlaybookWithFilters(playbookType, drugFilters, taFilters, dateFilters) {
    try {
      // Hide greeting on first playbook click
      const aiGreeting = document.getElementById('aiGreeting');
      if (aiGreeting) {
        aiGreeting.style.display = 'none';
      }

      // Ensure AI tab is visible
      const aiTabBtn = document.getElementById('ai-assistant-tab');
      if (window.bootstrap && aiTabBtn) new bootstrap.Tab(aiTabBtn).show();

      // Show filter context in user message
      const filterLabels = [];
      if (drugFilters.length > 0) filterLabels.push(`💊 ${drugFilters.join(', ')}`);
      if (taFilters.length > 0) filterLabels.push(`🎯 ${taFilters.join(', ')}`);
      if (dateFilters.length > 0) filterLabels.push(`📅 ${dateFilters.join(', ')}`);
      const filterText = filterLabels.length > 0 ? ` (${filterLabels.join(' • ')})` : '';

      appendToChat(`
        <div class="d-flex justify-content-start mb-2">
          <div class="bg-primary text-white rounded p-2" style="max-width:80%;">
            <strong>🤖 Running ${getPlaybookTitle(playbookType)}${filterText}...</strong>
            <span class="spinner-border spinner-border-sm ms-2" role="status"></span>
          </div>
        </div>`);

      // Scroll to bottom immediately when button clicked (with slight delay for DOM update)
      setTimeout(() => {
        if (chatContainer) {
          chatContainer.scrollTop = chatContainer.scrollHeight;
        }
      }, 100);

      const params = new URLSearchParams();
      drugFilters.forEach(f => params.append('drug_filters', f));
      taFilters.forEach(f => params.append('ta_filters', f));
      dateFilters.forEach(f => params.append('date_filters', f));

      const response = await fetch(`/api/playbook/${playbookType}/stream?${params}`);
      if (!response.ok) throw new Error('Playbook request failed');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let out = '';

      // Generate unique IDs for this playbook response to avoid conflicts
      const playbookId = 'playbook-content-' + Date.now();
      const playbookTextId = 'playbook-text-' + Date.now();

      appendToChat(`
        <div class="d-flex justify-content-start mb-2">
          <div class="bg-light border rounded p-3" style="max-width:90%;">
            <div id="${playbookId}" class="chat-stream"></div>
          </div>
        </div>`);

      const contentDiv = document.getElementById(playbookId);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (line.startsWith('event: ')) continue;
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6);
            if (dataStr === '[DONE]') continue;
            try {
              const parsed = JSON.parse(dataStr);

              // Handle table event (backend sends {title, columns, rows})
              if (parsed.title && parsed.columns && parsed.rows) {
                const tableHtml = createTableHTML(parsed.title, parsed.subtitle || '', parsed.columns, parsed.rows);

                // Check if text div already exists (from previous table)
                let textDiv = document.getElementById(playbookTextId);
                if (!textDiv) {
                  // First table - append table using insertAdjacentHTML to preserve content
                  contentDiv.insertAdjacentHTML('beforeend', tableHtml);
                  // Create text div for AI response
                  contentDiv.insertAdjacentHTML('beforeend', '<div class="mt-3" id="' + playbookTextId + '"></div>');
                } else {
                  // Subsequent tables - insert BEFORE the text div
                  textDiv.insertAdjacentHTML('beforebegin', tableHtml);
                }

                // Add interactivity to the last table added
                addPlaybookTableInteractivity(parsed.columns, parsed.rows);

                chatContainer.scrollTop = chatContainer.scrollHeight;
              }
              // Handle text event
              else if (parsed.text) {
                // Check if we have a separate text div (after table)
                let textDiv = document.getElementById(playbookTextId);
                if (textDiv) {
                  out += parsed.text;
                  textDiv.innerHTML = formatAIText(out) + '<span class="cursor-blink">▊</span>';
                } else {
                  // No table yet, create text div first then populate
                  if (!document.getElementById(playbookTextId)) {
                    contentDiv.insertAdjacentHTML('beforeend', '<div id="' + playbookTextId + '"></div>');
                  }
                  textDiv = document.getElementById(playbookTextId);
                  out += parsed.text;
                  textDiv.innerHTML = formatAIText(out) + '<span class="cursor-blink">▊</span>';
                }
                chatContainer.scrollTop = chatContainer.scrollHeight;
              }

            } catch (err) {
              console.warn('Parse error:', err);
            }
          }
        }
      }

      // Finalize - remove blinking cursor
      const textDiv = document.getElementById(playbookTextId);
      if (textDiv) {
        textDiv.innerHTML = formatAIText(out);
      } else {
        contentDiv.innerHTML = formatAIText(out);
      }
      chatContainer.scrollTop = chatContainer.scrollHeight;

    } catch (error) {
      console.error('Playbook error:', error);
      appendToChat('<div class="alert alert-danger">Error running analysis. Please try again.</div>');
    }
  }

  // Chat Scope Selector - Apply to chat requests
  let activeChatScope = { type: 'all', value: null };

  chatScopeDropdown.addEventListener('change', () => {
    const selected = chatScopeDropdown.value;
    if (selected === 'all') {
      activeChatScope = { type: 'all', value: null };
    } else if (selected.startsWith('drug:')) {
      activeChatScope = { type: 'drug', value: selected.replace('drug:', '') };
    } else if (selected.startsWith('ta:')) {
      activeChatScope = { type: 'ta', value: selected.replace('ta:', '') };
    }
  });

  // Hide filter sidebar when on AI Assistant tab (use class toggle instead of style changes)
  // Listen to ALL tab buttons (both appbar tabs and hidden nav-tabs)
  const allTabButtons = document.querySelectorAll('[data-bs-toggle="tab"]');

  console.log('[SIDEBAR DEBUG] Found tab buttons:', allTabButtons.length);

  function handleTabSwitch(target) {
    if (target === '#data-explorer') {
      console.log('[SIDEBAR DEBUG] 📊 Data Explorer tab shown - showing filter sidebar');
      document.body.classList.remove('ai-tab-active');
      document.body.classList.add('data-tab-active');
    } else if (target === '#ai-assistant') {
      console.log('[SIDEBAR DEBUG] 🤖 AI Assistant tab shown - hiding filter sidebar');
      document.body.classList.remove('data-tab-active');
      document.body.classList.add('ai-tab-active');
    }
    console.log('[SIDEBAR DEBUG] Body classes:', document.body.className);
  }

  // Listen to all tab buttons
  allTabButtons.forEach(button => {
    button.addEventListener('shown.bs.tab', (event) => {
      const target = event.target.getAttribute('data-bs-target');
      handleTabSwitch(target);
    });
  });

  // Set initial class on page load
  const activeTab = document.querySelector('.appbar-tab.active');
  if (activeTab) {
    const target = activeTab.getAttribute('data-bs-target');
    console.log('[SIDEBAR DEBUG] Initial active tab:', target);
    handleTabSwitch(target);
  }

});
