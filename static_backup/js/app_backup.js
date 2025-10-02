// static/js/app.js (Confirm this is the current content)

document.addEventListener('DOMContentLoaded', function() {

    // --- Get references to HTML elements ---
    const taFilterCheckboxes = document.querySelectorAll('.ta-filter-checkbox');
    const filterInfo = document.getElementById('filterInfo');
    const statusLine = document.getElementById('statusLine');
    const dataTableContainer = document.getElementById('data-table-container');
    const downloadButtonContainer = document.getElementById('download-button-container');
    const searchFieldSelect = document.getElementById('searchField');
    const keywordSearchInput = document.getElementById('keywordSearch');
    const searchButton = document.getElementById('searchButton');
    const searchResultsInfo = document.getElementById('search-results-info');

    // Chat elements
    const chatInput = document.getElementById('chat-input');
    const sendChatBtn = document.getElementById('send-button');
    const chatHistory = document.getElementById('chat-history');

    // Playbook buttons
    const playbookButtons = document.querySelectorAll('.playbook-button');

    // Tables container reference
    const tablesContainer = document.getElementById('tables-container');

    // Legacy loading spinner
    const loadingSpinner = document.createElement('div');
    loadingSpinner.className = 'loading-spinner legacy';

    let currentTaFilter = 'All'; // Default TA
    let currentSearch = { keyword: '', field: 'All' }; // Track current search state

    // Simple in-chat loading functions
    function addLoadingMessageToChat() {
        const loadingId = 'loading-' + Date.now();
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message assistant-message';
        messageDiv.id = loadingId;
        messageDiv.innerHTML = `
            <div class="chat-loading">
                <div class="chat-spinner"></div>
                <span>Generating response...</span>
            </div>
        `;

        if (chatHistory) {
            chatHistory.appendChild(messageDiv);
            chatHistory.scrollTop = chatHistory.scrollHeight;
        }

        return loadingId;
    }

    function removeLoadingMessage(loadingId) {
        const loadingElement = document.getElementById(loadingId);
        if (loadingElement) {
            loadingElement.remove();
        }
    }

    // --- Main Function to Display Data in a Table ---
    function displayData(data, filenamePrefix = 'data', isSearch = false) {
        console.log('displayData called with:', data ? data.length : 'null', 'items', 'isSearch:', isSearch);

        if (!dataTableContainer) {
            console.error('dataTableContainer not found!');
            return;
        }

        dataTableContainer.innerHTML = '';
        if (downloadButtonContainer) downloadButtonContainer.innerHTML = '';
        if (searchResultsInfo) searchResultsInfo.style.display = 'none';

        if (!data || data.length === 0) {
            dataTableContainer.innerHTML = '<p class="text-center mt-3">No data to display.</p>';
            if (isSearch) {
                searchResultsInfo.textContent = 'No results found for your search.';
                searchResultsInfo.className = 'alert alert-warning';
                searchResultsInfo.style.display = 'block';
            }
            return;
        }

        const table = document.createElement('table');
        table.className = 'table table-striped table-hover table-sm';
        const thead = document.createElement('thead');
        const tbody = document.createElement('tbody');
        table.appendChild(thead);
        table.appendChild(tbody);

        const headers = Object.keys(data[0]);
        const headerRow = document.createElement('tr');
        headers.forEach(headerText => {
            const th = document.createElement('th');
            th.textContent = headerText;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);

        const maxInitialRows = 50;
        const rowsToDisplay = isSearch ? data : data.slice(0, maxInitialRows); // Display all for search, limit for initial

        rowsToDisplay.forEach(rowData => {
            const row = document.createElement('tr');
            headers.forEach(header => {
                const td = document.createElement('td');
                let cellContent = rowData[header] || '';
                td.textContent = cellContent;
                if (typeof cellContent === 'string' && cellContent.length > 150) { // Truncate long strings
                    td.textContent = cellContent.substring(0, 150) + '...';
                    td.title = cellContent; // Show full content on hover
                }
                row.appendChild(td);
            });
            tbody.appendChild(row);
        });

        dataTableContainer.appendChild(table);

        const infoMessage = isSearch 
            ? `Found ${data.length} results.`
            : `Showing first ${rowsToDisplay.length} of ${data.length} total abstracts.`;
        
        searchResultsInfo.textContent = infoMessage;
        searchResultsInfo.className = 'alert alert-info';
        searchResultsInfo.style.display = 'block';

        // Update status line and filter info with counts
        if (statusLine) {
            statusLine.textContent = `Focus: ${currentTaFilter} • ${data.length.toLocaleString()} abstracts`;
        }
        if (filterInfo) {
            filterInfo.textContent = `🔍 ${data.length.toLocaleString()} abstracts`;
        }

        const csvData = Papa.unparse(data);
        const blob = new Blob([csvData], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const downloadLink = document.createElement('a');
        downloadLink.href = url;
        downloadLink.download = `${filenamePrefix}_${isSearch ? 'search_results' : 'data'}.csv`;
        downloadLink.className = 'btn btn-success download-button mt-2';
        downloadLink.textContent = `📥 Download Full Results (${data.length} rows)`;
        downloadButtonContainer.appendChild(downloadLink);
    }

    // --- Function to Fetch Data from the Backend ---
    function fetchData(endpoint, params = {}, isSearch = false) {
        dataTableContainer.innerHTML = '';
        dataTableContainer.appendChild(loadingSpinner);
        loadingSpinner.style.display = 'block';

        const url = new URL(endpoint, window.location.origin);
        Object.keys(params).forEach(key => url.searchParams.append(key, params[key]));

        fetch(url)
            .then(response => {
                console.log('Response status:', response.status);
                return response.json();
            })
            .then(data => {
                loadingSpinner.style.display = 'none';
                console.log('Received data:', data ? data.length : 'null', 'items');
                if (data.error) {
                    dataTableContainer.innerHTML = `<p class="text-danger text-center mt-3">Error: ${data.error}</p>`;
                } else if (!data || data.length === 0) {
                    dataTableContainer.innerHTML = `<p class="text-warning text-center mt-3">No data available.</p>`;
                } else {
                    displayData(data, params.ta, isSearch);
                }
            })
            .catch(error => {
                loadingSpinner.style.display = 'none';
                console.error('Fetch Error:', error);
                dataTableContainer.innerHTML = '<p class="text-danger text-center mt-3">A network error occurred. Please try again.</p>';
            });
    }

    // --- Add Chat Message to UI (for later use) ---
    function addChatMessage(role, content, tablesData = {}) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', role);
        messageDiv.innerHTML = content.replace(/\n/g, '<br>'); // Basic newline to <br>
        chatHistory.appendChild(messageDiv);

        // Handle attached tables
        for (const tableTitle in tablesData) {
            const tableContent = tablesData[tableTitle];
            if (tableContent && tableContent.length > 0) {
                const tableDiv = document.createElement('div');
                tableDiv.className = 'table-container';

                const tableTitleEl = document.createElement('h5');
                tableTitleEl.textContent = tableTitle;
                tableDiv.appendChild(tableTitleEl);

                // Render the table using PapaParse for display
                const csvData = Papa.unparse(tableContent);
                // PapaParse.parse can handle CSV string to data array
                const parsedData = Papa.parse(csvData, { header: true }).data; 
                
                const tableEl = document.createElement('table');
                tableEl.className = 'table table-sm table-striped';
                const theadEl = document.createElement('thead');
                const tbodyEl = document.createElement('tbody');
                tableEl.appendChild(theadEl);
                tableEl.appendChild(tbodyEl);

                const headers = Object.keys(parsedData[0]);
                const headerRowEl = document.createElement('tr');
                headers.forEach(header => {
                    const th = document.createElement('th');
                    th.textContent = header;
                    headerRowEl.appendChild(th);
                });
                theadEl.appendChild(headerRowEl);

                parsedData.forEach(rowData => {
                    const row = document.createElement('tr');
                    headers.forEach(header => {
                        const td = document.createElement('td');
                        td.textContent = rowData[header];
                        row.appendChild(td);
                    });
                    tbodyEl.appendChild(row);
                });
                tableDiv.appendChild(tableEl);

                // Add download button for this specific table
                const blob = new Blob([csvData], { type: 'text/csv' });
                const url = URL.createObjectURL(blob);
                const downloadLink = document.createElement('a');
                downloadLink.href = url;
                downloadLink.download = `${tableTitle.replace(/[^a-zA-Z0-9]/g, '_')}.csv`;
                downloadLink.className = 'btn btn-secondary btn-sm download-button';
                downloadLink.textContent = `📥 Download Table`;
                tableDiv.appendChild(downloadLink);

                messageDiv.appendChild(tableDiv);
            } else {
                 const noDataMsg = document.createElement('p');
                 noDataMsg.className = 'text-muted';
                 noDataMsg.textContent = `No data found for "${tableTitle}".`;
                 messageDiv.appendChild(noDataMsg);
            }
        }
        chatHistory.scrollTop = chatHistory.scrollHeight; // Scroll to bottom
    }


    // --- Event Handlers ---
    // TA Filter checkbox handler (mutually exclusive behavior)
    taFilterCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            if (this.checked) {
                // Uncheck all other checkboxes (mutually exclusive)
                taFilterCheckboxes.forEach(cb => {
                    if (cb !== this) cb.checked = false;
                });

                currentTaFilter = this.value;
                updateFilterInfo();
                updateStatusLine();

                // PERSISTENT SEARCH: If there's an active search, re-run it in the new filter
                if (currentSearch.keyword) {
                    console.log(`Filter changed to ${currentTaFilter}, re-running search for "${currentSearch.keyword}"`);
                    fetchData('/api/search', { ta: currentTaFilter, keyword: currentSearch.keyword, field: currentSearch.field }, true);
                } else {
                    // No active search, just load general data
                    fetchData('/api/data', { ta: currentTaFilter }, false);
                }
            } else {
                // If unchecking, revert to "All"
                document.getElementById('taFilter_All').checked = true;
                currentTaFilter = 'All';
                updateFilterInfo();
                updateStatusLine();

                // Re-run search or load data with "All" filter
                if (currentSearch.keyword) {
                    fetchData('/api/search', { ta: currentTaFilter, keyword: currentSearch.keyword, field: currentSearch.field }, true);
                } else {
                    fetchData('/api/data', { ta: currentTaFilter }, false);
                }
            }
        });
    });

    // Update filter info in sidebar
    function updateFilterInfo() {
        if (filterInfo) {
            filterInfo.textContent = `Loading ${currentTaFilter} data...`;
        }
    }

    // Update status line
    function updateStatusLine() {
        if (statusLine) {
            statusLine.textContent = `Focus: ${currentTaFilter} • Loading abstracts...`;
        }
    }

    // Playbook button handlers
    playbookButtons.forEach(button => {
        button.addEventListener('click', function() {
            const playbookKey = this.getAttribute('data-playbook');
            runPlaybook(playbookKey);
        });
    });

    // Function to run a playbook
    function runPlaybook(playbookKey) {
        const aiTab = document.getElementById('ai-tab');
        if (aiTab) {
            // Switch to AI Assistant tab
            const tabInstance = new bootstrap.Tab(aiTab);
            tabInstance.show();
        }

        // Add loading message to chat
        const playbookNames = {
            'competitor': 'Competitor Intelligence',
            'kol': 'KOL Analysis',
            'institution': 'Institution Analysis',
            'insights': 'Insights & Trends',
            'strategy': 'Strategic Recommendations'
        };

        const analysisName = playbookNames[playbookKey] || 'Analysis';
        const loadingId = addLoadingMessageToChat();

        // Fetch playbook results
        fetch(`/api/playbook/${playbookKey}?ta=${encodeURIComponent(currentTaFilter)}`)
            .then(response => response.json())
            .then(data => {
                removeLoadingMessage(loadingId);

                if (data.error) {
                    addChatMessage('assistant', `❌ Error running ${analysisName}: ${data.error}`);
                } else {
                    // Back to original chat flow
                    addChatMessage('assistant', data.narrative);

                    // Add tables if available
                    if (data.tables) {
                        for (const [tableKey, tableData] of Object.entries(data.tables)) {
                            if (tableData && tableData.length > 0) {
                                displayTableInChat(tableKey, tableData);
                            }
                        }
                    }
                }
            })
            .catch(error => {
                console.error('Error running playbook:', error);
                removeLoadingMessage(loadingId);
                addChatMessage('assistant', `❌ Failed to run ${analysisName}. Please try again.`);
            });
    }

    function performSearch() {
        const keyword = keywordSearchInput.value.trim();
        const field = searchFieldSelect.value;

        // Update current search state
        currentSearch = { keyword: keyword, field: field };

        if (!keyword) {
            // If search is cleared, reload the default data for the current TA
            currentSearch = { keyword: '', field: 'All' }; // Clear search state
            fetchData('/api/data', { ta: currentTaFilter }, false);
            return;
        }

        console.log(`Performing search: "${keyword}" in field "${field}" with TA filter "${currentTaFilter}"`);
        fetchData('/api/search', { ta: currentTaFilter, keyword: keyword, field: field }, true);
    }

    searchButton.addEventListener('click', performSearch);
    keywordSearchInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            performSearch();
        }
    });

    // Chat input and send button (for later use)
    sendChatBtn.addEventListener('click', function() {
        const userMessage = chatInput.value.trim();
        if (!userMessage) return;

        addChatMessage('user', userMessage);
        chatInput.value = '';

        // Add spinner loading message to chat
        const loadingId = addLoadingMessageToChat();

        fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: userMessage, ta_filter: currentTaFilter })
        })
        .then(response => response.json())
        .then(data => {
            // Remove loading message
            removeLoadingMessage(loadingId);

            if (data.action === 'trigger_playbook') {
                // If the backend says to trigger a playbook, call the playbook API
                const aiTab = document.getElementById('ai-tab');
                if (aiTab) {
                    new bootstrap.Tab(aiTab).show(); // Switch to AI tab
                }
                addChatMessage('assistant', data.message + " Loading full playbook narrative...");

                // Add another loading message for playbook
                const playbookLoadingId = addLoadingMessageToChat();

                fetch(`/api/playbook/${data.playbook_key}?ta=${encodeURIComponent(currentTaFilter)}`)
                    .then(response => response.json())
                    .then(playbookData => {
                        removeLoadingMessage(playbookLoadingId);

                        if (playbookData.narrative) {
                            addChatMessage('assistant', `<strong>${playbookData.playbook_title}</strong><br><br>${playbookData.narrative}`);
                            if (playbookData.tables) {
                                for (const [tableKey, tableData] of Object.entries(playbookData.tables)) {
                                    if (tableData && tableData.length > 0) {
                                        displayTableInChat(tableKey, tableData);
                                    }
                                }
                            }
                        } else {
                            addChatMessage('assistant', 'Error generating playbook narrative.');
                        }
                    })
                    .catch(error => {
                        console.error('Playbook API error:', error);
                        removeLoadingMessage(playbookLoadingId);
                        addChatMessage('assistant', 'An error occurred while loading the playbook.');
                    });

            } else {
                // Regular chat response - back to original flow
                addChatMessage('assistant', data.message, data.tables);
            }
        })
        .catch(error => {
            console.error('Chat API error:', error);
            removeLoadingMessage(loadingId);
            addChatMessage('assistant', 'An error occurred in chat. Please try again.');
        });
    });

    chatInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendChatBtn.click();
        }
    });
    
    // Note: Playbook button handling is already done above in the playbookButtons.forEach loop


    // Helper function to add message to chat
    function addMessageToChat(role, content) {
        if (!chatHistory) return;

        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${role}`;

        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        messageContent.innerHTML = content.replace(/\n/g, '<br>');

        messageDiv.appendChild(messageContent);
        chatHistory.appendChild(messageDiv);

        // Scroll to bottom
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    // Helper function to display table in chat
    function displayTableInChat(tableName, tableData) {
        if (!chatHistory || !tableData || tableData.length === 0) return;

        const tableContainer = document.createElement('div');
        tableContainer.className = 'table-container mt-3';

        const tableTitle = document.createElement('h6');
        tableTitle.textContent = tableName;
        tableTitle.className = 'table-title';

        const table = document.createElement('table');
        table.className = 'table table-striped table-sm';

        // Create header
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        const headers = Object.keys(tableData[0]);
        headers.forEach(header => {
            const th = document.createElement('th');
            th.textContent = header;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Create body
        const tbody = document.createElement('tbody');
        tableData.slice(0, 50).forEach(row => { // Limit to 50 rows for display
            const tr = document.createElement('tr');
            headers.forEach(header => {
                const td = document.createElement('td');
                td.textContent = row[header] || '';
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);

        tableContainer.appendChild(tableTitle);
        tableContainer.appendChild(table);

        // Add download button
        const downloadBtn = document.createElement('button');
        downloadBtn.className = 'btn btn-sm btn-outline-primary mt-2';
        downloadBtn.textContent = '📥 Download CSV';
        downloadBtn.onclick = () => downloadTableAsCSV(tableData, tableName);
        tableContainer.appendChild(downloadBtn);

        chatHistory.appendChild(tableContainer);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    // Helper function to download table as CSV
    function downloadTableAsCSV(data, filename) {
        const csvData = Papa.unparse(data);
        const blob = new Blob([csvData], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `${filename.replace(/[^a-z0-9]/gi, '_')}.csv`;
        link.click();
        URL.revokeObjectURL(url);
    }

    // --- Initial Load ---
    console.log('Loading initial data...');
    fetchData('/api/data', { ta: currentTaFilter }, false);
    updateFilterInfo();
    updateStatusLine();

}); // End of DOMContentLoaded listener