/**
 * GEOSPATIAL RAG - MAIN APP
 */

window.appSettings = {
    apiEndpoint: 'http://localhost:8000',
    mapboxToken: '',
    maxResults: 500
};

function showView(viewId) {
    document.querySelectorAll('.view-container').forEach(v => {
        v.classList.add('hidden');
        v.classList.remove('active');
    });
    document.querySelectorAll('.tab-btn').forEach(t => t.classList.remove('active'));

    const view = document.getElementById(`view-${viewId}`);
    if (view) {
        view.classList.remove('hidden');
        view.classList.add('active');
    }

    const tab = document.querySelector(`[data-view="${viewId}"]`);
    if (tab) tab.classList.add('active');

    // Init 3D map on first view
    if (viewId === 'map3d' && map3d && !map3d.initialized && window.appSettings.mapboxToken) {
        map3d.init(window.appSettings.mapboxToken);
        setTimeout(() => {
            if (chat?.getLastVisualization()) {
                map3d.displayData(chat.getLastVisualization());
            }
        }, 1500);
    }

    // Resize maps
    setTimeout(() => {
        if (viewId === 'map2d' && map2d) map2d.resize();
        if (viewId === 'map3d' && map3d) map3d.resize();
    }, 100);
}

async function checkHealth() {
    const indicator = document.getElementById('status-indicator');
    const text = document.getElementById('status-text');

    try {
        const health = await api.healthCheck();
        indicator.classList.toggle('online', health.status === 'healthy');
        indicator.classList.toggle('offline', health.status !== 'healthy');
        text.textContent = health.status === 'healthy' ? 'Connected' : 'Degraded';
    } catch {
        indicator.classList.remove('online');
        indicator.classList.add('offline');
        text.textContent = 'Disconnected';
    }
}

function loadSettings() {
    const saved = localStorage.getItem('geospatial-rag-settings-v2');
    if (saved) {
        try {
            Object.assign(window.appSettings, JSON.parse(saved));
            api.setBaseUrl(window.appSettings.apiEndpoint);
            document.getElementById('api-endpoint').value = window.appSettings.apiEndpoint;
            document.getElementById('mapbox-token').value = window.appSettings.mapboxToken;
            document.getElementById('max-results').value = window.appSettings.maxResults;
        } catch (e) {}
    }
}

function saveSettings() {
    window.appSettings.apiEndpoint = document.getElementById('api-endpoint').value;
    window.appSettings.mapboxToken = document.getElementById('mapbox-token').value;
    window.appSettings.maxResults = parseInt(document.getElementById('max-results').value);

    localStorage.setItem('geospatial-rag-settings-v2', JSON.stringify(window.appSettings));
    document.getElementById('settings-modal').classList.add('hidden');
    location.reload();
}

document.addEventListener('DOMContentLoaded', () => {
    console.log('Initializing Geospatial RAG...');

    loadSettings();
    initMap2D(window.appSettings.mapboxToken);
    initMap3D(window.appSettings.mapboxToken);
    initChat();

    // View tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => showView(btn.dataset.view));
    });

    // Export buttons
    document.getElementById('export-geojson')?.addEventListener('click', async () => {
        const query = chat?.getLastQuery();
        if (!query) return alert('Run a query first');
        try {
            const result = await api.exportData(query, 'geojson');
            if (result.success) window.open(api.getDownloadUrl(result.filename));
        } catch (e) { alert(e.message); }
    });

    // Settings
    document.getElementById('settings-btn')?.addEventListener('click', () => {
        document.getElementById('settings-modal').classList.remove('hidden');
    });
    document.querySelector('.close-btn')?.addEventListener('click', () => {
        document.getElementById('settings-modal').classList.add('hidden');
    });
    document.getElementById('save-settings')?.addEventListener('click', saveSettings);
    document.getElementById('settings-modal')?.addEventListener('click', (e) => {
        if (e.target.id === 'settings-modal') e.target.classList.add('hidden');
    });

    // Token warning
    if (!window.appSettings.mapboxToken) {
        chat?.addMessage('assistant', 
            '⚠️ **Mapbox token required**\n\n' +
            '1. Go to [mapbox.com](https://mapbox.com)\n' +
            '2. Sign up (free)\n' +
            '3. Copy your token\n' +
            '4. Click ⚙️ Settings and paste it'
        );
    }

    checkHealth();
    setInterval(checkHealth, 30000);

    console.log('Ready');
});
