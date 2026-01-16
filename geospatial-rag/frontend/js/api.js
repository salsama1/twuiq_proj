/**
 * GEOSPATIAL RAG - API CLIENT
 */

class ApiClient {
    constructor(baseUrl = 'http://localhost:8000') {
        this.baseUrl = baseUrl;
    }

    setBaseUrl(url) {
        this.baseUrl = url.replace(/\/$/, '');
    }

    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        
        try {
            const response = await fetch(url, {
                headers: { 'Content-Type': 'application/json' },
                ...options
            });
            
            if (!response.ok) {
                const error = await response.json().catch(() => ({ detail: response.statusText }));
                throw new Error(error.detail || `HTTP ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error(`API Error [${endpoint}]:`, error);
            throw error;
        }
    }

    async healthCheck() {
        return this.request('/api/health');
    }

    async query(queryText, options = {}) {
        return this.request('/api/query', {
            method: 'POST',
            body: JSON.stringify({
                query: queryText,
                include_visualization: true,
                max_results: options.maxResults || 500,
            }),
        });
    }

    async exportData(queryText, format = 'geojson') {
        return this.request('/api/export', {
            method: 'POST',
            body: JSON.stringify({ query: queryText, format }),
        });
    }

    getDownloadUrl(filename) {
        return `${this.baseUrl}/api/export/download/${filename}`;
    }
}

const api = new ApiClient();
