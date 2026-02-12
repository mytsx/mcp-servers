// Git MCP Extended Logs - JavaScript
let currentLogs = [];
const ws = new WebSocket(wsUrl);

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    if (data.type === 'new_log') {
        fetchLogs();
    }
};

async function fetchLogs() {
    const searchTerm = document.getElementById('searchInput').value;
    const statusFilter = document.getElementById('statusFilter').value;
    
    // Build query parameters for server-side filtering
    const params = new URLSearchParams();
    if (searchTerm) {
        params.append('command', searchTerm);
    }
    if (statusFilter) {
        params.append('status', statusFilter);
    }
    params.append('limit', '100'); // Request up to 100 logs
    
    const response = await fetch(`${apiUrl}?${params}`);
    currentLogs = await response.json();
    renderLogs();
}

function renderLogs() {
    const tbody = document.getElementById('logsTable');
    tbody.innerHTML = currentLogs.map(log => {
        const args = typeof log.arguments === 'string' ? JSON.parse(log.arguments) : log.arguments;
        const argsPreview = args.args.join(', ').substring(0, 100);
        const timestamp = new Date(log.timestamp).toLocaleString();
        const statusClass = log.status === 'success' ? 'text-green-600' : 'text-red-600';
        
        return `
            <tr>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${timestamp}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">${log.command}</td>
                <td class="px-6 py-4 text-sm text-gray-500 command-cell">
                    <div class="truncate-multiline">${argsPreview}</div>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm ${statusClass}">${log.status}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${log.duration.toFixed(3)}s</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    <button onclick="showDetails(${log.id})" 
                            class="text-indigo-600 hover:text-indigo-900">Details</button>
                </td>
            </tr>
        `;
    }).join('');
}

function showDetails(id) {
    const log = currentLogs.find(l => l.id === id);
    if (!log) return;
    
    const args = typeof log.arguments === 'string' ? JSON.parse(log.arguments) : log.arguments;
    const timestamp = new Date(log.timestamp).toLocaleString();
    
    const content = `
        <div class="space-y-3">
            <div><strong>Command:</strong> ${log.command}</div>
            <div><strong>Timestamp:</strong> ${timestamp}</div>
            <div><strong>Status:</strong> <span class="${log.status === 'success' ? 'text-green-600' : 'text-red-600'}">${log.status}</span></div>
            <div><strong>Duration:</strong> ${log.duration.toFixed(3)} seconds</div>
            ${log.repo_path ? `<div><strong>Repository:</strong> ${log.repo_path}</div>` : ''}
            
            <div>
                <strong>Arguments:</strong>
                <pre class="mt-2 p-3 bg-gray-100 rounded overflow-x-auto text-sm">${JSON.stringify(args, null, 2)}</pre>
            </div>
            
            ${log.output ? `
            <div>
                <strong>Output:</strong>
                <pre class="mt-2 p-3 bg-gray-100 rounded overflow-x-auto text-sm">${log.output}</pre>
            </div>
            ` : ''}
            
            ${log.error ? `
            <div>
                <strong>Error:</strong>
                <pre class="mt-2 p-3 bg-red-50 text-red-700 rounded overflow-x-auto text-sm">${log.error}</pre>
            </div>
            ` : ''}
        </div>
    `;
    
    document.getElementById('modalContent').innerHTML = content;
    document.getElementById('detailModal').classList.remove('hidden');
}

function closeModal() {
    document.getElementById('detailModal').classList.add('hidden');
}

// Close modal on Escape key
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        closeModal();
    }
});

// Close modal on background click
document.getElementById('detailModal').addEventListener('click', function(event) {
    if (event.target === this) {
        closeModal();
    }
});

// Add debounce function for search input
let searchTimeout;
function debounceSearch() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(fetchLogs, 300);
}

document.getElementById('searchInput').addEventListener('input', debounceSearch);
document.getElementById('statusFilter').addEventListener('change', fetchLogs);

// Initial load
fetchLogs();