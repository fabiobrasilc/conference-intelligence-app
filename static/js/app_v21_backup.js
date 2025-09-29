// ESMO 2025 Inline Filter JavaScript
document.addEventListener('DOMContentLoaded', function() {

    // --- Element References ---
    const drugFilterCheckboxes = document.querySelectorAll('.drug-filter-checkbox');
    const taFilterCheckboxes = document.querySelectorAll('.ta-filter-checkbox');
    const searchInput = document.getElementById('searchInput');
    const searchBtn = document.getElementById('searchBtn');
    const exportBtn = document.getElementById('exportBtn');
    const filterContext = document.getElementById('filterContext');
    const tableContainer = document.getElementById('tableContainer');

    // AI Tab elements
    const aiDrugFilterCheckboxes = document.querySelectorAll('.ai-drug-filter-checkbox');
    const aiTaFilterCheckboxes = document.querySelectorAll('.ai-ta-filter-checkbox');
    const aiFilterContext = document.getElementById('aiFilterContext');
    const playbookButtons = document.querySelectorAll('.playbook-button');
    const chatContainer = document.getElementById('chatContainer');
    const userInput = document.getElementById('userInput');
    const sendChatBtn = document.getElementById('sendChatBtn');

    // --- State Management ---
    let currentFilters = {
        drug_filters: [],
        ta_filters: []
    };

    // --- Initialize App ---
    loadData();

    // --- Helper Functions ---
    function getSelectedCheckboxValues(checkboxes) {
        return Array.from(checkboxes)
            .filter(cb => cb.checked)
            .map(cb => cb.value);
    }

    function setCheckboxValues(checkboxes, values) {
        checkboxes.forEach(cb => {
            cb.checked = values.includes(cb.value);
        });
    }

    function updateCurrentFilters() {
        currentFilters.drug_filters = getSelectedCheckboxValues(drugFilterCheckboxes);
        currentFilters.ta_filters = getSelectedCheckboxValues(taFilterCheckboxes);
    }

    function syncAIFilters() {
        setCheckboxValues(aiDrugFilterCheckboxes, currentFilters.drug_filters);
        setCheckboxValues(aiTaFilterCheckboxes, currentFilters.ta_filters);
        updateAIFilterContext();
    }

    function syncDataFilters() {
        setCheckboxValues(drugFilterCheckboxes, currentFilters.drug_filters);
        setCheckboxValues(taFilterCheckboxes, currentFilters.ta_filters);
    }

    // --- Event Listeners ---
    drugFilterCheckboxes.forEach(cb => {
        cb.addEventListener('change', handleFilterChange);
    });
    taFilterCheckboxes.forEach(cb => {
        cb.addEventListener('change', handleFilterChange);
    });
    searchInput.addEventListener('input', debounce(handleLiveSearch, 300));
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSearch();
    });
    searchBtn.addEventListener('click', handleSearch);
    exportBtn.addEventListener('click', handleExport);

    // AI Tab filter sync
    aiDrugFilterCheckboxes.forEach(cb => {
        cb.addEventListener('change', syncFiltersFromAI);
    });
    aiTaFilterCheckboxes.forEach(cb => {
        cb.addEventListener('change', syncFiltersFromAI);
    });

    // Playbook buttons
    playbookButtons.forEach(btn => {
        btn.addEventListener('click', (e) => handlePlaybook(e.target.dataset.playbook));
    });

    // Chat functionality
    sendChatBtn.addEventListener('click', handleChat);
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleChat();
    });

    // --- Filter Management ---
    function handleFilterChange() {
        updateCurrentFilters();
        syncAIFilters();
        loadData();
    }

    function syncFiltersFromAI() {
        currentFilters.drug_filters = getSelectedCheckboxValues(aiDrugFilterCheckboxes);
        currentFilters.ta_filters = getSelectedCheckboxValues(aiTaFilterCheckboxes);
        syncDataFilters();
        loadData();
        updateAIFilterContext();
    }

    function updateAIFilterContext() {
        const drugSummary = currentFilters.drug_filters.length > 0 ? currentFilters.drug_filters.join(', ') : 'All Drugs';
        const taSummary = currentFilters.ta_filters.length > 0 ? currentFilters.ta_filters.join(', ') : 'All Therapeutic Areas';
        const summary = `Analyzing: ${drugSummary} + ${taSummary}`;
        aiFilterContext.textContent = summary;
    }

    // --- Data Loading ---
    async function loadData() {
        try {
            showLoading();

            const params = new URLSearchParams();

            // Only add filters if they are selected, otherwise show all data
            if (currentFilters.drug_filters.length > 0) {
                currentFilters.drug_filters.forEach(filter => {
                    params.append('drug_filters', filter);
                });
            }

            if (currentFilters.ta_filters.length > 0) {
                currentFilters.ta_filters.forEach(filter => {
                    params.append('ta_filters', filter);
                });
            }

            const response = await fetch(`/api/data?${params}`);
            const data = await response.json();

            if (data.error) {
                throw new Error(data.error);
            }

            renderTable(data.data);
            updateFilterContext(data.filter_context);

        } catch (error) {
            console.error('Error loading data:', error);
            showError('Failed to load ESMO data');
        }
    }

    function showLoading() {
        tableContainer.innerHTML = `
            <div class="text-center py-4">
                <div class="spinner-border" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-2">Loading ESMO 2025 data...</p>
            </div>
        `;
    }

    function showError(message) {
        tableContainer.innerHTML = `
            <div class="alert alert-danger" role="alert">
                <h4 class="alert-heading">Error</h4>
                <p>${message}</p>
            </div>
        `;
    }

    // --- Table Rendering ---
    function renderTable(data) {
        if (!data || data.length === 0) {
            tableContainer.innerHTML = `
                <div class="alert alert-info" role="alert">
                    <h4 class="alert-heading">No Results</h4>
                    <p>No sessions found with current filters. Try adjusting your selection.</p>
                </div>
            `;
            return;
        }

        const headers = ['main_filters', 'session_category', 'date', 'time', 'room', 'session_type', 'identifier', 'study_title', 'speaker', 'location', 'affiliation'];
        const headerLabels = ['main_filters', 'session_category', 'date', 'time', 'room', 'session_type', 'identifier', 'study_title', 'speaker', 'location', 'affiliation'];

        let html = `
            <div class="table-responsive">
                <table class="table table-striped table-hover">
                    <thead class="table-dark">
                        <tr>
                            ${headerLabels.map(h => `<th>${h}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>
        `;

        data.forEach(row => {
            html += '<tr>';
            headers.forEach((header, index) => {
                const value = row[header] || '';

                // Show full text without truncation, but keep hover tooltip
                html += `<td title="${escapeHtml(value)}">${escapeHtml(value)}</td>`;
            });
            html += '</tr>';
        });

        html += '</tbody></table></div>';
        tableContainer.innerHTML = html;
    }

    function updateFilterContext(context) {
        if (!context) return;

        const { total_sessions, total_available, filter_summary } = context;
        const percentage = total_available > 0 ? Math.round((total_sessions / total_available) * 100) : 0;

        filterContext.innerHTML = `
            Showing <strong>${total_sessions.toLocaleString()}</strong> of
            <strong>${total_available.toLocaleString()}</strong> sessions
            (${percentage}%) • ${filter_summary}
        `;

        // Update export button text
        exportBtn.innerHTML = `📁 Download Table (${total_sessions.toLocaleString()} results, ${filter_summary})`;
    }


    // --- Search Functionality ---
    function handleLiveSearch() {
        const query = searchInput.value.trim();

        // Only trigger live search for 3+ characters
        if (query.length >= 3) {
            handleSearch();
        } else if (query.length === 0) {
            // Reset to filtered data when search is cleared
            loadData();
        }
        // For 1-2 characters, do nothing (don't search)
    }

    async function handleSearch() {
        const query = searchInput.value.trim();
        if (!query) {
            loadData(); // Reset to filtered data
            return;
        }

        try {
            showLoading();

            const params = new URLSearchParams();
            params.append('keyword', query);

            // Only add filters if they are selected
            if (currentFilters.drug_filters.length > 0) {
                currentFilters.drug_filters.forEach(filter => {
                    params.append('drug_filters', filter);
                });
            }

            if (currentFilters.ta_filters.length > 0) {
                currentFilters.ta_filters.forEach(filter => {
                    params.append('ta_filters', filter);
                });
            }

            const response = await fetch(`/api/search?${params}`);
            const data = await response.json();

            if (data.error) {
                throw new Error(data.error);
            }

            renderTable(data);

            // Update filter context to show search results with count
            const drugSummary = currentFilters.drug_filters.length > 0 ? currentFilters.drug_filters.join(', ') : 'All Drugs';
            const taSummary = currentFilters.ta_filters.length > 0 ? currentFilters.ta_filters.join(', ') : 'All Therapeutic Areas';
            filterContext.innerHTML = `
                Search results for "<strong>${escapeHtml(query)}</strong>" •
                <strong>${data.length.toLocaleString()}</strong> sessions found •
                Filters: ${drugSummary} + ${taSummary}
            `;

            // Update export button for search results
            exportBtn.innerHTML = `📁 Download Table (${data.length.toLocaleString()} search results, ${drugSummary} + ${taSummary})`;

        } catch (error) {
            console.error('Search error:', error);
            showError('Search failed. Please try again.');
        }
    }

    // --- Export Functionality ---
    async function handleExport() {
        try {
            exportBtn.disabled = true;
            exportBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Exporting...';

            const params = new URLSearchParams();
            params.append('format', 'csv');

            // Only add filters if they are selected
            if (currentFilters.drug_filters.length > 0) {
                currentFilters.drug_filters.forEach(filter => {
                    params.append('drug_filters', filter);
                });
            }

            if (currentFilters.ta_filters.length > 0) {
                currentFilters.ta_filters.forEach(filter => {
                    params.append('ta_filters', filter);
                });
            }

            const response = await fetch('/api/export', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    drug_filters: currentFilters.drug_filters,
                    ta_filters: currentFilters.ta_filters,
                    format: 'csv'
                })
            });

            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                const drugFilename = currentFilters.drug_filters.join('_').replace(/ /g, '_');
                const taFilename = currentFilters.ta_filters.join('_').replace(/ /g, '_');
                a.download = `esmo2025_${drugFilename}_${taFilename}.csv`;
                a.click();
                window.URL.revokeObjectURL(url);
            } else {
                throw new Error('Export failed');
            }

        } catch (error) {
            console.error('Export error:', error);
            alert('Export failed. Please try again.');
        } finally {
            exportBtn.disabled = false;
            exportBtn.innerHTML = '📁 Export';
        }
    }

    // --- Playbook Functionality ---
    async function handlePlaybook(playbookType) {
        try {
            // Switch to AI Assistant tab
            const aiTab = document.getElementById('ai-assistant-tab');
            const bootstrap = window.bootstrap || window.bootstrap;
            if (bootstrap) {
                const tab = new bootstrap.Tab(aiTab);
                tab.show();
            }

            // Clear chat and show loading
            appendToChatContainer(`
                <div class="mb-3">
                    <div class="d-flex justify-content-start">
                        <div class="bg-primary text-white rounded p-2 max-width-80">
                            <strong>🤖 Running ${getPlaybookTitle(playbookType)}...</strong>
                            <div class="spinner-border spinner-border-sm ms-2" role="status"></div>
                        </div>
                    </div>
                </div>
            `);

            // Call playbook API
            const params = new URLSearchParams();

            // Add multiple drug filters
            currentFilters.drug_filters.forEach(filter => {
                params.append('drug_filters', filter);
            });

            // Add multiple TA filters
            currentFilters.ta_filters.forEach(filter => {
                params.append('ta_filters', filter);
            });

            const response = await fetch(`/api/playbook/${playbookType}/stream?${params}`);
            if (!response.ok) throw new Error('Playbook request failed');

            // Handle streaming response
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            appendToChatContainer(`
                <div class="mb-3" id="playbook-response">
                    <div class="d-flex justify-content-start">
                        <div class="bg-light border rounded p-3 max-width-90">
                            <div id="playbook-content"></div>
                        </div>
                    </div>
                </div>
            `);

            const contentDiv = document.getElementById('playbook-content');

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // Keep incomplete line in buffer

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.slice(6);
                        if (data === '[DONE]') continue;

                        try {
                            const parsed = JSON.parse(data);
                            if (parsed.text) {
                                contentDiv.innerHTML += escapeHtml(parsed.text);
                                chatContainer.scrollTop = chatContainer.scrollHeight;
                            }
                        } catch (e) {
                            // Ignore malformed JSON
                        }
                    }
                }
            }

        } catch (error) {
            console.error('Playbook error:', error);
            appendToChatContainer(`
                <div class="mb-3">
                    <div class="d-flex justify-content-start">
                        <div class="bg-danger text-white rounded p-2">
                            Error running ${getPlaybookTitle(playbookType)}: ${error.message}
                        </div>
                    </div>
                </div>
            `);
        }
    }

    function getPlaybookTitle(type) {
        const titles = {
            'competitor': 'Competitor Intelligence',
            'kol': 'KOL Analysis',
            'institution': 'Institution Analysis',
            'insights': 'Insights & Trends',
            'strategy': 'Strategic Recommendations'
        };
        return titles[type] || type;
    }

    // --- Chat Functionality ---
    async function handleChat() {
        const message = userInput.value.trim();
        if (!message) return;

        userInput.value = '';

        // Add user message
        appendToChatContainer(`
            <div class="mb-3">
                <div class="d-flex justify-content-end">
                    <div class="bg-primary text-white rounded p-2 max-width-80">
                        ${escapeHtml(message)}
                    </div>
                </div>
            </div>
        `);

        try {
            // TODO: Implement chat API call
            appendToChatContainer(`
                <div class="mb-3">
                    <div class="d-flex justify-content-start">
                        <div class="bg-light border rounded p-2 max-width-80">
                            Chat functionality coming soon! Use the Quick Intelligence buttons above for analysis.
                        </div>
                    </div>
                </div>
            `);

        } catch (error) {
            console.error('Chat error:', error);
            appendToChatContainer(`
                <div class="mb-3">
                    <div class="d-flex justify-content-start">
                        <div class="bg-danger text-white rounded p-2">
                            Error: ${error.message}
                        </div>
                    </div>
                </div>
            `);
        }
    }

    function appendToChatContainer(html) {
        chatContainer.innerHTML += html;
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }


    // --- Utility Functions ---
    function truncateText(text, maxLength) {
        if (!text || text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    // --- CSS for chat styling ---
    const style = document.createElement('style');
    style.textContent = `
        .max-width-80 { max-width: 80%; }
        .max-width-90 { max-width: 90%; }
        #chatContainer { background-color: #f8f9fa; }
    `;
    document.head.appendChild(style);

});