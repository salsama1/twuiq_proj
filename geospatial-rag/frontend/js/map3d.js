/**
 * GEOSPATIAL RAG - 3D TERRAIN MAP (DECK.GL + MAPBOX)
 * Flat points with click-to-zoom and detailed tooltips
 */

class Map3D {
    constructor(containerId = 'map3d') {
        this.containerId = containerId;
        this.map = null;
        this.overlay = null;
        this.currentData = [];
        this.initialized = false;
        this.originalBounds = null;
        
        this.settings = {
            pointRadius: 8,
            terrainExaggeration: 1.5
        };
        
        this.initialViewState = {
            longitude: 42.5,
            latitude: 23.5,
            zoom: 6,
            pitch: 60,
            bearing: -20
        };
    }

    init(mapboxToken) {
        if (this.initialized) return;
        
        if (!mapboxToken) {
            this.showTokenError();
            return;
        }

        mapboxgl.accessToken = mapboxToken;

        this.map = new mapboxgl.Map({
            container: this.containerId,
            style: 'mapbox://styles/mapbox/satellite-streets-v12',
            center: [this.initialViewState.longitude, this.initialViewState.latitude],
            zoom: this.initialViewState.zoom,
            pitch: this.initialViewState.pitch,
            bearing: this.initialViewState.bearing,
            antialias: true
        });

        this.map.addControl(new mapboxgl.NavigationControl(), 'top-right');
        this.map.addControl(new mapboxgl.FullscreenControl(), 'top-right');

        this.map.on('load', () => {
            // Add terrain
            this.map.addSource('mapbox-dem', {
                type: 'raster-dem',
                url: 'mapbox://mapbox.mapbox-terrain-dem-v1',
                tileSize: 512,
                maxzoom: 14
            });

            this.map.setTerrain({
                source: 'mapbox-dem',
                exaggeration: this.settings.terrainExaggeration
            });

            // Add sky
            this.map.addLayer({
                id: 'sky',
                type: 'sky',
                paint: {
                    'sky-type': 'atmosphere',
                    'sky-atmosphere-sun': [0.0, 90.0],
                    'sky-atmosphere-sun-intensity': 15
                }
            });

            this.initDeckGL();
            this.setupControls();
            this.initialized = true;
            console.log('3D Terrain ready');
        });
    }

    initDeckGL() {
        this.overlay = new deck.MapboxOverlay({
            interleaved: false,
            layers: []
        });

        this.map.addControl(this.overlay);
    }

    showTokenError() {
        document.getElementById(this.containerId).innerHTML = 
            `<div style="display:flex;align-items:center;justify-content:center;height:100%;background:#1a1a2e;color:#fff;flex-direction:column;padding:20px;text-align:center;">
                <h3>⚠️ Mapbox Token Required</h3>
                <p>Click ⚙️ Settings and enter your Mapbox token</p>
            </div>`;
    }

    setupControls() {
        // Point radius
        const radiusSlider = document.getElementById('col-radius');
        if (radiusSlider) {
            radiusSlider.addEventListener('input', (e) => {
                this.settings.pointRadius = parseInt(e.target.value) / 300;
                document.getElementById('col-radius-val').textContent = Math.round(this.settings.pointRadius);
                this.updateLayers();
            });
        }

        // Terrain exaggeration
        const terrainSlider = document.getElementById('terrain-exag');
        if (terrainSlider) {
            terrainSlider.addEventListener('input', (e) => {
                this.settings.terrainExaggeration = parseInt(e.target.value) / 10;
                document.getElementById('terrain-exag-val').textContent = (parseInt(e.target.value) / 10).toFixed(1);
                if (this.map) {
                    this.map.setTerrain({
                        source: 'mapbox-dem',
                        exaggeration: this.settings.terrainExaggeration
                    });
                }
            });
        }

        // Zoom out button
        const zoomOutBtn = document.getElementById('zoom-out-3d');
        if (zoomOutBtn) {
            zoomOutBtn.addEventListener('click', () => this.zoomOutToAll());
        }
    }

    displayData(visualization) {
        if (!this.initialized) {
            console.log('3D map not initialized');
            return;
        }

        if (!visualization?.geojson?.features?.length) {
            console.log('No data for 3D');
            return;
        }

        this.currentData = visualization.geojson.features.map((f, i) => ({
            position: f.geometry.coordinates,
            longitude: f.geometry.coordinates[0],
            latitude: f.geometry.coordinates[1],
            properties: f.properties
        }));

        this.originalBounds = visualization.bounds;
        document.getElementById('point-count-3d').textContent = `${this.currentData.length} points`;
        
        this.updateLayers();

        if (visualization.bounds) {
            this.fitBounds(visualization.bounds);
        }

        console.log(`Displayed ${this.currentData.length} points in 3D`);
    }

    updateLayers() {
        if (!this.overlay || !this.currentData.length) return;

        // Flat scatter points on terrain
        const scatterLayer = new deck.ScatterplotLayer({
            id: 'scatter-3d',
            data: this.currentData,
            getPosition: d => d.position,
            getFillColor: d => this.getColor(d.properties),
            getLineColor: [255, 255, 255, 200],
            getRadius: this.settings.pointRadius * 500,
            radiusMinPixels: 6,
            radiusMaxPixels: 20,
            stroked: true,
            lineWidthMinPixels: 2,
            pickable: true,
            autoHighlight: true,
            highlightColor: [255, 255, 0, 255],
            onHover: info => this.showTooltip(info),
            onClick: info => this.handleClick(info)
        });

        this.overlay.setProps({ layers: [scatterLayer] });
    }

    showTooltip(info) {
        const tooltip = document.getElementById('tooltip-3d');
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
        if (p.occ_imp) html += `<div class="tooltip-row"><span>Importance:</span> ${p.occ_imp}</div>`;
        if (p.elements) html += `<div class="tooltip-row"><span>Elements:</span> ${p.elements}</div>`;
        
        html += `<div class="tooltip-coords">📍 ${d.latitude.toFixed(6)}, ${d.longitude.toFixed(6)}</div>`;
        html += `<div class="tooltip-hint">Click to zoom</div>`;

        if (!tooltip) {
            const t = document.createElement('div');
            t.id = 'tooltip-3d';
            t.className = 'map-tooltip map-tooltip-dark';
            document.getElementById('view-map3d').appendChild(t);
        }
        
        const tt = document.getElementById('tooltip-3d');
        tt.innerHTML = html;
        tt.style.display = 'block';
        tt.style.left = (info.x + 10) + 'px';
        tt.style.top = (info.y + 10) + 'px';
    }

    handleClick(info) {
        if (!info.object) return;
        
        const d = info.object;
        
        // Show zoom out button
        const zoomOutBtn = document.getElementById('zoom-out-3d');
        if (zoomOutBtn) zoomOutBtn.classList.remove('hidden');
        
        // Fly to clicked point
        this.map.flyTo({
            center: [d.longitude, d.latitude],
            zoom: 14,
            pitch: 70,
            bearing: 0,
            duration: 1500
        });
    }

    zoomOutToAll() {
        // Hide zoom out button
        const zoomOutBtn = document.getElementById('zoom-out-3d');
        if (zoomOutBtn) zoomOutBtn.classList.add('hidden');
        
        if (this.originalBounds) {
            this.fitBounds(this.originalBounds);
        } else {
            this.map.flyTo({
                center: [this.initialViewState.longitude, this.initialViewState.latitude],
                zoom: this.initialViewState.zoom,
                pitch: this.initialViewState.pitch,
                bearing: this.initialViewState.bearing,
                duration: 1500
            });
        }
    }

    getColor(props) {
        const commodity = (props?.major_comm || '').toLowerCase();
        if (commodity.includes('gold')) return [255, 215, 0, 230];
        if (commodity.includes('copper')) return [184, 115, 51, 230];
        if (commodity.includes('silver')) return [192, 192, 192, 230];
        if (commodity.includes('iron')) return [139, 69, 19, 230];
        if (commodity.includes('zinc')) return [100, 149, 237, 230];
        return [231, 76, 60, 230];
    }

    fitBounds(bounds) {
        if (!this.map) return;
        this.map.fitBounds([
            [bounds.min_lon, bounds.min_lat],
            [bounds.max_lon, bounds.max_lat]
        ], { padding: 80, duration: 1500, pitch: 60, bearing: -20 });
    }

    resize() {
        if (this.map) this.map.resize();
    }
}

let map3d = null;
function initMap3D(token) {
    if (!map3d) map3d = new Map3D('map3d');
    return map3d;
}
