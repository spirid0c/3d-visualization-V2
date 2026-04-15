import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// ---- Settings / Meta ----
const PARAMS = {
    lons: 192,
    lats: 94,
    frames: 91,
    currentFrame: 0,
    datasetIndex: 1, // 1 for PWAT1, 2 for PWAT2
    seasonIndex: 0,  // 0=Jan, 1=July
    viewMode: 0,     // 0 = 3D, 1 = 2D, 2 = SPLIT
};

// Gaussian Latitude levels (from flx.ctl) - Row 0 = North, Row 93 = South
const GAUSSIAN_LATS = [
    88.542, 86.653, 84.753, 82.851, 80.947, 79.043, 77.139, 75.235, 73.331, 71.426,
    69.522, 67.617, 65.713, 63.808, 61.903, 59.999, 58.094, 56.189, 54.285, 52.380,
    50.475, 48.571, 46.666, 44.761, 42.856, 40.952, 39.047, 37.142, 35.238, 33.333,
    31.428, 29.523, 27.619, 25.714, 23.809, 21.904, 20.000, 18.095, 16.190, 14.286,
    12.381, 10.476, 8.571, 6.667, 4.762, 2.857, 0.952, -0.952, -2.857, -4.762,
    -6.667, -8.571, -10.476, -12.381, -14.286, -16.190, -18.095, -20.000, -21.904, -23.809,
    -25.714, -27.619, -29.523, -31.428, -33.333, -35.238, -37.142, -39.047, -40.952, -42.856,
    -44.761, -46.666, -48.571, -50.475, -52.380, -54.285, -56.189, -58.094, -59.999, -61.903,
    -63.808, -65.713, -67.617, -69.522, -71.426, -73.331, -75.235, -77.139, -79.043, -80.947,
    -82.851, -84.753, -86.653, -88.542
];

// ---- Source de verite : make_summer.gs / flx.ctl ----
const SEASONS = [
    {
        prefix: 'jpbz_201707',
        label: 'Summer 2017 — JP tracer (00Z01JUL2017)',
        tdefStart: new Date('2017-07-01T00:00:00Z'),
        increment: 86400000
    },
    {
        prefix: 'jpbz_1_2018',
        label: 'Winter 2018 — JP tracer (00Z01JAN2018)',
        tdefStart: new Date('2018-01-01T00:00:00Z'),
        increment: 86400000
    }
];

let buffer1 = null;
let buffer2 = null;
let dataTexture = null;
let material = null;

// ---- UI Bindings ----
const uiLabelSet = document.getElementById('dataset-label');
const uiLabelFrame = document.getElementById('frame-label');
const uiDateDisplay = document.getElementById('date-display');
const sliderTime = document.getElementById('time-slider');
const btnToggle = document.getElementById('toggle-data');
const btnPlay = document.getElementById('btn-play');
const uiSeasonSelector = document.getElementById('season-selector');
const btnToggleView = document.getElementById('btn-toggle-view');

let globe = null;
let graticule = null;
let coastMesh = null;
let basePlane = null;

// 2D Canvas setup (Transparent HUD Layer)
const canvas2D = document.getElementById('canvas-2d');
const ctx2D = canvas2D.getContext('2d', { alpha: true }); // Must be true to see WebGL behind
const canvas2DContainer = document.getElementById('canvas-2d-container');
const mainContent = document.getElementById('main-content');

function resize2DCanvas() {
    if (canvas2DContainer.style.display === 'none') return;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas2DContainer.getBoundingClientRect();
    if (rect.width === 0) return;

    // Calcul de la taille max en conservant le ratio strict de 2.04
    let targetW = rect.width * 0.95;
    let targetH = targetW / 2.04;
    
    if (targetH > rect.height * 0.95) {
        targetH = rect.height * 0.95;
        targetW = targetH * 2.04;
    }

    // Taille physique de la zone de dessin (Retina/High-DPI)
    canvas2D.width = targetW * dpr;
    canvas2D.height = targetH * dpr;

    // Taille visuelle bloquée pour empêcher le CSS d'étirer l'image
    canvas2D.style.width = targetW + 'px';
    canvas2D.style.height = targetH + 'px';

    // SYNCHRONISATION : Calcul de la distance Z dynamique (camera2D)
    const vFOV = camera2D.fov * Math.PI / 180;
    const finalZ = (rect.height / targetH) / (2 * Math.tan(vFOV / 2));
    camera2D.position.set(0, 0, finalZ);
}

function updateCameras() {
    const W = mainContent.clientWidth;
    const H = mainContent.clientHeight;
    // Si on est en Split (mode 2), la largeur est divisée par 2
    const aspect = (PARAMS.viewMode === 2) ? (W / 2) / H : (W / H);
    
    camera2D.aspect = aspect; 
    camera2D.updateProjectionMatrix();
    camera3D.aspect = aspect; 
    camera3D.updateProjectionMatrix();
    
    renderer.setSize(W, H);
    resize2DCanvas();
}

// Offscreen Buffer for Bilinear Interpolation (192x94 native resolution)
const offscreenCanvas = document.createElement('canvas');
offscreenCanvas.width = 192;
offscreenCanvas.height = 94;
const offscreenCtx = offscreenCanvas.getContext('2d', { alpha: true });

let coastlinesGeoJSON = null;

sliderTime.min = 0;
sliderTime.max = PARAMS.frames - 1;

// ---- Auto-Play State ----
let isPlaying = false;
let lastFrameTime = 0;
const FPS = 12;
const MS_PER_FRAME = 1000 / FPS;

// ---- Three.js Setup ----
const container = document.getElementById('canvas-container');
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x050505); // Global Black Workspace

const camera2D = new THREE.PerspectiveCamera(45, (mainContent.clientWidth / 2) / mainContent.clientHeight, 0.1, 100);
const camera3D = new THREE.PerspectiveCamera(45, (mainContent.clientWidth / 2) / mainContent.clientHeight, 0.1, 100);
camera3D.position.set(0, 0, 3.5);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(mainContent.clientWidth, mainContent.clientHeight);
renderer.setPixelRatio(window.devicePixelRatio);
container.appendChild(renderer.domElement);

const controls = new OrbitControls(camera3D, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.05;

// ---- 1. Base Globe ----
const globeGeom = new THREE.SphereGeometry(1.0, 64, 64);
const globeMat = new THREE.MeshBasicMaterial({ color: 0x2a2a2a });
globe = new THREE.Mesh(globeGeom, globeMat);
scene.add(globe);

// ---- 2. Graticule ----
const graticuleMat = new THREE.LineBasicMaterial({ color: 0x444444, transparent: true, opacity: 0.5 });
const graticuleGeom = new THREE.BufferGeometry();
const graticulePoints = [];
const radiusGraticule = 1.001;

for (let lon = -180; lon <= 180; lon += 15) {
    const lonRad = lon * Math.PI / 180;
    for (let lat = -90; lat <= 90; lat += 2) {
        const latRad = lat * Math.PI / 180;
        const x = radiusGraticule * Math.cos(latRad) * Math.cos(lonRad);
        const y = radiusGraticule * Math.sin(latRad);
        const z = -radiusGraticule * Math.cos(latRad) * Math.sin(lonRad);
        graticulePoints.push(new THREE.Vector3(x, y, z));
    }
}
for (let lat = -90; lat <= 90; lat += 15) {
    const latRad = lat * Math.PI / 180;
    for (let lon = -180; lon <= 180; lon += 2) {
        const lonRad = lon * Math.PI / 180;
        const x = radiusGraticule * Math.cos(latRad) * Math.cos(lonRad);
        const y = radiusGraticule * Math.sin(latRad);
        const z = -radiusGraticule * Math.cos(latRad) * Math.sin(lonRad);
        graticulePoints.push(new THREE.Vector3(x, y, z));
    }
}
graticuleGeom.setFromPoints(graticulePoints);
graticule = new THREE.LineSegments(graticuleGeom, graticuleMat);
scene.add(graticule);

// ---- 2b. Coastlines ----
function loadCoastlines() {
    fetch('countries.geojson')
        .then(res => res.json())
        .then(data => {
            coastlinesGeoJSON = data; 
            const mat = new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.9, depthWrite: false });
            const R = 1.005; 
            const positions = [];
            data.features.forEach(f => {
                const rings = (f.geometry.type === 'Polygon') ? [f.geometry.coordinates] : f.geometry.coordinates;
                rings.forEach(poly => poly.forEach(ring => {
                    for (let n = 0; n < ring.length - 1; n++) {
                        if (Math.abs(ring[n][0] - ring[n+1][0]) > 180) continue;
                        const l1 = ring[n][0]*Math.PI/180; const a1 = ring[n][1]*Math.PI/180;
                        const l2 = ring[n+1][0]*Math.PI/180; const a2 = ring[n+1][1]*Math.PI/180;
                        positions.push(R*Math.cos(a1)*Math.cos(l1), R*Math.sin(a1), -R*Math.cos(a1)*Math.sin(l1));
                        positions.push(R*Math.cos(a2)*Math.cos(l2), R*Math.sin(a2), -R*Math.cos(a2)*Math.sin(l2));
                    }
                }));
            });
            const geom = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
            coastMesh = new THREE.LineSegments(geom, mat);
            coastMesh.renderOrder = 3;
            scene.add(coastMesh);
        });
}
loadCoastlines();

// ---- 3. Unified Shader Layer ----
const initialData = new Float32Array(PARAMS.lons * PARAMS.lats);
dataTexture = new THREE.DataTexture(initialData, PARAMS.lons, PARAMS.lats, THREE.RedFormat, THREE.FloatType);
dataTexture.generateMipmaps = false; 
dataTexture.minFilter = THREE.LinearFilter;
dataTexture.magFilter = THREE.LinearFilter;
dataTexture.wrapS = THREE.ClampToEdgeWrapping;
dataTexture.wrapT = THREE.ClampToEdgeWrapping;
dataTexture.needsUpdate = true;

const _VS = `
varying vec2 vUv;
void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const _FS = `
uniform sampler2D tData;
uniform float u_is3D;
varying vec2 vUv;

vec3 getColor(float val) {
    if (val < 0.001 || val > 1.0e15) return vec3(0.18, 0.44, 0.77); // Unified GrADS Blue
    if (val < 0.002) return vec3(0.70, 0.90, 1.00);
    if (val < 0.005) return vec3(0.40, 0.80, 1.00);
    if (val < 0.01)  return vec3(0.00, 1.00, 1.00);
    if (val < 0.02)  return vec3(0.00, 0.80, 0.00);
    if (val < 0.05)  return vec3(0.50, 1.00, 0.00);
    if (val < 0.1)   return vec3(1.00, 1.00, 0.00);
    if (val < 0.2)   return vec3(1.00, 0.80, 0.00);
    if (val < 0.5)   return vec3(1.00, 0.60, 0.00);
    if (val < 1.0)   return vec3(1.00, 0.40, 0.00);
    if (val < 2.0)   return vec3(1.00, 0.00, 0.00);
    if (val < 5.0)   return vec3(0.80, 0.00, 0.00);
    if (val < 10.0)  return vec3(0.60, 0.00, 0.00);
    return vec3(1.00, 0.00, 1.00);
}

void main() {
    vec2 finalUv;
    if (u_is3D > 0.5) {
        float lon = vUv.x * 360.0 - 180.0;
        float gribLon = (lon < 0.0 ? lon + 360.0 : lon);
        finalUv = vec2(gribLon / 360.0, 1.0 - vUv.y);
    } else {
        // Mirror 2D : Identité pure
        finalUv = vec2(vUv.x, 1.0 - vUv.y);
    }
    float val = texture2D(tData, finalUv).r;
    gl_FragColor = vec4(getColor(val), 1.0);
}
`;

material = new THREE.ShaderMaterial({
    uniforms: { 
        tData: { value: dataTexture },
        u_is3D: { value: 1.0 } // Default to 3D
    },
    vertexShader: _VS, fragmentShader: _FS, side: THREE.DoubleSide
});

const dataSphere = new THREE.Mesh(new THREE.SphereGeometry(1.002, 64, 64), material);
dataSphere.renderOrder = 2;
scene.add(dataSphere);

const dataPlaneGeom = new THREE.PlaneGeometry(2.04, 1.0); // Ratio 192/94
const dataPlane = new THREE.Mesh(dataPlaneGeom, material);
dataPlane.position.set(0, 0, 0.0); // Exactly at origin for 2D mode
dataPlane.rotation.set(0, 0, 0); // No tilt
dataPlane.frustumCulled = false;
dataPlane.visible = false;
dataPlane.renderOrder = 2; 
scene.add(dataPlane);

// ---- 3c. 2D Base Ground (The "Surface" Twin) ----
const basePlaneGeom = new THREE.PlaneGeometry(2.04, 1.0);
const basePlaneMat = new THREE.MeshBasicMaterial({ color: 0x1a1a1a }); 
basePlane = new THREE.Mesh(basePlaneGeom, basePlaneMat);
basePlane.position.set(0, 0, -0.01); // Standard depth layering
basePlane.visible = false;
basePlane.renderOrder = 1; 
scene.add(basePlane);

// ---- Markers ----
const markers = [];
function createMarker(lat, lon, labelText, r = 1.11) {
    const latRad = lat * Math.PI / 180; const lonRad = lon * Math.PI / 180;
    const x = r * Math.cos(latRad) * Math.cos(lonRad);
    const y = r * Math.sin(latRad);
    const z = -r * Math.cos(latRad) * Math.sin(lonRad);
    const group = new THREE.Group(); group.position.set(x, y, z);
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(0.02), new THREE.MeshBasicMaterial({ color: 0xffff00 }));
    group.add(mesh);
    const canvas = document.createElement('canvas'); canvas.width = 128; canvas.height = 64;
    const ctx = canvas.getContext('2d'); ctx.font = 'bold 44px Arial'; ctx.fillStyle = '#fff';
    ctx.strokeStyle = '#000'; ctx.lineWidth = 3; ctx.textAlign = 'center'; ctx.fillText(labelText, 64, 32); ctx.strokeText(labelText, 64, 32);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas) }));
    sprite.scale.set(0.18, 0.09, 1); sprite.position.y = 0.05; group.add(sprite);
    scene.add(group); markers.push(group);
}
createMarker(36, 138, "JP"); createMarker(-10, -55, "BZ");

// ---- Data Loop ----
async function loadData() {
    const season = SEASONS[PARAMS.seasonIndex];
    const res1 = await fetch(season.prefix + '_pwat1_91frames.bin');
    if (res1.ok) buffer1 = new Float32Array(await res1.arrayBuffer());
    const res2 = await fetch(season.prefix + '_pwat2_91frames.bin');
    if (res2.ok) buffer2 = new Float32Array(await res2.arrayBuffer());
    updateFrame();
}

function updateFrame() {
    const active = PARAMS.datasetIndex === 1 ? buffer1 : buffer2;
    if (!active) return;
    const frameData = active.subarray(PARAMS.currentFrame * 192 * 94, (PARAMS.currentFrame + 1) * 192 * 94);
    dataTexture.image.data.set(frameData);
    dataTexture.needsUpdate = true;
    
    // Update Slider UI
    sliderTime.value = PARAMS.currentFrame;

    const d = new Date(SEASONS[PARAMS.seasonIndex].tdefStart.getTime() + PARAMS.currentFrame * 86400000);
    const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
    uiDateDisplay.innerText = `${String(d.getUTCDate()).padStart(2, '0')} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
    uiLabelFrame.innerText = `${PARAMS.currentFrame + 1} / 91`;
    if (!PARAMS.is3D) render2D();
}

function render2D() {
    if (!ctx2D || canvas2D.width === 0) return;
    const W = canvas2D.width; const H = canvas2D.height;
    ctx2D.clearRect(0, 0, W, H); // Clears to transparency because alpha:true
    const lonToX = (lon) => { 
        let l = lon; if (l < 0) l += 360; 
        return (l / 360.0) * W; 
    };
    const latToY = (lat) => {
        // Recherche d'index + Interpolation Linéaire Mathématique (Zéro Snapping)
        let i = 0;
        for (; i < 93; i++) {
            if (GAUSSIAN_LATS[i] >= lat && lat > GAUSSIAN_LATS[i+1]) break;
        }
        const lat_n = GAUSSIAN_LATS[i];
        const lat_s = GAUSSIAN_LATS[i+1];
        const t = (lat - lat_n) / (lat_s - lat_n); 
        return ((i + t) / 94.0) * H;
    };
    if (coastlinesGeoJSON) {
        ctx2D.strokeStyle = 'rgba(255, 255, 255, 0.7)'; // Softer HUD
        ctx2D.lineWidth = 1 * (window.devicePixelRatio || 1); 
        ctx2D.beginPath();
        coastlinesGeoJSON.features.forEach(f => {
            const rings = (f.geometry.type === 'Polygon') ? [f.geometry.coordinates] : f.geometry.coordinates;
            rings.forEach(poly => poly.forEach(ring => {
                for (let n = 0; n < ring.length; n++) {
                    const lat = ring[n][1];
                    if (lat < -88 || lat > 88) continue; 

                    // Convert current longitude to 0-360 space
                    let lon = ring[n][0];
                    let l_360 = lon < 0 ? lon + 360 : lon; 
                    const x = (l_360 / 360.0) * W; 
                    const y = latToY(lat);
                    
                    if (n === 0) {
                        ctx2D.moveTo(x, y);
                    } else {
                        // Convert previous longitude to 0-360 space
                        let prevLon = ring[n-1][0];
                        let prevL_360 = prevLon < 0 ? prevLon + 360 : prevLon;
                        
                        // If the horizontal gap exceeds 180 degrees in 360-space, it's a wrap-around jump
                        if (Math.abs(l_360 - prevL_360) > 180) {
                            ctx2D.moveTo(x, y);
                        } else {
                            ctx2D.lineTo(x, y);
                        }
                    }
                }
            }));
        });
        ctx2D.stroke();
    }

    // --- Dessin des Pins JP et BZ ---
    const dpr = window.devicePixelRatio || 1;
    const drawPin = (lat, lon, label) => {
        let l_360 = lon < 0 ? lon + 360 : lon;
        const x = (l_360 / 360.0) * W; 
        const y = latToY(lat);

        // Point jaune
        ctx2D.beginPath();
        ctx2D.arc(x, y, 4 * dpr, 0, 2 * Math.PI);
        ctx2D.fillStyle = '#ffff00';
        ctx2D.fill();
        ctx2D.lineWidth = 1 * dpr;
        ctx2D.strokeStyle = '#000000';
        ctx2D.stroke();

        // Texte High-DPI (Blanc avec contour noir)
        const fontSize = 14 * dpr;
        ctx2D.font = `bold ${fontSize}px Arial`;
        ctx2D.textAlign = 'center';
        const textY = y - (10 * dpr); // Remonte le texte au-dessus du point
        
        ctx2D.lineWidth = 3 * dpr;
        ctx2D.strokeStyle = '#000000';
        ctx2D.strokeText(label, x, textY); // Contour
        ctx2D.fillStyle = '#ffffff';
        ctx2D.fillText(label, x, textY);   // Remplissage
    };

    drawPin(36, 138, "JP");
    drawPin(-10, -55, "BZ");
}

// ---- Events ----
sliderTime.addEventListener('input', (e) => { isPlaying = false; PARAMS.currentFrame = parseInt(e.target.value); updateFrame(); });
btnToggle.addEventListener('click', () => { PARAMS.datasetIndex = PARAMS.datasetIndex === 1 ? 2 : 1; uiLabelSet.innerText = PARAMS.datasetIndex === 1 ? 'PWAT1 — Japan' : 'PWAT2 — Brazil'; updateFrame(); });
uiSeasonSelector.addEventListener('change', (e) => { PARAMS.seasonIndex = parseInt(e.target.value); loadData(); });
btnPlay.addEventListener('click', () => {
    if (!buffer1 && !buffer2) return;
    isPlaying = !isPlaying;
    btnPlay.textContent = isPlaying ? '⏸ Pause' : '▶ Play';
    if (isPlaying) {
        lastFrameTime = performance.now(); // Solid sync on Play
        btnPlay.classList.add('playing');
    } else {
        btnPlay.classList.remove('playing');
    }
});

btnToggleView.addEventListener('click', () => {
    // Cycle : 0 (3D) -> 1 (2D) -> 2 (SPLIT) -> 0
    PARAMS.viewMode = (PARAMS.viewMode + 1) % 3;
    
    const labels = ['Vue : Globe 3D', 'Vue : Plan 2D', 'Vue : Comparative'];
    btnToggleView.innerText = labels[PARAMS.viewMode];

    if (PARAMS.viewMode === 0) {
        // MODE 3D
        canvas2DContainer.style.display = 'none';
        camera3D.position.set(0, 0, 3.5);
    } else if (PARAMS.viewMode === 1) {
        // MODE 2D
        canvas2DContainer.style.display = 'flex';
        canvas2DContainer.style.width = '100%';
        canvas2DContainer.style.borderRight = 'none';
        dataPlane.rotation.set(0, 0, 0); 
        dataPlane.position.set(0, 0, 0);
    } else {
        // MODE COMPARATIF (SPLIT)
        canvas2DContainer.style.display = 'flex';
        canvas2DContainer.style.width = '50%';
        canvas2DContainer.style.borderRight = '2px solid #333';
        dataPlane.rotation.set(0, 0, 0); 
        dataPlane.position.set(0, 0, 0);
        camera3D.position.set(0, 0, 3.5);
    }
    
    updateCameras();
    camera2D.lookAt(0, 0, 0); 
    camera3D.lookAt(0, 0, 0); 
    updateFrame();
});

// Initialization
updateCameras();
camera2D.lookAt(0, 0, 0); 
camera3D.lookAt(0, 0, 0); 
updateFrame();

function animateLoop(t) {
    requestAnimationFrame(animateLoop);
    controls.update();

    if (isPlaying && (t - lastFrameTime >= MS_PER_FRAME)) {
        lastFrameTime = t;
        PARAMS.currentFrame = (PARAMS.currentFrame + 1) % 91;
        updateFrame();
    }

    const W = mainContent.clientWidth;
    const H = mainContent.clientHeight;

    if (PARAMS.viewMode === 0) {
        // --- RENDU 100% 3D ---
        renderer.setViewport(0, 0, W, H);
        renderer.setScissorTest(false);
        material.uniforms.u_is3D.value = 1.0;

        dataPlane.visible = false; basePlane.visible = false;
        dataSphere.visible = true; globe.visible = true; graticule.visible = true; coastMesh.visible = true;
        
        const camDir = camera3D.position.clone().normalize();
        markers.forEach(m => { m.visible = (camDir.dot(m.position.clone().normalize()) > 0); });
        renderer.render(scene, camera3D);

    } else if (PARAMS.viewMode === 1) {
        // --- RENDU 100% 2D ---
        renderer.setViewport(0, 0, W, H);
        renderer.setScissorTest(false);
        material.uniforms.u_is3D.value = 0.0;

        dataPlane.visible = true; basePlane.visible = true;
        dataSphere.visible = false; globe.visible = false; graticule.visible = false; coastMesh.visible = false;
        markers.forEach(m => { m.visible = false; });
        renderer.render(scene, camera2D);

    } else if (PARAMS.viewMode === 2) {
        // --- RENDU COMPARATIF (SPLIT) ---
        const halfW = W / 2;
        renderer.setScissorTest(true);

        // GAUCHE (2D)
        renderer.setViewport(0, 0, halfW, H);
        renderer.setScissor(0, 0, halfW, H);
        material.uniforms.u_is3D.value = 0.0;
        dataPlane.visible = true; basePlane.visible = true;
        dataSphere.visible = false; globe.visible = false; graticule.visible = false; coastMesh.visible = false;
        markers.forEach(m => { m.visible = false; });
        renderer.render(scene, camera2D);

        // DROITE (3D)
        renderer.setViewport(halfW, 0, halfW, H);
        renderer.setScissor(halfW, 0, halfW, H);
        material.uniforms.u_is3D.value = 1.0;
        dataPlane.visible = false; basePlane.visible = false;
        dataSphere.visible = true; globe.visible = true; graticule.visible = true; coastMesh.visible = true;
        const camDir = camera3D.position.clone().normalize();
        markers.forEach(m => { m.visible = (camDir.dot(m.position.clone().normalize()) > 0); });
        renderer.render(scene, camera3D);

        renderer.setScissorTest(false);
    }
}
requestAnimationFrame(animateLoop);

window.addEventListener('resize', updateCameras);
loadData();
