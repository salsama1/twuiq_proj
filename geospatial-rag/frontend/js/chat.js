/**
 * GEOSPATIAL RAG - CHAT INTERFACE
 */

class Chat {
    constructor() {
        this.messagesContainer = document.getElementById('chat-messages');
        this.input = document.getElementById('chat-input');
        this.sendBtn = document.getElementById('send-btn');
        
        this.isProcessing = false;
        this.lastVisualization = null;
        this.lastQuery = '';
        this.lastData = null;
        
        this.setupEventListeners();
    }

    setupEventListeners() {
        this.sendBtn.addEventListener('click', () => this.sendMessage());
        this.input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
    }

    async sendMessage() {
        const query = this.input.value.trim();
        if (!query || this.isProcessing) return;

        this.addMessage('user', query);
        this.input.value = '';
        this.lastQuery = query;

        await this.processQuery(query);
    }

    async processQuery(query) {
        this.isProcessing = true;
        this.showLoading(true);

        try {
            const response = await api.query(query, {
                maxResults: window.appSettings?.maxResults || 9999999999999
            });

            this.handleResponse(response);
        } catch (error) {
            this.addMessage('assistant', `❌ Error: ${error.message}`);
        } finally {
            this.isProcessing = false;
            this.showLoading(false);
        }
    }

    handleResponse(response) {
        if (!response.success) {
            this.addMessage('assistant', `Sorry: ${response.error}`);
            return;
        }

        this.lastData = response.data;
        this.lastVisualization = response.visualization;

        let message = response.description ? response.description + '\n\n' : '';
        message += `Found **${response.row_count || 0}** results.`;

        if (response.sql_query) {
            const sql = response.sql_query.length > 80 ? response.sql_query.slice(0, 80) + '...' : response.sql_query;
            message += `\n\n\`${sql}\``;
        }

        this.addMessage('assistant', message);

        // Update maps
        if (response.visualization) {
            if (map2d?.overlay) map2d.displayData(response.visualization);
            if (map3d?.initialized) map3d.displayData(response.visualization);
        }

        // Update table
        if (response.data) this.updateTable(response.data);
    }

    updateTable(data) {
        if (!data?.length) return;

        const header = document.getElementById('table-header');
        const body = document.getElementById('table-body');
        document.getElementById('result-count').textContent = `${data.length} results`;

        const cols = Object.keys(data[0]);
        header.innerHTML = '<tr>' + cols.map(c => `<th>${c}</th>`).join('') + '</tr>';
        body.innerHTML = data.slice(0, 200).map(row => 
            '<tr>' + cols.map(c => `<td>${row[c] ?? ''}</td>`).join('') + '</tr>'
        ).join('');
    }

    addMessage(role, content) {
        const div = document.createElement('div');
        div.className = `message ${role}`;
        div.innerHTML = `<div class="message-content">${
            content
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/`(.*?)`/g, '<code>$1</code>')
                .replace(/\n/g, '<br>')
        }</div>`;
        this.messagesContainer.appendChild(div);
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }

    showLoading(show) {
        document.getElementById('loading-overlay').classList.toggle('hidden', !show);
    }

    getLastVisualization() { return this.lastVisualization; }
    getLastQuery() { return this.lastQuery; }
}

let chat = null;
function initChat() {
    if (!chat) chat = new Chat();
    return chat;
}
