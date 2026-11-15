// One persistent WebGL scene. Pure function of backend data (graph payload) + mode. Redaction is decided by the server:
// restricted nodes arrive as opaque placeholders and are drawn as striped blanks; this file never sees their content.
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {EffectComposer} from 'three/addons/postprocessing/EffectComposer.js';
import {RenderPass} from 'three/addons/postprocessing/RenderPass.js';
import {UnrealBloomPass} from 'three/addons/postprocessing/UnrealBloomPass.js';
import {OutputPass} from 'three/addons/postprocessing/OutputPass.js';
import {CSS2DRenderer, CSS2DObject} from 'three/addons/renderers/CSS2DRenderer.js';

const COL = {VERIFIED: 0x3ddc97, INFERRED: 0xf5b942, CONFLICT: 0xff5a4d, MISSING: 0x8b95a1, TESTIMONY: 0xa78bfa,
  public: 0x3ddc97, team: 0xf5b942, confidential: 0xff5a4d, person: 0x6fb3ff, restricted: 0x2a2f36};
const EDGE = {cites: [.29, .36, .42], holds: [.30, .55, 1], dep: [.96, .72, .26], conflict: [1, .35, .3]};
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));

export const scene = {mode: 'landing', docked: false, N: [], byId: new Map(), E: [], sel: null, hov: null, sim: null, ready: false,
  filter: {type: 'all', cut: ''}, handlers: {}, stats: {fps: 60}, dates: []};
const X = {}; const pos = new Map(); const pulses = [];
let T = 0, last = performance.now(), probe = [], probed = false;

const NODE_VS = 'varying vec3 vN,vV,vP;void main(){vN=normalize(normalMatrix*normal);vP=position;vec4 m=modelViewMatrix*vec4(position,1.);vV=-m.xyz;gl_Position=projectionMatrix*m;}';
const NODE_FS = 'varying vec3 vN,vV,vP;uniform vec3 uC;uniform float uD,uO,uF,uR,uG,uT;void main(){vec3 n=normalize(vN);float f=pow(1.-max(dot(n,normalize(vV)),0.),2.4);float l=.32+.68*max(dot(n,normalize(vec3(.4,.8,.6))),0.);' +
  'vec3 c=mix(uC,vec3(.9,.08,.05),uF*.8);c=c*(l+f*1.4)*uD;c+=uC*uG*(.35+.35*sin(uT*5.));' +
  'float s=step(.5,fract((vP.x+vP.y+vP.z)*5.5));vec3 red=mix(vec3(.01),vec3(.16,.17,.2),s)+vec3(.35,.05,.04)*f;c=mix(c,red,uR);gl_FragColor=vec4(c,uO);\n#include <colorspace_fragment>\n}';

function nodeMat(col) {
  return new THREE.ShaderMaterial({transparent: true, depthWrite: false, vertexShader: NODE_VS, fragmentShader: NODE_FS,
    uniforms: {uC: {value: new THREE.Color(col)}, uD: {value: 1}, uO: {value: 1}, uF: {value: 0}, uR: {value: 0}, uG: {value: 0}, uT: {value: 0}}});
}
const mkTex = fn => { const k = document.createElement('canvas'); k.width = k.height = 64; fn(k.getContext('2d')); return new THREE.CanvasTexture(k); };

export function init(canvas, labelsEl) {
  X.cv = canvas; X.labelsEl = labelsEl;
  try { X.r = new THREE.WebGLRenderer({canvas, antialias: true, powerPreference: 'high-performance'}); } catch (e) { canvas.style.display = 'none'; scene.ready = false; return false; }
  const lo = innerWidth < 700 || (navigator.hardwareConcurrency || 8) <= 4;
  X.lo = lo; X.r.setPixelRatio(lo ? 1 : Math.min(devicePixelRatio, 1.75));
  X.sc = new THREE.Scene(); X.cam = new THREE.PerspectiveCamera(52, 1, .1, 300); X.cam.position.set(0, 4, 26);
  X.grp = new THREE.Group(); X.sc.add(X.grp);
  X.ctl = new OrbitControls(X.cam, canvas); X.ctl.enableDamping = true; X.ctl.dampingFactor = .07; X.ctl.enablePan = false; X.ctl.minDistance = 6; X.ctl.maxDistance = 60; X.ctl.autoRotate = true; X.ctl.autoRotateSpeed = .45; X.ctl.enabled = false;
  X.U = {uT: {value: 0}, uA: {value: 1}, uTint: {value: new THREE.Vector3(.0, .5, .45)}};
  const bg = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShaderMaterial({uniforms: X.U, depthTest: false, depthWrite: false,
    vertexShader: 'varying vec2 vUv;void main(){vUv=uv;gl_Position=vec4(position.xy,.9999,1.);}',
    fragmentShader: 'varying vec2 vUv;uniform float uT,uA;uniform vec3 uTint;float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h(i),h(i+vec2(1.,0.)),f.x),mix(h(i+vec2(0.,1.)),h(i+vec2(1.,1.)),f.x),f.y);}float fbm(vec2 p){float v=0.,a=.5;for(int i=0;i<5;i++){v+=a*n(p);p*=2.02;a*=.5;}return v;}' +
      'void main(){vec2 p=(vUv-.5)*vec2(uA,1.)*2.6;float t=uT*.04;float w=fbm(p+t);float f=fbm(p+w*1.7-t);vec3 c=mix(vec3(.012,.02,.03),vec3(.03,.07,.1),f);c+=uTint*smoothstep(.5,1.,f)*.16;c+=vec3(.5,.07,.05)*smoothstep(.62,.95,fbm(p*1.3-w+4.))*.1;vec2 q=vUv-.5;c*=1.-1.5*dot(q,q);c+=(h(gl_FragCoord.xy+uT)-.5)/255.;gl_FragColor=vec4(pow(max(c,0.),vec3(2.2)),1.);\n#include <colorspace_fragment>\n}'}));
  bg.frustumCulled = false; bg.renderOrder = -10; X.sc.add(bg);
  X.HT = mkTex(x => { const g = x.createRadialGradient(32, 32, 0, 32, 32, 32); g.addColorStop(0, 'rgba(255,255,255,.95)'); g.addColorStop(1, 'rgba(255,255,255,0)'); x.fillStyle = g; x.fillRect(0, 0, 64, 64); });
  X.RT = mkTex(x => { x.strokeStyle = '#fff'; x.lineWidth = 4; x.beginPath(); x.arc(32, 32, 26, 0, 7); x.stroke(); });
  // case core: the evidence all converges on
  X.core = new THREE.Group();
  const wf = new THREE.Mesh(new THREE.IcosahedronGeometry(1.5, 1), new THREE.MeshBasicMaterial({color: 0x5eead4, wireframe: true, transparent: true, opacity: .55, blending: THREE.AdditiveBlending, depthWrite: false}));
  const gl = new THREE.Sprite(new THREE.SpriteMaterial({map: X.HT, color: 0x5eead4, transparent: true, opacity: .5, blending: THREE.AdditiveBlending, depthWrite: false})); gl.scale.setScalar(9);
  X.core.add(wf, gl); X.core.userData = {wf, gl}; X.grp.add(X.core);
  const dn = lo || REDUCED ? 0 : 420, dp = new Float32Array(dn * 3); for (let i = 0; i < dn * 3; i++) dp[i] = (Math.random() - .5) * 70;
  const dg = new THREE.BufferGeometry(); dg.setAttribute('position', new THREE.BufferAttribute(dp, 3));
  X.dust = new THREE.Points(dg, new THREE.PointsMaterial({size: .07, color: 0x9fb4ba, transparent: true, opacity: .4, depthWrite: false})); X.sc.add(X.dust);
  X.lab = new CSS2DRenderer({element: labelsEl}); X.tip = document.createElement('div'); X.tip.className = 'lbl'; X.tipObj = new CSS2DObject(X.tip); X.tipObj.visible = false; X.grp.add(X.tipObj);
  X.ray = new THREE.Raycaster(); X.mv = new THREE.Vector2(); X.tmp = new THREE.Vector3();
  buildComposer(); fit(); new ResizeObserver(fit).observe(document.body); addEventListener('resize', fit);
  addEventListener('pointermove', e => { X.mx = e.clientX / innerWidth - .5; X.my = e.clientY / innerHeight - .5; }, {passive: true});
  canvas.addEventListener('pointermove', onMove); canvas.addEventListener('pointerleave', () => hover(null));
  let dn0 = null; canvas.addEventListener('pointerdown', e => { dn0 = [e.clientX, e.clientY]; });
  canvas.addEventListener('pointerup', e => { if (dn0 && Math.hypot(e.clientX - dn0[0], e.clientY - dn0[1]) < 5 && scene.docked) { const n = pick(e); scene.select(n && n.id); } dn0 = null; });
  canvas.addEventListener('webglcontextlost', e => { e.preventDefault(); X.lost = true; });
  canvas.addEventListener('webglcontextrestored', () => { X.lost = false; scene.setGraph(X.lastGraph, true); });
  canvas.addEventListener('keydown', onKey); canvas.tabIndex = -1;
  scene.ready = true; scene.mx = 0; requestAnimationFrame(loop); return true;
}

function buildComposer() {
  X.bloom = null; X.comp = null;
  if (X.lo) return;
  X.comp = new EffectComposer(X.r); X.comp.addPass(new RenderPass(X.sc, X.cam));
  X.bloom = new UnrealBloomPass(new THREE.Vector2(512, 512), .75, .6, .18); X.comp.addPass(X.bloom); X.comp.addPass(new OutputPass());
}
function fit() {
  if (!X.r) return; const h = X.cv.parentElement === document.body ? null : X.cv.parentElement;
  const w = h ? h.clientWidth : innerWidth, H = h ? h.clientHeight : innerHeight; if (!w || !H) return;
  X.r.setSize(w, H, false); X.cam.aspect = w / H; X.cam.updateProjectionMatrix(); X.U.uA.value = w / H; X.comp && X.comp.setSize(w, H); X.lab.setSize(w, H);
}

/* ---------- graph ---------- */
export function layout(N, E) {
  const hasClaims = N.some(n => n.kind === 'claim');
  N.forEach((n, i) => { n.p = (pos.get(n.id) || new THREE.Vector3()).clone(); if (!pos.has(n.id)) { const a = i / N.length * Math.PI * 2; n.p.set(Math.cos(a) * 8 + (Math.random() - .5), (Math.random() - .5) * 6, Math.sin(a) * 8 + (Math.random() - .5)); } n.v = new THREE.Vector3(); });
  if (!hasClaims) { const s = N.filter(n => n.kind === 'src'); s.forEach((n, i) => { const a = i / s.length * Math.PI * 2 - Math.PI / 2; n.p.set(Math.cos(a) * 8, Math.sin(i * 1.7) * 1.6, Math.sin(a) * 8); }); return; }
  const fresh = N.some(n => !pos.has(n.id)), it = fresh ? 220 : 0;
  for (let k = 0; k < it; k++) {
    for (const a of N) { for (const b of N) { if (a === b) continue; const q = a.p.clone().sub(b.p), d = Math.max(.4, q.lengthSq()); a.v.add(q.multiplyScalar((a.kind === 'src' && b.kind === 'src' ? 2.4 : 1.2) / d)); } a.v.addScaledVector(a.p, -.012); }
    for (const e of E) { const a = e.a, b = e.b, q = b.p.clone().sub(a.p), f = (q.length() - (e.kind === 'dep' ? 2.4 : 3.4)) * .02; q.normalize().multiplyScalar(f); a.v.add(q); b.v.sub(q); }
    N.forEach(n => { n.p.add(n.v.multiplyScalar(.5)); n.v.multiplyScalar(.6); });
  }
}

scene.setGraph = function (g, force) {
  if (!scene.ready) return; X.lastGraph = g;
  const sig = JSON.stringify(g.nodes.map(n => [n.id, n.restricted ? 1 : 0, n.state, n.status, n.label && n.label.length])) + g.edges.length;
  if (!force && sig === X.sig) return; X.sig = sig;
  const prev = new Map(scene.byId);
  for (const o of [...X.grp.children]) if (o !== X.core && o !== X.tipObj) { o.traverse(c => c.element && c.element.remove()); X.grp.remove(o); o.geometry && o.geometry.dispose(); o.material && o.material.dispose && o.material.dispose(); }
  const N = [], byId = new Map(), now = performance.now() / 1000;
  g.nodes.forEach((d, i) => {
    const old = prev.get(d.id), kind = d.kind, red = !!d.restricted;
    const size = kind === 'src' ? .75 : kind === 'person' ? .35 + .05 * (d.count || 1) : red ? .4 : .26 + .34 * (d.confidence || .4);
    const col = red ? COL.restricted : kind === 'src' ? COL[d.acl] : kind === 'person' ? ((d.solo || 0) >= 2 ? COL.CONFLICT : COL.person) : COL[d.state];
    const geo = kind === 'src' ? new THREE.OctahedronGeometry(size) : kind === 'person' ? new THREE.DodecahedronGeometry(size) : new THREE.SphereGeometry(size, X.lo ? 12 : 26, X.lo ? 10 : 18);
    const mat = nodeMat(col), m = new THREE.Mesh(geo, mat), n = {id: d.id, kind, d, red, size, m, mat, nb: new Set(), i, p: null,
      pres: old ? old.pres : 0, born: old ? 0 : now + (kind === 'src' ? 0 : .5 + i * .03), dim: 1, fall: 0, leave: 0, base: 1, R: old ? old.R : (red ? 1 : 0), ring: null, halo: null};
    m.userData.n = n; N.push(n); byId.set(d.id, n);
  });
  const E = []; g.edges.forEach(e => { const a = byId.get(e.a), b = byId.get(e.b); if (!a || !b) return; a.nb.add(b); b.nb.add(a); E.push({a, b, kind: e.conflict ? 'conflict' : e.kind, o: 0}); });
  layout(N, E); N.forEach(n => pos.set(n.id, n.p.clone()));
  N.forEach(n => {
    n.m.position.copy(n.p); X.grp.add(n.m);
    const hot = !n.red && ((n.d.state === 'CONFLICT') || (n.kind === 'person' && n.d.solo >= 2));
    if (hot) { const s = new THREE.Sprite(new THREE.SpriteMaterial({map: X.HT, color: n.kind === 'person' ? COL.CONFLICT : COL.CONFLICT, transparent: true, opacity: .6, blending: THREE.AdditiveBlending, depthWrite: false})); s.scale.setScalar(n.size * 6.5); n.m.add(s); n.halo = s; }
    if (n.kind === 'claim') { const s = new THREE.Sprite(new THREE.SpriteMaterial({map: X.RT, color: 0x3ddc97, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false})); s.scale.setScalar(n.size * 3.6); n.m.add(s); n.ring = s; }
    if ((n.kind === 'src' || n.kind === 'person') && !n.red) { const d = document.createElement('div'); d.className = 'lbl ' + (n.kind === 'src' ? 'src' : 'per'); d.textContent = n.kind === 'src' ? n.d.name.split('/').pop() : n.d.name[0].toUpperCase() + n.d.name.slice(1); const o = new CSS2DObject(d); o.position.set(0, n.size + .55, 0); n.m.add(o); n.lab = d; }
  });
  // edges: ONE draw call. Per-vertex colour + alpha, updated each frame
  const ev = E.length * 2, ep = new Float32Array(ev * 3), ec = new Float32Array(ev * 3), ea = new Float32Array(ev);
  E.forEach((e, k) => { const c = EDGE[e.kind] || EDGE.cites; for (let j = 0; j < 2; j++) ec.set(c, (k * 2 + j) * 3); });
  const lg = new THREE.BufferGeometry(); lg.setAttribute('position', new THREE.BufferAttribute(ep, 3)); lg.setAttribute('color', new THREE.BufferAttribute(ec, 3)); lg.setAttribute('aA', new THREE.BufferAttribute(ea, 1));
  X.lines = new THREE.LineSegments(lg, new THREE.ShaderMaterial({transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, vertexShader: 'attribute vec3 color;attribute float aA;varying vec3 vC;varying float vA;void main(){vC=color;vA=aA;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}', fragmentShader: 'varying vec3 vC;varying float vA;void main(){gl_FragColor=vec4(vC*vA,vA);\n#include <colorspace_fragment>\n}'}));
  X.lines.frustumCulled = false; X.grp.add(X.lines); X.E = E;
  const K = E.length && !REDUCED ? (X.lo ? 50 : 140) : 0; X.K = K; X.fe = Array.from({length: K}, (_, i) => ({e: E[i % E.length], t: Math.random()}));
  X.fp = new Float32Array(K * 3); const fg = new THREE.BufferGeometry(); fg.setAttribute('position', new THREE.BufferAttribute(X.fp, 3)); X.fg = fg;
  X.flow = new THREE.Points(fg, new THREE.PointsMaterial({size: .16, map: X.HT, color: 0xffe9c0, transparent: true, opacity: .9, blending: THREE.AdditiveBlending, depthWrite: false})); X.flow.frustumCulled = false; X.grp.add(X.flow);
  scene.N = N; scene.byId = byId; scene.E = E; scene.dates = g.dates || [];
  const keep = scene.sel && byId.get(scene.sel.id); scene.sel = keep && !keep.red ? keep : null;
  X.core.visible = !N.some(n => n.kind === 'claim') || scene.mode !== 'map';
};

/* ---------- modes, selection, effects ---------- */
scene.setMode = function (m) {
  scene.mode = m; if (!scene.ready) return;
  const tint = {landing: [0, .5, .45], connect: [.1, .3, .5], reconstruct: [.5, .12, .08], work: [.02, .22, .3], map: [.05, .25, .4]}[m] || [0, .4, .4];
  X.tintGoal = new THREE.Vector3(...tint);
  X.goalDist = {landing: 25, connect: 22, reconstruct: 20, work: 31, map: 24}[m]; X.opGoal = {landing: 1, connect: 1, reconstruct: 1, work: .5, map: 1}[m];
  X.ctl.autoRotate = !scene.docked; X.ctl.autoRotateSpeed = m === 'work' ? .25 : .5;
  X.core.visible = m !== 'map' || !scene.N.some(n => n.kind === 'claim');
  X.cv.style.opacity = X.opGoal;
};
scene.dock = function (el, labelsEl) {
  if (!scene.ready) return; scene.docked = true; X.cv.classList.add('docked'); el.appendChild(X.cv); el.appendChild(labelsEl); labelsEl.style.position = 'absolute';
  X.cv.style.opacity = 1; X.cv.tabIndex = 0; X.cv.removeAttribute('aria-hidden'); X.cv.setAttribute('aria-label', '3D evidence map. Arrow keys rotate, plus and minus zoom, N and P step through nodes.');
  X.ctl.enabled = true; X.ctl.autoRotate = true; X.ctl.autoRotateSpeed = .35; X.cam.position.setLength(40); X.r.setPixelRatio(X.lo ? 1 : Math.min(devicePixelRatio, 1.75)); fit();
};
scene.undock = function () {
  if (!scene.ready || !scene.docked) return; scene.docked = false; X.cv.classList.remove('docked'); document.body.prepend(X.cv); document.body.insertBefore(X.labelsEl, X.cv.nextSibling); X.labelsEl.style.position = '';
  X.cv.tabIndex = -1; X.cv.setAttribute('aria-hidden', 'true'); X.ctl.enabled = false; X.r.setPixelRatio(1); scene.sel = null; scene.hov = null; X.tipObj.visible = false; fit();
};
scene.select = function (id) {
  const n = id ? scene.byId.get(id) : null; scene.sel = n; scene.handlers.select && scene.handlers.select(n && !n.red ? n.d : n ? {restricted: true, id: n.id} : null);
  if (n) { X.goalTarget = n.p.clone().multiplyScalar(.6); } else X.goalTarget = new THREE.Vector3();
};
scene.focus = function (id) { const n = scene.byId.get(id); if (n) { scene.sel = n; X.goalTarget = n.p.clone().multiplyScalar(.6); scene.pulse(id, 0x5eead4); } };
scene.highlight = function (id) { scene.hov = id ? scene.byId.get(id) || null : null; };
scene.simulate = function (info) { scene.sim = info ? {person: info.person, orphaned: new Set(info.orphaned), ripple: new Set(info.ripple || [])} : null; if (info) { const p = scene.byId.get('P:' + info.person); p && scene.pulse(p.id, 0xff5a4d, 7); } };
scene.setFilter = function (f) { Object.assign(scene.filter, f); };
scene.pulse = function (id, color, big) {
  if (!scene.ready || REDUCED) return; const n = scene.byId.get(id); if (!n) return;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({map: X.RT, color, transparent: true, opacity: .9, blending: THREE.AdditiveBlending, depthWrite: false})); s.position.copy(n.p); X.grp.add(s); pulses.push({s, t: 0, big: big || 3.5, n0: n.size});
};
scene.reveal = function () { const now = performance.now() / 1000; scene.N.forEach((n, i) => { n.pres = 0; n.born = now + (n.kind === 'src' ? 0 : .6 + i * .05); }); X.ctl.autoRotateSpeed = 1.6; setTimeout(() => X.ctl && (X.ctl.autoRotateSpeed = .5), 3500); };
scene.neighbours = id => { const n = scene.byId.get(id); return n ? [...n.nb].filter(o => !o.red).map(o => o.d) : []; };

function pick(e) { const b = X.cv.getBoundingClientRect(); X.mv.set((e.clientX - b.left) / b.width * 2 - 1, -((e.clientY - b.top) / b.height) * 2 + 1); X.ray.setFromCamera(X.mv, X.cam); const h = X.ray.intersectObjects(scene.N.filter(n => n.m.visible).map(n => n.m), false)[0]; return h && h.object.userData.n; }
function hover(n) { scene.hov = n; if (!n) { X.tipObj.visible = false; document.body.style.cursor = ''; } }
function onMove(e) {
  if (!scene.docked || e.buttons) return; const n = pick(e) || null; scene.hov = n; X.cv.style.cursor = n ? 'pointer' : 'grab';
  const t = document.getElementById('tip');
  if (n && t) { t.textContent = n.red ? 'RESTRICTED: needs higher clearance' : n.kind === 'claim' ? `${n.id} · ${n.d.state} · ${n.d.label}` : n.kind === 'src' ? n.d.name : n.d.name; t.style.left = Math.min(innerWidth - 300, e.clientX + 14) + 'px'; t.style.top = e.clientY + 14 + 'px'; t.style.opacity = 1; } else if (t) t.style.opacity = 0;
}
function onKey(e) {
  const k = e.key, c = X.ctl; if (k === '+' || k === '=') { X.cam.position.multiplyScalar(.9); } else if (k === '-') { X.cam.position.multiplyScalar(1.1); }
  else if (k === 'ArrowLeft' || k === 'ArrowRight') { X.cam.position.applyAxisAngle(new THREE.Vector3(0, 1, 0), k === 'ArrowLeft' ? .12 : -.12); } else if (k === 'ArrowUp' || k === 'ArrowDown') { X.cam.position.y += k === 'ArrowUp' ? 1 : -1; }
  else if (k === 'n' || k === 'p') { const v = scene.N.filter(o => !o.red && o.m.visible); if (v.length) scene.select(v[(v.indexOf(scene.sel) + (k === 'n' ? 1 : -1) + v.length) % v.length].id); } else if (k === 'Escape') scene.select(null); else return;
  e.preventDefault(); c.update();
}

/* ---------- frame ---------- */
function visibleNode(n) {
  if (n.kind !== 'claim' || n.red) return true; const f = scene.filter;
  if (f.type !== 'all' && n.d.type !== f.type) return false; return !(f.cut && n.d.date && n.d.date > f.cut);
}
function loop() {
  requestAnimationFrame(loop); if (!scene.ready || X.lost || document.hidden) return;
  const now = performance.now(), dt = Math.min(.05, (now - last) / 1000), k = 1 - Math.exp(-dt * 8); last = now; if (!REDUCED) T += dt;
  if (!probed && now > 3000) { probe.push(dt); if (probe.length > 70) { probe.sort((a, b) => a - b); scene.stats.fps = Math.round(1 / probe[35]); if (probe[35] > .026 && !X.lo) { X.lo = true; X.comp = null; X.bloom = null; X.r.setPixelRatio(1); X.dust.visible = false; } probed = true; } }
  X.U.uT.value = T; X.U.uTint.value.lerp(X.tintGoal || X.U.uTint.value, k * .3);
  const t = now / 1000, docked = scene.docked;
  if (!docked) { X.ctl.enabled = false; const d = X.cam.position.length(), g = X.goalDist || 25; X.cam.position.multiplyScalar(1 + (g - d) / d * k * .4); X.cam.position.y += (-(X.my || 0) * 6 + 3 - X.cam.position.y) * k * .15; }
  if (X.goalTarget) { X.ctl.target.lerp(X.goalTarget, k * .5); }
  X.ctl.update();
  const core = X.core, cs = 1 + .06 * Math.sin(T * 2); core.rotation.y += dt * .3; core.rotation.x += dt * .12; core.scale.setScalar(cs * (scene.N.some(n => n.kind === 'claim') ? .6 : 1));
  const foc = scene.sel || scene.hov, sim = scene.sim, tod = new Date().getTime();
  for (const n of scene.N) {
    const on = t >= n.born && visibleNode(n); n.pres += ((on ? 1 : 0) - n.pres) * (1 - Math.exp(-dt * 5));
    const isP = n.kind === 'person', lv = isP && sim && n.d.name === sim.person ? 1 : 0; n.leave += (lv - n.leave) * k;
    const fl = n.kind === 'claim' && sim && sim.orphaned.has(n.id) ? 1 : 0; n.fall += (fl - n.fall) * k;
    const rp = n.kind === 'claim' && sim && sim.ripple.has(n.id) ? 1 : 0;
    n.dim += ((!foc || n === foc || foc.nb.has(n) ? 1 : .25) - n.dim) * k;
    const st = n.kind === 'claim' && !n.red ? n.d.status : null, bt = n.kind !== 'claim' || n.red ? 1 : st === 'rejected' ? .18 : st === 'approved' ? 1 : .62; n.base += (bt - n.base) * k;
    n.R += ((n.red ? 1 : 0) - n.R) * k * .7;
    const u = n.mat.uniforms, pr = n.pres * (1 - n.leave);
    u.uD.value = n.dim; u.uF.value = n.fall; u.uR.value = n.R; u.uT.value = T; u.uG.value = (n === scene.sel ? 1 : 0) + rp * .7 + (n === scene.hov ? .5 : 0); u.uO.value = pr * (.28 + .72 * n.dim) * n.base;
    const sh = n.fall > .05 && !REDUCED ? Math.sin(T * 40 + n.i) * .05 * n.fall : 0; n.m.position.set(n.p.x + sh, n.p.y + (n.kind === 'src' || REDUCED ? 0 : Math.sin(T * .8 + n.i) * .12), n.p.z);
    n.m.visible = pr > .02; n.m.scale.setScalar(Math.max(.001, pr) * (1 - .55 * n.fall) * (n === scene.sel ? 1.5 : n === scene.hov ? 1.25 : 1) * (n.halo && !REDUCED ? 1 + .1 * Math.sin(T * 5) : 1));
    if (n.kind === 'src') n.m.rotation.y += dt * .6;
    if (n.halo) n.halo.material.opacity = .6 * pr * n.dim; if (n.ring) n.ring.material.opacity = (st === 'approved' ? .8 : 0) * pr * n.dim;
    if (n.lab) n.lab.style.opacity = (docked || scene.mode === 'connect' || scene.mode === 'reconstruct' ? 1 : 0) * pr * (.35 + .65 * n.dim);
  }
  // edges
  const L = X.lines; if (L) { const P = L.geometry.attributes.position, A = L.geometry.attributes.aA;
    X.E.forEach((e, i) => { const a = e.a, b = e.b, lk = (a.leave > .5 || b.leave > .5) ? 0 : 1, goal = Math.min(a.pres, b.pres) * lk * (!foc || a === foc || b === foc ? .55 : .06) * (e.kind === 'conflict' ? 1.6 : 1); e.o += (goal - e.o) * k;
      P.setXYZ(i * 2, a.m.position.x, a.m.position.y, a.m.position.z); P.setXYZ(i * 2 + 1, b.m.position.x, b.m.position.y, b.m.position.z); A.setX(i * 2, e.o); A.setX(i * 2 + 1, e.o); });
    P.needsUpdate = A.needsUpdate = true; }
  if (X.K) { for (let q = 0; q < X.K; q++) { const f = X.fe[q], a = f.e.a.m.position, b = f.e.b.m.position; f.t = (f.t + dt * (f.e.kind === 'conflict' ? .35 : .16)) % 1; const on = f.e.o > .2; X.fp[q * 3] = on ? a.x + (b.x - a.x) * f.t : 999; X.fp[q * 3 + 1] = on ? a.y + (b.y - a.y) * f.t : 999; X.fp[q * 3 + 2] = on ? a.z + (b.z - a.z) * f.t : 999; } X.fg.attributes.position.needsUpdate = true; }
  for (let i = pulses.length - 1; i >= 0; i--) { const p = pulses[i]; p.t += dt; const u = p.t / 1.2; if (u >= 1) { X.grp.remove(p.s); p.s.material.dispose(); pulses.splice(i, 1); continue; } p.s.scale.setScalar(p.n0 * 3 + u * p.big * 3); p.s.material.opacity = .9 * (1 - u); }
  const hn = foc && foc.kind === 'claim' && !foc.red && docked ? foc : null; if (hn) { X.tip.textContent = hn.id; X.tipObj.position.copy(hn.m.position); X.tipObj.position.y += hn.size + .5; X.tipObj.visible = true; } else X.tipObj.visible = false;
  X.dust.rotation.y += dt * .01;
  if (X.comp) X.comp.render(); else X.r.render(X.sc, X.cam); X.lab.render(X.sc, X.cam);
}
