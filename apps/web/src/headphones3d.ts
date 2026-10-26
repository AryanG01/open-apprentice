import * as THREE from "three";

// Stylised 3D interpretation of the flat h7-headphones.svg illustration (see
// docs/evaluation/headphones3d_img2threejs.md). Single front view: depths, cross-sections and
// rear faces are invented. Units: 1 = 364 px of the 1024 px reference, so the model is ~2 tall.
const BAND_COLOR = "#fdfbff";
const CUP_TOP = "#ffd23f";
const CUP_BOTTOM = "#f29e1d";
const PAD_TOP = "#c9a23f";
const PAD_BOTTOM = "#b9802a";
const DOT_COLOR = "#ff7a59";

const BAND_OUTER = 0.93;
const BAND_INNER = 0.775;
const BAND_CENTER_Y = 0.071;
// Legs run into the cups so no gap shows at the rounded cup corners.
const BAND_LEG_BOTTOM = -0.2;
const BAND_DEPTH = 0.2;
const BAND_BEVEL = 0.02;

const CUP_X = 0.81;
const CUP_Y = -0.547;
const CUP_W = 0.52;
const CUP_H = 0.907;
const CUP_R = 0.22;
const CUP_DEPTH = 0.34;
const CUP_BEVEL = 0.035;

const PAD_W = 0.3;
const PAD_H = 0.6;
const PAD_R = 0.12;
const PAD_DEPTH = 0.05;

function roundedRect(w: number, h: number, r: number): THREE.Shape {
  const x = -w / 2;
  const y = -h / 2;
  const s = new THREE.Shape();
  s.moveTo(x + r, y);
  s.lineTo(x + w - r, y);
  s.absarc(x + w - r, y + r, r, -Math.PI / 2, 0, false);
  s.lineTo(x + w, y + h - r);
  s.absarc(x + w - r, y + h - r, r, 0, Math.PI / 2, false);
  s.lineTo(x + r, y + h);
  s.absarc(x + r, y + h - r, r, Math.PI / 2, Math.PI, false);
  s.lineTo(x, y + r);
  s.absarc(x + r, y + r, r, Math.PI, Math.PI * 1.5, false);
  return s;
}

function extrude(shape: THREE.Shape, depth: number, bevel: number): THREE.ExtrudeGeometry {
  const g = new THREE.ExtrudeGeometry(shape, {
    depth,
    bevelEnabled: bevel > 0,
    bevelThickness: bevel,
    bevelSize: bevel,
    bevelSegments: 3,
    curveSegments: 32,
  });
  g.translate(0, 0, -depth / 2);
  return g;
}

/** Vertical two-stop vertex-colour gradient between the geometry's y extents. */
function paintGradient(g: THREE.BufferGeometry, top: string, bottom: string): void {
  g.computeBoundingBox();
  const box = g.boundingBox;
  const pos = g.getAttribute("position");
  if (!box) return;
  const a = new THREE.Color(top);
  const b = new THREE.Color(bottom);
  const c = new THREE.Color();
  const colors = new Float32Array(pos.count * 3);
  for (let i = 0; i < pos.count; i++) {
    c.copy(a).lerp(b, (box.max.y - pos.getY(i)) / (box.max.y - box.min.y));
    colors.set([c.r, c.g, c.b], i * 3);
  }
  g.setAttribute("color", new THREE.BufferAttribute(colors, 3));
}

function bandGeometry(): THREE.ExtrudeGeometry {
  // Bevel grows the profile outward by BAND_BEVEL, so shrink it to keep the reference proportions.
  const ro = BAND_OUTER - BAND_BEVEL;
  const ri = BAND_INNER + BAND_BEVEL;
  const cy = BAND_CENTER_Y;
  const leg = BAND_LEG_BOTTOM + BAND_BEVEL;
  const s = new THREE.Shape();
  s.moveTo(ro, leg);
  s.lineTo(ro, cy);
  s.absarc(0, cy, ro, 0, Math.PI, false);
  s.lineTo(-ro, leg);
  s.lineTo(-ri, leg);
  s.lineTo(-ri, cy);
  s.absarc(0, cy, ri, Math.PI, 0, true);
  s.lineTo(ri, leg);
  s.closePath();
  return extrude(s, BAND_DEPTH - 2 * BAND_BEVEL, BAND_BEVEL);
}

export function createHeadphones(): THREE.Group {
  const group = new THREE.Group();
  group.name = "root";

  const bandMat = new THREE.MeshStandardMaterial({ color: BAND_COLOR, roughness: 0.6, metalness: 0 });
  const cupMat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.45, metalness: 0 });
  const padMat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.8, metalness: 0 });
  const dotMat = new THREE.MeshStandardMaterial({ color: DOT_COLOR, roughness: 0.5, metalness: 0 });

  const band = new THREE.Mesh(bandGeometry(), bandMat);
  band.name = "headband";
  group.add(band);

  for (const side of [-1, 1]) {
    const cupGeo = extrude(roundedRect(CUP_W - 2 * CUP_BEVEL, CUP_H - 2 * CUP_BEVEL, CUP_R - CUP_BEVEL), CUP_DEPTH - 2 * CUP_BEVEL, CUP_BEVEL);
    paintGradient(cupGeo, CUP_TOP, CUP_BOTTOM);
    const cup = new THREE.Mesh(cupGeo, cupMat);
    cup.name = side < 0 ? "ear-cup-neg" : "ear-cup-pos";
    cup.position.set(side * CUP_X, CUP_Y, 0);
    group.add(cup);

    // Inset cushion panel proud of both broad faces (rear one is invented).
    for (const face of [-1, 1]) {
      const padGeo = extrude(roundedRect(PAD_W, PAD_H, PAD_R), PAD_DEPTH, 0);
      paintGradient(padGeo, PAD_TOP, PAD_BOTTOM);
      const pad = new THREE.Mesh(padGeo, padMat);
      pad.name = `cushion-${side < 0 ? "neg" : "pos"}${face < 0 ? "-back" : ""}`;
      pad.position.set(0, 0, face * (CUP_DEPTH / 2 + PAD_DEPTH / 2 - 0.005));
      cup.add(pad);
    }
  }

  const dot = new THREE.Mesh(new THREE.SphereGeometry(0.06, 24, 16), dotMat);
  dot.name = "accent-dot";
  dot.position.set(0, -0.093, 0);
  group.add(dot);

  return group;
}

export function disposeHeadphones(group: THREE.Group): void {
  const materials = new Set<THREE.Material>();
  group.traverse((obj) => {
    if (!(obj instanceof THREE.Mesh)) return;
    obj.geometry.dispose();
    if (Array.isArray(obj.material)) obj.material.forEach((m) => materials.add(m));
    else materials.add(obj.material);
  });
  materials.forEach((m) => m.dispose());
}
