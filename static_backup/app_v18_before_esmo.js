// static/js/app.js (Confirm this is the current content)

// CACHE BUSTER: Paragraph fix v3 - All handlers should use proper paragraph splitting
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

    // Chat elements - match HTML IDs
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
    let conversationHistory = []; // Store conversation history (last 10 exchanges)

    // --- Utility Functions ---
    function getOrderedHeaders(dataObject) {
        // Enforce consistent column order: Abstract #, Poster #, Title, Authors, Institutions, then others
        const preferredOrder = ['Abstract #', 'Poster #', 'Title', 'Authors', 'Institutions'];
        const dataKeys = Object.keys(dataObject);

        // Start with preferred columns that exist in the data
        const orderedHeaders = preferredOrder.filter(col => dataKeys.includes(col));

        // Add any remaining columns not in preferred order
        const remainingHeaders = dataKeys.filter(col => !preferredOrder.includes(col));

        return [...orderedHeaders, ...remainingHeaders];
    }

    // Simple in-chat loading functions
    function addLoadingMessageToChat(customMessage = 'Generating response...') {
        const loadingId = 'loading-' + Date.now();
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message assistant-message';
        messageDiv.id = loadingId;
        messageDiv.innerHTML = `
            <div class="chat-loading">
                <div class="chat-spinner"></div>
                <span>${customMessage}</span>
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

        // Use utility function to get properly ordered headers
        const headers = getOrderedHeaders(data[0]);

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
        // Build paragraphs correctly - avoid nested <p> tags
        const paragraphs = content
            .trim()
            .split(/\n{2,}/)         // paragraph breaks
            .map(p => p.replace(/\n/g, '<br>'));  // line breaks within a paragraph

        // Apply light markdown: bold
        const html = paragraphs
            .map(p => p.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>'))
            .map(p => `<p>${p}</p>`)
            .join('');

        messageDiv.innerHTML = html;
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
                
                // Create scrollable table wrapper
                const tableResponsive = document.createElement('div');
                tableResponsive.className = 'table-responsive';

                const tableEl = document.createElement('table');
                tableEl.className = 'table table-sm table-striped';
                const theadEl = document.createElement('thead');
                const tbodyEl = document.createElement('tbody');
                tableEl.appendChild(theadEl);
                tableEl.appendChild(tbodyEl);

                // Use utility function to get properly ordered headers
                const headers = getOrderedHeaders(parsedData[0]);

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

                // Wrap table in responsive container
                tableResponsive.appendChild(tableEl);
                tableDiv.appendChild(tableResponsive);

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

            // Switch to AI Assistant tab first
            const aiTab = document.getElementById('ai-tab');
            const aiTabPane = document.getElementById('ai');
            const explorerTab = document.getElementById('explorer-tab');
            const explorerTabPane = document.getElementById('explorer');

            if (aiTab && aiTabPane) {
                // Activate AI tab
                explorerTab.classList.remove('active');
                explorerTab.setAttribute('aria-selected', 'false');
                aiTab.classList.add('active');
                aiTab.setAttribute('aria-selected', 'true');

                // Show AI tab content, hide explorer
                explorerTabPane.classList.remove('show', 'active');
                aiTabPane.classList.add('show', 'active');
            }

            runPlaybook(playbookKey);

            // Scroll to bottom after a short delay to ensure content loads
            setTimeout(() => {
                window.scrollTo({
                    top: document.body.scrollHeight,
                    behavior: 'smooth'
                });
            }, 500);
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

        // Use streaming for all analysis buttons
        if (playbookKey === 'kol') {
            // Use Server-Sent Events for streaming KOL analysis
            runStreamingKolAnalysis(loadingId);
        } else if (playbookKey === 'competitor') {
            // Use Server-Sent Events for streaming competitor analysis
            runStreamingCompetitorAnalysis(loadingId);
        } else if (playbookKey === 'institution') {
            // Use Server-Sent Events for streaming institution analysis
            runStreamingInstitutionAnalysis(loadingId);
        } else if (playbookKey === 'insights') {
            // Use Server-Sent Events for streaming insights analysis
            runStreamingInsightsAnalysis(loadingId);
        } else if (playbookKey === 'strategy') {
            // Use Server-Sent Events for streaming strategy analysis
            runStreamingStrategyAnalysis(loadingId);
        } else {
            // Fallback for any unknown playbooks (shouldn't happen)
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
    }

    // Structured SSE streaming KOL Analysis function
    function runStreamingKolAnalysis(loadingId) {
        // Remove loading message and create streaming message container
        removeLoadingMessage(loadingId);

        const streamingMessageId = 'streaming-' + Date.now();
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message assistant-message';
        messageDiv.id = streamingMessageId;
        messageDiv.innerHTML = '<div class="streaming-content"></div>';

        if (chatHistory) {
            chatHistory.appendChild(messageDiv);
            chatHistory.scrollTop = chatHistory.scrollHeight;
        }

        const contentDiv = messageDiv.querySelector('.streaming-content');

        // State tracking for hybrid streaming
        let currentSection = '';
        let currentAuthor = '';
        let currentElement = null;
        let fullContent = '';

        // Clear any existing tables before starting new analysis
        const tablesContainer = document.getElementById('tables-container');
        if (tablesContainer) {
            tablesContainer.innerHTML = '';
        }

        // Create EventSource for hybrid streaming
        const eventSource = new EventSource(`/api/playbook/kol/stream?ta=${encodeURIComponent(currentTaFilter)}`);

        eventSource.onopen = function() {
            console.log('🔗 Connected to hybrid KOL analysis stream');
        };

        // Handle heading events
        eventSource.addEventListener('heading', function(event) {
            const { level, text } = JSON.parse(event.data);
            const heading = document.createElement('h' + (level || 2));
            heading.textContent = text;
            heading.className = 'kol-heading';
            contentDiv.appendChild(heading);

            console.log(`📋 Added heading: ${text}`);
            chatHistory.scrollTop = chatHistory.scrollHeight;
        });

        // Handle real-time token streaming
        eventSource.addEventListener('token', function(event) {
            const { text, section, author } = JSON.parse(event.data);

            // If we don't have a current element, create new one
            if (!currentElement) {
                if (section === 'executive_summary') {
                    currentElement = document.createElement('p');
                    currentElement.className = 'kol-paragraph executive-summary';
                    contentDiv.appendChild(currentElement);
                    fullContent = ''; // Reset content for new paragraph
                } else if (section === 'kol_profile') {
                    // Create new profile paragraph with author name
                    const profileDiv = document.createElement('p');
                    profileDiv.className = 'kol-profile';

                    const authorName = document.createElement('strong');
                    authorName.textContent = author + ': ';
                    profileDiv.appendChild(authorName);

                    currentElement = document.createElement('span');
                    profileDiv.appendChild(currentElement);
                    contentDiv.appendChild(profileDiv);
                    fullContent = ''; // Reset content for new profile
                }

                currentSection = section;
                currentAuthor = author;
            }

            // If author changed (new KOL profile), create new element
            if (section === 'kol_profile' && author !== currentAuthor) {
                const profileDiv = document.createElement('p');
                profileDiv.className = 'kol-profile';

                const authorName = document.createElement('strong');
                authorName.textContent = author + ': ';
                profileDiv.appendChild(authorName);

                currentElement = document.createElement('span');
                profileDiv.appendChild(currentElement);
                contentDiv.appendChild(profileDiv);

                currentAuthor = author;
                fullContent = '';
            }

            // Append token to content
            fullContent += text;

            // Update element with formatted content (handle markdown)
            const formattedContent = fullContent.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
            currentElement.innerHTML = formattedContent;

            // Auto-scroll
            chatHistory.scrollTop = chatHistory.scrollHeight;
        });

        // Handle paragraph boundaries
        eventSource.addEventListener('paragraph_boundary', function(event) {
            // Force new paragraph for next content
            currentElement = null;
            console.log('📝 Paragraph boundary detected');
        });

        // Handle section boundaries
        eventSource.addEventListener('section_boundary', function(event) {
            const { section } = JSON.parse(event.data);
            currentElement = null;
            currentSection = '';
            console.log(`📚 Section boundary: ${section}`);
        });

        // Handle KOL profile start
        eventSource.addEventListener('kol_start', function(event) {
            const { author } = JSON.parse(event.data);
            currentAuthor = author;
            currentElement = null; // Force new element creation
            console.log(`👤 Starting KOL profile: ${author}`);
        });

        // Handle KOL profile end
        eventSource.addEventListener('kol_end', function(event) {
            const { author } = JSON.parse(event.data);
            currentElement = null;
            currentAuthor = '';
            console.log(`✅ Completed KOL profile: ${author}`);
        });

        // Handle table events
        eventSource.addEventListener('table', function(event) {
            const { title, rows } = JSON.parse(event.data);

            console.log(`📊 Adding table: ${title} with ${rows.length} rows`);
            displayTableInChat(title, rows);
        });

        // Handle completion
        eventSource.addEventListener('done', function(event) {
            console.log('🎉 Structured KOL analysis stream complete!');
            eventSource.close();
        });

        eventSource.onerror = function(error) {
            console.error('❌ KOL analysis stream error:', error);

            // Check if we received substantial content before the error
            const hasSubstantialContent = contentDiv.innerHTML.includes('Executive Summary') ||
                                        contentDiv.querySelectorAll('h3').length > 0;

            eventSource.close();

            if (hasSubstantialContent) {
                contentDiv.innerHTML += '<p><em>⚠️ Connection interrupted during analysis. Partial results shown above.</em></p>';
            } else {
                contentDiv.innerHTML += '<p><em>Connection error occurred. Please try again.</em></p>';
            }
        };
    }

    // Structured SSE streaming competitor analysis function
    function runStreamingCompetitorAnalysis(loadingId) {
        // Remove loading message and create streaming message container
        removeLoadingMessage(loadingId);

        const streamingMessageId = 'streaming-' + Date.now();
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message assistant-message';
        messageDiv.id = streamingMessageId;
        messageDiv.innerHTML = '<div class="streaming-content"></div>';

        if (chatHistory) {
            chatHistory.appendChild(messageDiv);
            chatHistory.scrollTop = chatHistory.scrollHeight;
        }

        const contentDiv = messageDiv.querySelector('.streaming-content');

        // Clear any existing tables before starting new analysis
        const tablesContainer = document.getElementById('tables-container');
        if (tablesContainer) {
            tablesContainer.innerHTML = '';
        }

        // Create EventSource for competitor streaming
        const eventSource = new EventSource(`/api/playbook/competitor/stream?ta=${encodeURIComponent(currentTaFilter)}`);

        eventSource.onopen = function() {
            console.log('🔗 Connected to competitor analysis stream');
        };

        // Handle heading events
        eventSource.addEventListener('heading', function(event) {
            const { level, text } = JSON.parse(event.data);
            const heading = document.createElement('h' + (level || 2));
            heading.textContent = text;
            heading.className = 'competitor-heading';
            contentDiv.appendChild(heading);

            console.log(`📋 Added heading: ${text}`);
            chatHistory.scrollTop = chatHistory.scrollHeight;
        });

        // Handle real-time token streaming
        eventSource.addEventListener('token', function(event) {
            const { text, section } = JSON.parse(event.data);

            // Add text to the main content area
            if (!currentElement || currentElement.tagName !== 'P') {
                currentElement = document.createElement('p');
                contentDiv.appendChild(currentElement);
            }

            currentElement.textContent += text;
            chatHistory.scrollTop = chatHistory.scrollHeight;
        });

        // Handle table events
        eventSource.addEventListener('table', function(event) {
            const { title, rows } = JSON.parse(event.data);

            console.log(`📊 Adding table: ${title} with ${rows.length} rows`);
            displayTableInChat(title, rows);
        });

        // Handle completion
        eventSource.addEventListener('end', function(event) {
            console.log('🎉 Competitor analysis stream complete!');
            eventSource.close();
        });

        eventSource.onerror = function(error) {
            console.error('❌ Competitor analysis stream error:', error);
            eventSource.close();
            contentDiv.innerHTML += '<p><em>Connection error occurred. Please try again.</em></p>';
        };

        // Track current element for streaming
        let currentElement = null;
    }

    // Function to add top authors table after KOL analysis
    function addTopAuthorsTable(taFilter) {
        console.log('📊 Adding top authors table for:', taFilter);

        // Fetch top authors data
        fetch(`/api/data?ta=${encodeURIComponent(taFilter)}`)
            .then(response => response.json())
            .then(data => {
                if (data && data.length > 0) {
                    // Count authors and their institutions (like v8 version)
                    const authorData = {};
                    data.forEach(row => {
                        if (row.Authors) {
                            const authors = row.Authors.split(';');
                            const institutions = row.Institutions ? row.Institutions.split(';') : [];

                            authors.forEach(author => {
                                const cleanAuthor = author.trim();
                                if (cleanAuthor) {
                                    if (!authorData[cleanAuthor]) {
                                        authorData[cleanAuthor] = {
                                            count: 0,
                                            institutions: []
                                        };
                                    }
                                    authorData[cleanAuthor].count++;

                                    // Add institutions for this author
                                    institutions.forEach(inst => {
                                        const cleanInst = inst.trim();
                                        if (cleanInst && cleanInst.length > 10) {
                                            authorData[cleanAuthor].institutions.push(cleanInst);
                                        }
                                    });
                                }
                            });
                        }
                    });

                    // Convert to array and sort, adding top institutions
                    const topAuthors = Object.entries(authorData)
                        .map(([author, data]) => {
                            // Count institution frequency and get top 2
                            const instCounts = {};
                            data.institutions.forEach(inst => {
                                instCounts[inst] = (instCounts[inst] || 0) + 1;
                            });

                            const topInsts = Object.entries(instCounts)
                                .sort((a, b) => b[1] - a[1])
                                .slice(0, 2)
                                .map(([inst, count]) => inst);

                            return {
                                Authors: author,
                                'Abstract Count': data.count,
                                'Top Institutions': topInsts.join('; ')
                            };
                        })
                        .sort((a, b) => b['Abstract Count'] - a['Abstract Count'])
                        .slice(0, 15);

                    if (topAuthors.length > 0) {
                        // Create table container
                        const tableContainer = document.createElement('div');
                        tableContainer.className = 'table-container mt-4';
                        tableContainer.innerHTML = `
                            <h5>👥 Top 15 Authors by Abstract Count</h5>
                            <div class="table-responsive">
                                <table class="table table-striped table-bordered">
                                    <thead>
                                        <tr>
                                            <th>Author</th>
                                            <th>Abstract Count</th>
                                            <th>Top Institutions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${topAuthors.map(author =>
                                            `<tr><td>${author.Authors}</td><td>${author['Abstract Count']}</td><td>${author['Top Institutions']}</td></tr>`
                                        ).join('')}
                                    </tbody>
                                </table>
                            </div>
                        `;

                        // Find the tabs container and add the table
                        const tabsContainer = document.getElementById('tables-container');
                        if (tabsContainer) {
                            tabsContainer.appendChild(tableContainer);
                        }
                    }
                }
            })
            .catch(error => {
                console.error('Error fetching top authors:', error);
            });
    }

    // Institution Analysis Streaming Function
    function runStreamingInstitutionAnalysis(loadingId) {
        // Remove loading message and create streaming message container
        removeLoadingMessage(loadingId);

        const streamingMessageId = 'streaming-' + Date.now();
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message assistant-message';
        messageDiv.id = streamingMessageId;
        messageDiv.innerHTML = '<div class="streaming-content"></div>';

        if (chatHistory) {
            chatHistory.appendChild(messageDiv);
            chatHistory.scrollTop = chatHistory.scrollHeight;
        }

        const contentDiv = messageDiv.querySelector('.streaming-content');

        // Clear any existing tables before starting new analysis
        const tablesContainer = document.getElementById('tables-container');
        if (tablesContainer) {
            tablesContainer.innerHTML = '';
        }

        // Create EventSource for institution streaming
        const eventSource = new EventSource(`/api/playbook/institution/stream?ta=${encodeURIComponent(currentTaFilter)}`);

        eventSource.onopen = function() {
            console.log('🔗 Connected to institution analysis stream');
        };

        // Handle heading events
        eventSource.addEventListener('heading', function(event) {
            const { level, text } = JSON.parse(event.data);
            const heading = document.createElement('h' + (level || 2));
            heading.textContent = text;
            heading.className = 'institution-heading';
            contentDiv.appendChild(heading);

            console.log(`📋 Added heading: ${text}`);
            chatHistory.scrollTop = chatHistory.scrollHeight;
        });

        // Handle table events
        eventSource.addEventListener('table', function(event) {
            const { title, rows } = JSON.parse(event.data);
            console.log(`📊 Adding table: ${title} with ${rows.length} rows`);
            displayTableInChat(title, rows);
        });

        // Handle section events
        eventSource.addEventListener('section', function(event) {
            const { title } = JSON.parse(event.data);
            console.log(`📝 Starting section: ${title}`);
        });

        // Handle real-time token streaming
        eventSource.addEventListener('token', function(event) {
            const { text, section } = JSON.parse(event.data);

            // Add text to the main content area
            if (!currentElement || currentElement.tagName !== 'P') {
                currentElement = document.createElement('p');
                contentDiv.appendChild(currentElement);
            }

            currentElement.textContent += text;
            chatHistory.scrollTop = chatHistory.scrollHeight;
        });

        // Handle completion
        eventSource.addEventListener('end', function(event) {
            console.log('🎉 Institution analysis stream complete!');
            eventSource.close();
        });

        eventSource.onerror = function(error) {
            console.error('❌ Institution analysis stream error:', error);
            eventSource.close();
            contentDiv.innerHTML += '<p><em>Connection error occurred. Please try again.</em></p>';
        };

        // Track current element for streaming
        let currentElement = null;
    }

    // Insights & Trends Analysis Streaming Function
    function runStreamingInsightsAnalysis(loadingId) {
        // Remove loading message and create streaming message container
        removeLoadingMessage(loadingId);

        const streamingMessageId = 'streaming-' + Date.now();
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message assistant-message';
        messageDiv.id = streamingMessageId;
        messageDiv.innerHTML = '<div class="streaming-content"></div>';

        if (chatHistory) {
            chatHistory.appendChild(messageDiv);
            chatHistory.scrollTop = chatHistory.scrollHeight;
        }

        const contentDiv = messageDiv.querySelector('.streaming-content');

        // Clear any existing tables before starting new analysis
        const tablesContainer = document.getElementById('tables-container');
        if (tablesContainer) {
            tablesContainer.innerHTML = '';
        }

        // Create EventSource for insights streaming
        const eventSource = new EventSource(`/api/playbook/insights/stream?ta=${encodeURIComponent(currentTaFilter)}`);

        eventSource.onopen = function() {
            console.log('🔗 Connected to insights analysis stream');
        };

        // Handle heading events
        eventSource.addEventListener('heading', function(event) {
            const { level, text } = JSON.parse(event.data);
            const heading = document.createElement('h' + (level || 2));
            heading.textContent = text;
            heading.className = 'insights-heading';
            contentDiv.appendChild(heading);

            console.log(`📋 Added heading: ${text}`);
            chatHistory.scrollTop = chatHistory.scrollHeight;
        });

        // Handle table events
        eventSource.addEventListener('table', function(event) {
            const { title, rows } = JSON.parse(event.data);
            console.log(`📊 Adding table: ${title} with ${rows.length} rows`);
            displayTableInChat(title, rows);
        });

        // Handle section events
        eventSource.addEventListener('section', function(event) {
            const { title } = JSON.parse(event.data);
            console.log(`📝 Starting section: ${title}`);
        });

        // Handle real-time token streaming
        eventSource.addEventListener('token', function(event) {
            const { text, section } = JSON.parse(event.data);

            // Add text to the main content area
            if (!currentElement || currentElement.tagName !== 'P') {
                currentElement = document.createElement('p');
                contentDiv.appendChild(currentElement);
            }

            currentElement.textContent += text;
            chatHistory.scrollTop = chatHistory.scrollHeight;
        });

        // Handle completion
        eventSource.addEventListener('end', function(event) {
            console.log('🎉 Insights analysis stream complete!');
            eventSource.close();
        });

        eventSource.onerror = function(error) {
            console.error('❌ Insights analysis stream error:', error);
            eventSource.close();
            contentDiv.innerHTML += '<p><em>Connection error occurred. Please try again.</em></p>';
        };

        // Track current element for streaming
        let currentElement = null;
    }

    // Strategic Recommendations Streaming Function
    function runStreamingStrategyAnalysis(loadingId) {
        // Remove loading message and create streaming message container
        removeLoadingMessage(loadingId);

        const streamingMessageId = 'streaming-' + Date.now();
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message assistant-message';
        messageDiv.id = streamingMessageId;
        messageDiv.innerHTML = '<div class="streaming-content"></div>';

        if (chatHistory) {
            chatHistory.appendChild(messageDiv);
            chatHistory.scrollTop = chatHistory.scrollHeight;
        }

        const contentDiv = messageDiv.querySelector('.streaming-content');

        // Clear any existing tables before starting new analysis
        const tablesContainer = document.getElementById('tables-container');
        if (tablesContainer) {
            tablesContainer.innerHTML = '';
        }

        // Create EventSource for strategy streaming
        const eventSource = new EventSource(`/api/playbook/strategy/stream?ta=${encodeURIComponent(currentTaFilter)}`);

        eventSource.onopen = function() {
            console.log('🔗 Connected to strategy analysis stream');
        };

        // Handle heading events
        eventSource.addEventListener('heading', function(event) {
            const { level, text } = JSON.parse(event.data);
            const heading = document.createElement('h' + (level || 2));
            heading.textContent = text;
            heading.className = 'strategy-heading';
            contentDiv.appendChild(heading);

            console.log(`📋 Added heading: ${text}`);
            chatHistory.scrollTop = chatHistory.scrollHeight;
        });

        // Handle table events
        eventSource.addEventListener('table', function(event) {
            const { title, rows } = JSON.parse(event.data);
            console.log(`📊 Adding table: ${title} with ${rows.length} rows`);
            displayTableInChat(title, rows);
        });

        // Handle section events
        eventSource.addEventListener('section', function(event) {
            const { title } = JSON.parse(event.data);
            console.log(`📝 Starting section: ${title}`);
        });

        // Handle real-time token streaming
        eventSource.addEventListener('token', function(event) {
            const { text, section } = JSON.parse(event.data);

            // Add text to the main content area
            if (!currentElement || currentElement.tagName !== 'P') {
                currentElement = document.createElement('p');
                contentDiv.appendChild(currentElement);
            }

            currentElement.textContent += text;
            chatHistory.scrollTop = chatHistory.scrollHeight;
        });

        // Handle completion
        eventSource.addEventListener('end', function(event) {
            console.log('🎉 Strategy analysis stream complete!');
            eventSource.close();
        });

        eventSource.onerror = function(error) {
            console.error('❌ Strategy analysis stream error:', error);
            eventSource.close();
            contentDiv.innerHTML += '<p><em>Connection error occurred. Please try again.</em></p>';
        };

        // Track current element for streaming
        let currentElement = null;
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

    // Hybrid Chat Pipeline: Always stream + add tables when relevant
    sendChatBtn.addEventListener('click', function() {
        const userMessage = chatInput.value.trim();
        if (!userMessage) return;

        addChatMessage('user', userMessage);
        chatInput.value = '';

        // Always use streaming for natural responses
        const streamingMessageId = 'streaming-' + Date.now();
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message assistant-message';
        messageDiv.id = streamingMessageId;
        messageDiv.innerHTML = '<div class="streaming-content"></div>';

        if (chatHistory) {
            chatHistory.appendChild(messageDiv);
            chatHistory.scrollTop = chatHistory.scrollHeight;
        }

        const contentDiv = messageDiv.querySelector('.streaming-content');
        let fullContent = '';
        let currentParagraphContent = '';
        let hasReceivedTables = false; // Track if we've already received tables via SSE

        // Store user message in conversation history
        conversationHistory.push({ role: 'user', content: userMessage });

        // Limit conversation history to last 20 messages (10 exchanges)
        if (conversationHistory.length > 20) {
            conversationHistory = conversationHistory.slice(-20);
        }

        // Use fetch with streaming for POST support with conversation history
        fetch('/api/chat/stream', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: userMessage,
                ta_filter: currentTaFilter,
                conversation_history: conversationHistory
            })
        })
        .then(response => {
            console.log('🔗 Connected to chat stream');

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            function processStream() {
                return reader.read().then(({ done, value }) => {
                    if (done) {
                        console.log('🎉 Chat stream complete!');

                        // Store assistant response in conversation history
                        if (fullContent.trim()) {
                            conversationHistory.push({ role: 'assistant', content: fullContent.trim() });

                            // Limit conversation history to last 20 messages (10 exchanges)
                            if (conversationHistory.length > 20) {
                                conversationHistory = conversationHistory.slice(-20);
                            }
                        }

                        // After streaming completes, check if we should add tables (only if not already received)
                        if (!hasReceivedTables) {
                            checkAndAddRelevantTables(userMessage, streamingMessageId);
                        }
                        return;
                    }

                    // Decode chunk and process SSE format
                    const chunk = decoder.decode(value, { stream: true });
                    const lines = chunk.split('\n');

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const eventData = line.slice(6); // Remove 'data: ' prefix

                            // Handle special events
                            if (eventData.startsWith('{') && (eventData.includes('"title"') && eventData.includes('"rows"'))) {
                                // This is a table event
                                try {
                                    const { title, rows } = JSON.parse(eventData);
                                    console.log(`📊 Adding table: ${title} with ${rows.length} rows`);
                                    displayTableInChat(title, rows);
                                    hasReceivedTables = true;
                                } catch (e) {
                                    console.error('Error parsing table data:', e);
                                }
                                continue;
                            }

                            if (eventData === '[DONE]') {
                                console.log('🎉 Chat stream complete!');

                                // Store assistant response in conversation history
                                if (fullContent.trim()) {
                                    conversationHistory.push({ role: 'assistant', content: fullContent.trim() });

                                    // Limit conversation history to last 20 messages (10 exchanges)
                                    if (conversationHistory.length > 20) {
                                        conversationHistory = conversationHistory.slice(-20);
                                    }
                                }

                                // After streaming completes, check if we should add tables (only if not already received)
                                if (!hasReceivedTables) {
                                    checkAndAddRelevantTables(userMessage, streamingMessageId);
                                }
                                return;
                            }

                            // Check for paragraph break signal
                            if (eventData === '|||PARAGRAPH_BREAK|||') {
                                // Finalize current paragraph and start a new one
                                currentParagraphContent = '';
                                const newParagraph = document.createElement('p');
                                contentDiv.appendChild(newParagraph);
                                continue;
                            }

                            // Regular token - append to content
                            fullContent += eventData;
                            currentParagraphContent += eventData;

                            // Get or create the current paragraph element
                            let currentParagraph = contentDiv.lastElementChild;
                            if (!currentParagraph || currentParagraph.tagName !== 'P') {
                                currentParagraph = document.createElement('p');
                                contentDiv.appendChild(currentParagraph);
                            }

                            // Apply simple markdown formatting and update only the current paragraph
                            const formattedContent = currentParagraphContent.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                            currentParagraph.innerHTML = formattedContent;

                            // Auto-scroll to bottom
                            chatHistory.scrollTop = chatHistory.scrollHeight;
                        }
                    }

                    // Continue processing the stream
                    return processStream();
                });
            }

            return processStream();
        })
        .catch(error => {
            console.error('💥 Chat fetch failed:', error);

            if (fullContent.trim() === '') {
                // No content received, show error
                contentDiv.innerHTML = '❌ Connection failed during chat response. Please try again.';
            }
        });
    });

    // Function to check if query needs data tables and add them
    function checkAndAddRelevantTables(userMessage, messageId) {
        // Check if this query should have accompanying data tables
        const needsTableData = isDataQuery(userMessage);

        if (needsTableData) {
            console.log('🔍 Query needs data tables, fetching...');

            // Fetch table data via the existing non-streaming endpoint
            fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: userMessage,
                    ta_filter: currentTaFilter,
                    conversation_history: conversationHistory
                })
            })
            .then(response => response.json())
            .then(data => {
                // Only add tables, ignore the narrative (we already have that from streaming)
                if (data.tables && Object.keys(data.tables).length > 0) {
                    console.log(`📊 Adding ${Object.keys(data.tables).length} tables to chat`);
                    Object.entries(data.tables).forEach(([title, tableData]) => {
                        addTableToChat(title, tableData);
                    });
                }
            })
            .catch(error => {
                console.error('Error fetching table data:', error);
            });
        }
    }

    // Enhanced data query detection (replaces isTableQuery)
    function isDataQuery(message) {
        const lowerMessage = message.toLowerCase();

        // Patterns that indicate data/table queries
        const dataPatterns = [
            // Author information queries - comprehensive patterns
            /\b(tell me|more about|info|information|details|who is|what about).*(author|researcher|scientist)/i,
            /\b(tell me|more about|info|information|details|who is|what about)\s+[a-z]+\s+[a-z]+/i, // "tell me about John Smith"
            /\b(does|has|is)\s+[a-z]+\s+[a-z]+\s+.*(involvement|collaboration|work|research|study|abstract|pharmaceutical|industry)/i, // "Does petros grivas have any..."
            /\b[a-z]+\s+[a-z]+\s+(have|has|involved|working|research|study|abstract)/i, // "Petros Grivas have any..."
            /\b(abstracts? (?:by|from|with|involving|authored by)).*/i,
            /\b(studies by|research by|work by|papers by)/i,
            /\b(all abstracts).*/i,
            /\b(top \d+ authors?)/i,
            /\b(list.*authors?)/i,
            // Institution queries
            /\b(institution|hospital|university|center|college).*(abstracts?|studies|research)/i,
            // Common author name patterns - more comprehensive
            /\b(milloy|omar|elghawy|gupta|kamat|balar|rosenberg|galsky|powles|grivas|bamias|loriot|petrylak|hussain|sonpavde|de wit|plimack)/i,
            // Generic name patterns that could be authors
            /\b(dr\.?\s+[a-z]+|prof\.?\s+[a-z]+)/i,
            // Two-word combinations that are likely names
            /\b[A-Z][a-z]+\s+[A-Z][a-z]+\b.*\b(research|study|abstract|work|involvement|collaboration)/i,
            // Studies/research patterns
            /\b(author.*(study|studies|abstract|research|paper))/i,
            /\b(researcher.*(study|studies|abstract|research|paper))/i,
            // Drug/compound queries with specific research context
            /\b(abstracts?.*(enfortumab|pembrolizumab|avelumab|nivolumab))/i,
            /\b(studies?.*(enfortumab|pembrolizumab|avelumab|nivolumab))/i,
            // Industry involvement questions
            /\b(pharmaceutical|industry|collaboration|partnership).*(involvement|work|research)/i,
        ];

        // Debug logging
        const matches = dataPatterns.filter(pattern => pattern.test(message));
        if (matches.length > 0) {
            console.log(`🔍 Query "${message}" matched ${matches.length} data patterns - will fetch tables`);
        }

        return dataPatterns.some(pattern => pattern.test(message));
    }

    // Helper function to add table to chat
    function addTableToChat(title, tableData, caption) {
        // Use the existing displayTableInChat function
        displayTableInChat(title, tableData);
    }


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
        // Build paragraphs correctly - avoid nested <p> tags
        const paragraphs = content
            .trim()
            .split(/\n{2,}/)         // paragraph breaks
            .map(p => p.replace(/\n/g, '<br>'));  // line breaks within a paragraph

        // Apply light markdown: bold
        const html = paragraphs
            .map(p => p.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>'))
            .map(p => `<p>${p}</p>`)
            .join('');

        messageContent.innerHTML = html;

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

        // Create scrollable table wrapper
        const tableResponsive = document.createElement('div');
        tableResponsive.className = 'table-responsive';

        const table = document.createElement('table');
        table.className = 'table table-striped table-sm';

        // Create header with consistent column ordering
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');

        // Use utility function to get properly ordered headers
        const headers = getOrderedHeaders(tableData[0]);

        headers.forEach(header => {
            const th = document.createElement('th');
            th.textContent = header;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Create body
        const tbody = document.createElement('tbody');
        tableData.forEach(row => { // Show all rows now that we have scrolling
            const tr = document.createElement('tr');
            headers.forEach(header => {
                const td = document.createElement('td');
                td.textContent = row[header] || '';
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);

        // Wrap table in responsive container
        tableResponsive.appendChild(table);

        tableContainer.appendChild(tableTitle);
        tableContainer.appendChild(tableResponsive);

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

    // --- Navigation Buttons Functionality ---
    const backToTopBtn = document.getElementById('backToTopBtn');
    const backToBottomBtn = document.getElementById('backToBottomBtn');

    // Show/hide buttons based on scroll position
    window.addEventListener('scroll', function() {
        if (window.pageYOffset > 300) {
            backToTopBtn.classList.add('show');
            backToBottomBtn.classList.add('show');
        } else {
            backToTopBtn.classList.remove('show');
            backToBottomBtn.classList.remove('show');
        }
    });

    // Smooth scroll to top when clicked
    backToTopBtn.addEventListener('click', function() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });

    // Smooth scroll to bottom when clicked
    backToBottomBtn.addEventListener('click', function() {
        window.scrollTo({
            top: document.body.scrollHeight,
            behavior: 'smooth'
        });
    });

    // --- Initial Load ---
    console.log('Loading initial data...');
    fetchData('/api/data', { ta: currentTaFilter }, false);
    updateFilterInfo();
    updateStatusLine();

}); // End of DOMContentLoaded listener