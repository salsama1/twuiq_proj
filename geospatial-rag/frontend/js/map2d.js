/**
 * GEOSPATIAL RAG - 2D MAP (DECK.GL + MAPBOX)
 * Using MapboxOverlay for reliable rendering
 */

class Map2D {
    constructor(containerId = 'map2d') {
        this.containerId = containerId;
        this.map = null;
        this.overlay = null;
        this.currentData = [];
        this.currentLayerType = 'scatter';
        this.originalBounds = null;
        
        this.settings = {
            scatter: { radius: 8, opacity: 0.8 },
            hexagon: { radius: 20000, coverage: 0.8, elevation: 100 },
            heatmap: { intensity: 1, radius: 30, threshold: 0.05 }
        };
        
        this.initialView = {
            longitude: 42.5,
            latitude: 23.5,
            zoom: 6
        };
    }

    init(mapboxToken) {
        if (!mapboxToken) {
            this.showTokenError();
            return;
        }

        mapboxgl.accessToken = mapboxToken;

        this.map = new mapboxgl.Map({
            container: this.containerId,
            style: 'mapbox://styles/mapbox/dark-v11',
            center: [this.initialView.longitude, this.initialView.latitude],
            zoom: this.initialView.zoom,
            antialias: true
        });

        this.map.addControl(new mapboxgl.NavigationControl(), 'top-right');

        // Create MapboxOverlay - this is the reliable method
        this.overlay = new deck.MapboxOverlay({
            interleaved: false,
            layers: []
        });

        this.map.addControl(this.overlay);

        this.map.on('load', () => {
            this.setupControls();
            console.log('2D Map ready with MapboxOverlay');
        });
    }

    showTokenError() {
        document.getElementById(this.containerId).innerHTML = 
            `<div style="display:flex;align-items:center;justify-content:center;height:100%;background:#1a1a2e;color:#fff;flex-direction:column;padding:20px;text-align:center;">
                <h3>⚠️ Mapbox Token Required</h3>
                <p>Click ⚙️ Settings and enter your Mapbox token</p>
            </div>`;
    }

    setupControls() {
        // Layer type buttons
        document.querySelectorAll('#control-panel-2d .layer-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('#control-panel-2d .layer-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.currentLayerType = btn.dataset.layer;
                this.showLayerControls(this.currentLayerType);
                this.updateLayers();
            });
        });

        // Scatter controls
        this.setupSlider('scatter-radius', (val) => {
            this.settings.scatter.radius = parseInt(val);
            document.getElementById('scatter-radius-val').textContent = val;
            this.updateLayers();
        });
        
        this.setupSlider('scatter-opacity', (val) => {
            this.settings.scatter.opacity = parseInt(val) / 100;
            document.getElementById('scatter-opacity-val').textContent = val;
            this.updateLayers();
        });

        // Hexagon controls
        this.setupSlider('hex-radius', (val) => {
            this.settings.hexagon.radius = parseInt(val) * 1000;
            document.getElementById('hex-radius-val').textContent = val;
            this.updateLayers();
        });
        
        this.setupSlider('hex-coverage', (val) => {
            this.settings.hexagon.coverage = parseInt(val) / 100;
            document.getElementById('hex-coverage-val').textContent = val;
            this.updateLayers();
        });
        
        this.setupSlider('hex-elevation', (val) => {
            this.settings.hexagon.elevation = parseInt(val);
            document.getElementById('hex-elevation-val').textContent = val;
            this.updateLayers();
        });

        // Heatmap controls
        this.setupSlider('heat-intensity', (val) => {
            this.settings.heatmap.intensity = parseInt(val) / 10;
            document.getElementById('heat-intensity-val').textContent = (parseInt(val) / 10).toFixed(1);
            this.updateLayers();
        });
        
        this.setupSlider('heat-radius', (val) => {
            this.settings.heatmap.radius = parseInt(val);
            document.getElementById('heat-radius-val').textContent = val;
            this.updateLayers();
        });
        
        this.setupSlider('heat-threshold', (val) => {
            this.settings.heatmap.threshold = parseInt(val) / 100;
            document.getElementById('heat-threshold-val').textContent = (parseInt(val) / 100).toFixed(2);
            this.updateLayers();
        });
    }

    setupSlider(id, callback) {
        const slider = document.getElementById(id);
        if (slider) {
            slider.addEventListener('input', (e) => callback(e.target.value));
        }
    }

    showLayerControls(layerType) {
        document.querySelectorAll('.layer-controls-section').forEach(el => el.classList.add('hidden'));
        const controlsEl = document.getElementById(`${layerType}-controls`);
        if (controlsEl) controlsEl.classList.remove('hidden');
    }

    displayData(visualization) {
        if (!this.overlay) {
            console.log('Map not ready');
            return;
        }

        if (!visualization?.geojson?.features?.length) {
            console.log('No data to display');
            this.overlay.setProps({ layers: [] });
            return;
        }

        this.currentData = visualization.geojson.features.map(f => ({
            position: f.geometry.coordinates,
            longitude: f.geometry.coordinates[0],
            latitude: f.geometry.coordinates[1],
            properties: f.properties
        }));

        this.originalBounds = visualization.bounds;
        document.getElementById('point-count-2d').textContent = `${this.currentData.length} points`;
        
        this.updateLayers();
        
        if (visualization.bounds) {
            this.fitBounds(visualization.bounds);
        }

        console.log(`Displayed ${this.currentData.length} points on 2D map`);
    }

    updateLayers() {
        if (!this.overlay || !this.currentData.length) return;

        let layer;
        const s = this.settings;

        switch (this.currentLayerType) {
            case 'scatter':
                layer = new deck.ScatterplotLayer({
                    id: 'scatter-layer',
                    data: this.currentData,
                    getPosition: d => d.position,
                    getFillColor: d => this.getColor(d.properties),
                    getLineColor: [255, 255, 255, 150],
                    getRadius: s.scatter.radius * 300,
                    radiusMinPixels: s.scatter.radius,
                    radiusMaxPixels: s.scatter.radius * 4,
                    opacity: s.scatter.opacity,
                    stroked: true,
                    lineWidthMinPixels: 1,
                    pickable: true,
                    autoHighlight: true,
                    highlightColor: [255, 255, 0, 200],
                    onHover: info => this.showTooltip(info),
                    onClick: info => this.handleClick(info)
                });
                break;

            case 'hexagon':
                layer = new deck.HexagonLayer({
                    id: 'hexagon-layer',
                    data: this.currentData,
                    getPosition: d => d.position,
                    radius: s.hexagon.radius,
                    coverage: s.hexagon.coverage,
                    elevationScale: s.hexagon.elevation,
                    elevationRange: [0, 3000],
                    extruded: true,
                    pickable: true,
                    colorRange: [
                        [1, 152, 189],
                        [73, 227, 206],
                        [216, 254, 181],
                        [254, 237, 177],
                        [254, 173, 84],
                        [209, 55, 78]
                    ],
                    material: {
                        ambient: 0.64,
                        diffuse: 0.6,
                        shininess: 32
                    },
                    onHover: info => this.showHexTooltip(info)
                });
                break;

            case 'heatmap':
                layer = new deck.HeatmapLayer({
                    id: 'heatmap-layer',
                    data: this.currentData,
                    getPosition: d => d.position,
                    getWeight: 1,
                    intensity: s.heatmap.intensity,
                    radiusPixels: s.heatmap.radius,
                    threshold: s.heatmap.threshold,
                    colorRange: [
                        [255, 255, 178, 25],
                        [254, 217, 118, 85],
                        [254, 178, 76, 127],
                        [253, 141, 60, 170],
                        [240, 59, 32, 212],
                        [189, 0, 38, 255]
                    ]
                });
                break;
        }

        this.overlay.setProps({ layers: [layer] });
    }

    showTooltip(info) {
        const tooltip = document.getElementById('tooltip-2d');
        if (!info.object) {
            if (tooltip) tooltip.style.display = 'none';
            return;
        }

        const d = info.object;
        const p = d.properties || {};
        
        let html = `<div class="tooltip-header">${p.eng_name || p.sampleid || p.borehole_i || 'Site'}</div>`;
        
        if (p.arb_name) html += `<div class="tooltip-row"><span>Arabic:</span> ${p.arb_name}</div>`;
        if (p.major_comm) html += `<div class="tooltip-row"><span>Major Commodity:</span> ${p.major_comm}</div>`;
        if (p.minor_comm) html += `<div class="tooltip-row"><span>Minor Commodity:</span> ${p.minor_comm}</div>`;
        if (p.region) html += `<div class="tooltip-row"><span>Region:</span> ${p.region}</div>`;
        if (p.occ_type) html += `<div class="tooltip-row"><span>Type:</span> ${p.occ_type}</div>`;
        if (p.elements) html += `<div class="tooltip-row"><span>Elements:</span> ${p.elements}</div>`;
        
        html += `<div class="tooltip-coords">📍 ${d.latitude.toFixed(6)}, ${d.longitude.toFixed(6)}</div>`;

        if (!tooltip) {
            const t = document.createElement('div');
            t.id = 'tooltip-2d';
            t.className = 'map-tooltip';
            document.getElementById('view-map2d').appendChild(t);
        }
        
        const tt = document.getElementById('tooltip-2d');
        tt.innerHTML = html;
        tt.style.display = 'block';
        tt.style.left = (info.x + 10) + 'px';
        tt.style.top = (info.y + 10) + 'px';
    }

    showHexTooltip(info) {
        const tooltip = document.getElementById('tooltip-2d');
        if (!info.object) {
            if (tooltip) tooltip.style.display = 'none';
            return;
        }

        const count = info.object.points?.length || 0;
        let html = `<div class="tooltip-header">Hexagon Cluster</div>`;
        html += `<div class="tooltip-row"><span>Sites:</span> ${count}</div>`;
        
        if (count > 0 && count <= 5) {
            html += `<div class="tooltip-divider"></div>`;
            info.object.points.forEach(p => {
                const name = p.source?.properties?.eng_name || 'Site';
                html += `<div class="tooltip-row">• ${name}</div>`;
            });
        }

        if (!tooltip) {
            const t = document.createElement('div');
            t.id = 'tooltip-2d';
            t.className = 'map-tooltip';
            document.getElementById('view-map2d').appendChild(t);
        }
        
        const tt = document.getElementById('tooltip-2d');
        tt.innerHTML = html;
        tt.style.display = 'block';
        tt.style.left = (info.x + 10) + 'px';
        tt.style.top = (info.y + 10) + 'px';
    }

    handleClick(info) {
        if (!info.object) return;
        
        const d = info.object;
        this.showInfoPanel(d);
        
        // Zoom to point
        this.map.flyTo({
            center: [d.longitude, d.latitude],
            zoom: 12,
            duration: 1000
        });
        
        // Show zoom out button
        const zoomOutBtn = document.getElementById('zoom-out-2d');
        if (zoomOutBtn) zoomOutBtn.classList.remove('hidden');
    }
    
    showInfoPanel(data) {
        let panel = document.getElementById('info-panel-2d');
        if (!panel) {
            panel = document.createElement('div');
            panel.id = 'info-panel-2d';
            panel.className = 'info-panel';
            document.getElementById('view-map2d').appendChild(panel);
        }
        
        const p = data.properties || {};
        
        let html = `
            <div class="info-panel-header">
                <h3>${p.eng_name || p.sampleid || p.borehole_i || 'Site Details'}</h3>
                <button class="info-close-btn" onclick="map2d.hideInfoPanel()">×</button>
            </div>
            <div class="info-panel-body">
        `;
        
        // All available properties
        const fields = [
            { key: 'arb_name', label: 'Arabic Name' },
            { key: 'mods', label: 'MODS ID' },
            { key: 'major_comm', label: 'Major Commodity' },
            { key: 'minor_comm', label: 'Minor Commodity' },
            { key: 'trace_comm', label: 'Trace Commodity' },
            { key: 'region', label: 'Region' },
            { key: 'occ_type', label: 'Type' },
            { key: 'occ_imp', label: 'Importance' },
            { key: 'exp_status', label: 'Exploration Status' },
            { key: 'host_rocks', label: 'Host Rocks' },
            { key: 'geologic_f', label: 'Geological Formation' },
            { key: 'gitology', label: 'Deposit Type' },
            { key: 'elevation', label: 'Elevation' },
            { key: 'project_na', label: 'Project Name' },
            { key: 'projectnam', label: 'Project Name' },
            { key: 'borehole_i', label: 'Borehole ID' },
            { key: 'borehole_t', label: 'Borehole Type' },
            { key: 'depth_m', label: 'Depth (m)' },
            { key: 'sampleid', label: 'Sample ID' },
            { key: 'sampletype', label: 'Sample Type' },
            { key: 'elements', label: 'Elements' },
        ];
        
        fields.forEach(f => {
            if (p[f.key] && p[f.key] !== 'null' && p[f.key] !== '') {
                html += `<div class="info-row"><span class="info-label">${f.label}:</span><span class="info-value">${p[f.key]}</span></div>`;
            }
        });
        
        html += `
            <div class="info-coords">
                <span class="info-label">Coordinates:</span>
                <span class="info-value">${data.latitude.toFixed(6)}, ${data.longitude.toFixed(6)}</span>
            </div>
            </div>
        `;
        
        panel.innerHTML = html;
        panel.classList.remove('hidden');
    }
    
    hideInfoPanel() {
        const panel = document.getElementById('info-panel-2d');
        if (panel) panel.classList.add('hidden');
    }
    
    zoomOutToAll() {
        this.hideInfoPanel();
        const zoomOutBtn = document.getElementById('zoom-out-2d');
        if (zoomOutBtn) zoomOutBtn.classList.add('hidden');
        
        if (this.originalBounds) {
            this.fitBounds(this.originalBounds);
        }
    }

    getColor(props) {
        const commodity = (props?.major_comm || '').toLowerCase();
        if (commodity.includes('gold')) return [255, 215, 0, 220];
        if (commodity.includes('copper')) return [184, 115, 51, 220];
        if (commodity.includes('silver')) return [192, 192, 192, 220];
        if (commodity.includes('iron')) return [139, 69, 19, 220];
        if (commodity.includes('zinc')) return [100, 149, 237, 220];
        return [231, 76, 60, 220];
    }

    fitBounds(bounds) {
        if (!this.map) return;
        this.map.fitBounds([
            [bounds.min_lon, bounds.min_lat],
            [bounds.max_lon, bounds.max_lat]
        ], { padding: 50, duration: 1000 });
    }

    resize() {
        if (this.map) this.map.resize();
    }
}

let map2d = null;
function initMap2D(token) {
    if (!map2d) map2d = new Map2D('map2d');
    map2d.init(token);
    return map2d;
}
