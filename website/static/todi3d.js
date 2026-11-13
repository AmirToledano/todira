/* 2026-11-13 (owner: "I'd rather it really be Todi in 3D, and I don't want to pay for it"): Todi as a real 3D model,
   built here from simple shapes with three.js (no paid service, no model file): a chocolate-and-tan dapple dachshund
   with long ears, tan eyebrows, a teal collar with its tag and a small gold crown. It takes the drawn Todi's place in
   the same walker, so todi.js keeps moving it along the street and its classes keep driving the pose: .is-walking
   (legs, bob, ears), .is-sniffing (nose to the ground), .is-looking (head up). The flip to face the other way is the
   same CSS flip the drawing uses. Loaded by home.js only after the page is up, only with WebGL and only without
   reduced motion; until then, or if anything here fails, the drawing stays. */
import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.min.js";

const COAT = 0x6a4430, COAT_DARK = 0x45291b, TAN = 0xcf9152, SPOT = 0xa98a72, NOSE = 0x1b1411;
const TEAL = 0x0b7a73, GOLD = 0xe2b14c, RUBY = 0xb3262e;

function mat(color, rough = 0.78, metal = 0) {
  return new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: metal });
}

function mesh(geo, material, x = 0, y = 0, z = 0) {
  const m = new THREE.Mesh(geo, material);
  m.position.set(x, y, z);
  return m;
}

/* The dog faces -X (left on screen, like the drawing); the ground is y = 0. */
export function buildTodi() {
  const coat = mat(COAT), dark = mat(COAT_DARK), tan = mat(TAN), spot = mat(SPOT, 0.85);
  const nose = mat(NOSE, 0.35), eye = mat(NOSE, 0.2), teal = mat(TEAL, 0.55), gold = mat(GOLD, 0.32, 0.65);
  const dog = new THREE.Group();
  const body = new THREE.Group();
  dog.add(body);

  // the long body: a capsule along X, a deep chest in front and a round rump behind
  const torso = mesh(new THREE.CapsuleGeometry(0.4, 1.45, 8, 20), coat, 0.15, 0.78, 0);
  torso.rotation.z = Math.PI / 2;
  torso.scale.set(1, 1, 0.92);
  body.add(torso);
  const chest = mesh(new THREE.SphereGeometry(0.46, 24, 16), coat, -0.52, 0.7, 0);
  chest.scale.set(1, 1.06, 0.9);
  body.add(chest);
  body.add(mesh(new THREE.SphereGeometry(0.42, 24, 16), coat, 0.82, 0.8, 0));
  const bib = mesh(new THREE.SphereGeometry(0.3, 18, 12), tan, -0.78, 0.6, 0);  // the tan chest patch
  bib.scale.set(0.6, 1, 0.75);
  body.add(bib);
  // dapple spots on the back and sides
  [[-0.1, 0.38, 0.12, 0.13], [0.35, 0.34, -0.2, 0.1], [0.62, 0.3, 0.26, 0.12], [0.1, 0.22, 0.36, 0.09],
   [0.5, 0.18, -0.36, 0.08], [-0.35, 0.3, -0.25, 0.09]].forEach(([x, dy, z, r]) => {
    const n = new THREE.Vector3(0, dy, z).normalize();
    const s = mesh(new THREE.SphereGeometry(r, 14, 8), spot, x, 0.78 + n.y * 0.385, n.z * 0.355);
    s.scale.set(1.25, 1, 0.12);
    s.lookAt(x, 0.78 + n.y * 2, n.z * 2);
    body.add(s);
  });

  // neck, collar and tag
  const neck = mesh(new THREE.CapsuleGeometry(0.23, 0.42, 6, 14), coat, -0.88, 1.04, 0);
  neck.rotation.z = -0.7;
  body.add(neck);
  const collar = mesh(new THREE.TorusGeometry(0.25, 0.065, 10, 28), teal, -0.86, 1.02, 0);
  collar.rotation.set(0, Math.PI / 2, -0.7);
  body.add(collar);
  const tag = mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.03, 18), gold, -1.08, 0.8, 0.06);
  tag.rotation.set(Math.PI / 2, 0, 0.3);
  body.add(tag);

  // the head: skull, a long tan-tipped snout, nose, eyes, tan eyebrows, long ears, and the crown
  const head = new THREE.Group();
  head.position.set(-1.06, 1.36, 0);
  body.add(head);
  const skull = mesh(new THREE.SphereGeometry(0.32, 24, 18), coat, 0, 0.04, 0);
  skull.scale.set(1.12, 0.96, 0.9);
  head.add(skull);
  const snout = mesh(new THREE.CapsuleGeometry(0.15, 0.44, 8, 16), coat, -0.42, -0.09, 0);
  snout.rotation.z = Math.PI / 2 + 0.1;
  snout.scale.set(0.92, 1, 0.95);
  head.add(snout);
  const muzzle = mesh(new THREE.SphereGeometry(0.14, 16, 12), tan, -0.56, -0.16, 0);
  muzzle.scale.set(1.4, 0.6, 0.95);
  head.add(muzzle);
  head.add(mesh(new THREE.SphereGeometry(0.08, 14, 10), nose, -0.74, -0.07, 0));
  [-1, 1].forEach((side) => {
    head.add(mesh(new THREE.SphereGeometry(0.068, 14, 10), eye, -0.24, 0.1, side * 0.2));
    head.add(mesh(new THREE.SphereGeometry(0.022, 8, 6), mat(0xffffff, 0.2), -0.29, 0.135, side * 0.24));
    const brow = mesh(new THREE.SphereGeometry(0.04, 10, 8), tan, -0.2, 0.2, side * 0.19);
    brow.scale.set(1.3, 0.6, 1);
    head.add(brow);
    const earPivot = new THREE.Group();
    earPivot.position.set(0.06, 0.16, side * 0.27);
    const ear = mesh(new THREE.SphereGeometry(1, 18, 14), dark, 0.03, -0.3, side * 0.04);
    ear.scale.set(0.19, 0.34, 0.06);
    earPivot.add(ear);
    earPivot.rotation.x = side * 0.12;
    head.add(earPivot);
    head.userData[side < 0 ? "earL" : "earR"] = earPivot;
  });
  const crown = new THREE.Group();
  crown.position.set(0.03, 0.37, 0);
  crown.rotation.z = 0.12;
  crown.add(mesh(new THREE.CylinderGeometry(0.2, 0.17, 0.1, 22, 1, true), gold));
  for (let i = 0; i < 6; i++) {
    const a = (i / 6) * Math.PI * 2;
    crown.add(mesh(new THREE.ConeGeometry(0.045, 0.14, 8), gold, Math.cos(a) * 0.19, 0.11, Math.sin(a) * 0.19));
    if (i % 2 === 0) { crown.add(mesh(new THREE.SphereGeometry(0.022, 8, 6), mat(RUBY, 0.3), Math.cos(a) * 0.195, 0.01, Math.sin(a) * 0.195)); }
  }
  head.add(crown);

  // four short legs, each turning at the shoulder or hip, with tan paws
  const legs = [];
  [[-0.6, -0.19], [-0.6, 0.19], [0.88, -0.19], [0.88, 0.19]].forEach(([x, z]) => {
    const leg = new THREE.Group();
    leg.position.set(x, 0.62, z);
    leg.add(mesh(new THREE.CapsuleGeometry(0.125, 0.3, 6, 12), coat, 0, -0.24, 0));
    const paw = mesh(new THREE.SphereGeometry(0.125, 14, 10), tan, -0.035, -0.5, 0);
    paw.scale.set(1.15, 0.72, 1);
    leg.add(paw);
    body.add(leg);
    legs.push(leg);
  });

  // the tail, thick at the base and thin at the tip
  const tail = new THREE.Group();
  tail.position.set(1.2, 0.9, 0);
  const tailMesh = mesh(new THREE.CylinderGeometry(0.03, 0.075, 0.66, 10), coat, 0, 0.3, 0);
  tail.add(tailMesh);
  tail.rotation.z = -0.85;
  body.add(tail);

  dog.userData = { body, head, legs, tail };
  return dog;
}

function shadowTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, "rgba(0,0,0,.55)");
  grad.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
}

/* Puts a 3D Todi in place of the drawing inside `walker` and keeps it posed from the classes todi.js sets.
   Returns the new element, or throws (the drawing then simply stays). */
export function mountTodi3D(walker, stage) {
  const svg = walker.querySelector("svg.todi-dog");
  const canvas = document.createElement("canvas");
  canvas.className = "todi-dog todi-3d";
  canvas.setAttribute("aria-hidden", "true");
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xfff6e8, 0x7a5a42, 2.3));
  const sun = new THREE.DirectionalLight(0xffffff, 2.1);
  sun.position.set(-2, 4, 3);
  scene.add(sun);
  const rim = new THREE.DirectionalLight(0xffe2b0, 0.9);
  rim.position.set(3, 2, -2);
  scene.add(rim);

  const dog = buildTodi();
  dog.rotation.y = -0.45;  // a little toward the viewer, so it reads as a body and not a cut-out
  scene.add(dog);
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(3.4, 1.3), new THREE.MeshBasicMaterial({ map: shadowTexture(), transparent: true, depthWrite: false }));
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.set(0.1, 0.01, 0);
  scene.add(shadow);

  const camera = new THREE.PerspectiveCamera(26, 1.6, 0.1, 50);
  camera.position.set(-0.4, 1.7, 7.4);
  camera.lookAt(0.05, 0.82, 0);

  const size = () => {
    const w = walker.clientWidth || 120, h = Math.round(w / 1.6);
    renderer.setSize(w, h, false);
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
  };
  size();
  if ("ResizeObserver" in window) { new ResizeObserver(size).observe(walker); }

  // take the drawing's place, with its current pose and facing
  if (svg) {
    canvas.classList.add(...Array.from(svg.classList).filter((c) => c.startsWith("is-")));
    canvas.style.transform = svg.style.transform;
    svg.style.display = "none";
  }
  walker.appendChild(canvas);
  walker.classList.add("is-3d");

  const { body, head, legs, tail } = dog.userData;
  let phase = 0, walkMix = 0, headTilt = 0, last = performance.now();
  const ease = (from, to, k) => from + (to - from) * k;
  const frame = (now) => {
    requestAnimationFrame(frame);
    if (document.hidden || (stage && stage.classList.contains("td-paused"))) { last = now; return; }
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    const walking = canvas.classList.contains("is-walking");
    const sniffing = canvas.classList.contains("is-sniffing");
    const looking = canvas.classList.contains("is-looking");
    walkMix = ease(walkMix, walking ? 1 : 0, Math.min(1, dt * 8));
    phase += dt * 10.5 * (0.25 + walkMix);
    const swing = Math.sin(phase) * 0.55 * walkMix;
    legs[0].rotation.z = swing; legs[3].rotation.z = swing;     // front-left with back-right
    legs[1].rotation.z = -swing; legs[2].rotation.z = -swing;   // front-right with back-left
    body.position.y = Math.abs(Math.sin(phase)) * 0.045 * walkMix;
    const t = now / 1000;
    let want = Math.sin(phase) * 0.04 * walkMix;
    if (sniffing) { want = 0.5 + Math.sin(t * 18) * 0.05; }
    else if (looking) { want = -0.22 + Math.sin(t * 2) * 0.04; }
    headTilt = ease(headTilt, want, Math.min(1, dt * 7));
    head.rotation.z = headTilt;
    const earSwing = Math.sin(phase + 0.6) * 0.18 * walkMix + Math.sin(t * 1.3) * 0.03;
    head.userData.earL.rotation.z = earSwing;
    head.userData.earR.rotation.z = earSwing;
    tail.rotation.x = Math.sin(t * (walking ? 15 : 9)) * 0.55;
    shadow.scale.set(1 - body.position.y * 1.5, 1, 1);
    renderer.render(scene, camera);
  };
  requestAnimationFrame(frame);
  return canvas;
}
