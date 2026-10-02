import * as THREE from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";

import { stepBody } from "./hero-physics.js";

const PALETTE = {
  pink: 0xf540a0,
  yellow: 0xffcd18,
  cyan: 0x0bcce0,
  blue: 0x1559ef,
  violet: 0x6032d7,
  white: 0xf4f4f1,
  navy: 0x132e9c,
};

function plastic(color) {
  return new THREE.MeshPhysicalMaterial({
    color,
    metalness: 0.08,
    roughness: 0.22,
    clearcoat: 0.75,
    clearcoatRoughness: 0.16,
  });
}

function brick(studsX, studsZ, color, withUnderside = false) {
  const group = new THREE.Group();
  const pitch = 0.72;
  const width = studsX * pitch;
  const depth = studsZ * pitch;
  const material = plastic(color);
  if (withUnderside) {
    const wall = 0.12;
    const slab = new THREE.Mesh(
      new RoundedBoxGeometry(width, wall, depth, 3, 0.06), material,
    );
    slab.position.y = 0.27;
    group.add(slab);
    for (const side of [-1, 1]) {
      const sideWall = new THREE.Mesh(
        new RoundedBoxGeometry(wall, 0.53, depth, 3, 0.045), material,
      );
      sideWall.position.set(side * (width - wall) / 2, -0.025, 0);
      group.add(sideWall);
      const endWall = new THREE.Mesh(
        new RoundedBoxGeometry(width - wall * 2, 0.53, wall, 3, 0.045), material,
      );
      endWall.position.set(0, -0.025, side * (depth - wall) / 2);
      group.add(endWall);
    }
  } else {
    group.add(new THREE.Mesh(new RoundedBoxGeometry(width, 0.62, depth, 4, 0.075), material));
  }
  const studGeometry = new THREE.CylinderGeometry(0.264, 0.278, 0.17, 40);
  for (let x = 0; x < studsX; x += 1) {
    for (let z = 0; z < studsZ; z += 1) {
      const stud = new THREE.Mesh(studGeometry, material);
      stud.position.set((x - (studsX - 1) / 2) * pitch, 0.39, (z - (studsZ - 1) / 2) * pitch);
      group.add(stud);
    }
  }
  return group;
}

function modularCube() {
  const group = new THREE.Group();
  const shell = new THREE.Mesh(new RoundedBoxGeometry(2.43, 2.43, 2.43, 4, 0.13), plastic(PALETTE.navy));
  group.add(shell);
  const colors = [PALETTE.blue, PALETTE.blue, PALETTE.yellow,
    PALETTE.blue, PALETTE.white, PALETTE.blue,
    PALETTE.blue, PALETTE.blue, PALETTE.white];
  const tile = new RoundedBoxGeometry(0.69, 0.69, 0.105, 3, 0.055);
  const materials = new Map();
  const materialFor = (color) => {
    if (!materials.has(color)) materials.set(color, plastic(color));
    return materials.get(color);
  };
  for (let row = 0; row < 3; row += 1) {
    for (let column = 0; column < 3; column += 1) {
      const x = (column - 1) * 0.77;
      const y = (1 - row) * 0.77;
      const index = row * 3 + column;
      const front = new THREE.Mesh(tile, materialFor(colors[index]));
      front.position.set(x, y, 1.23);
      group.add(front);
      const top = new THREE.Mesh(tile, materialFor(index % 4 === 0 ? PALETTE.white : PALETTE.blue));
      top.rotation.x = -Math.PI / 2;
      top.position.set(x, 1.23, y);
      group.add(top);
      const side = new THREE.Mesh(tile, materialFor(index === 1 ? PALETTE.yellow : PALETTE.blue));
      side.rotation.y = Math.PI / 2;
      side.position.set(1.23, y, x);
      group.add(side);
    }
  }
  return group;
}

const PIECES = [
  { shape: () => brick(1, 2, PALETTE.pink), x: 0.105, y: 0.15, scale: 2.8, radius: 235, mass: 1, rotation: [0.55, 0.48, -0.35] },
  { shape: modularCube, x: 0.87, y: 0.2, scale: 1.8, radius: 300, mass: 2.2, rotation: [0.42, -0.62, 0.22] },
  { shape: () => brick(1, 2, PALETTE.cyan), x: 0.08, y: 0.48, scale: 1.4, radius: 225, mass: 0.9, rotation: [0.75, -0.35, -0.8] },
  { shape: () => brick(2, 2, PALETTE.yellow), x: 0.16, y: 0.83, scale: 3.1, radius: 320, mass: 2.5, rotation: [0.45, -0.3, -0.34] },
  { shape: () => brick(1, 1, PALETTE.white), x: 0.86, y: 0.63, scale: 1.4, radius: 195, mass: 0.7, rotation: [0.55, 0.35, -0.38] },
  { shape: () => brick(1, 2, PALETTE.pink, true), x: 0.94, y: 0.84, scale: 2.2, radius: 230, mass: 1, rotation: [-0.35, 0.9, 0.35] },
  { shape: () => brick(1, 1, PALETTE.violet), x: 0.72, y: 0.92, scale: 1.9, radius: 180, mass: 0.75, rotation: [0.55, -0.3, 0.25] },
];

export function mountHeroScene(hero, canvas, reducedMotion = false, onBodyVisibility = () => {}) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: "low-power" });
  } catch {
    hero.classList.add("no-webgl");
    canvas.dataset.rendered = "false";
    return { setPaused() {}, dispose() {} };
  }
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.02;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.7));

  const scene = new THREE.Scene();
  scene.add(new THREE.AmbientLight(0xffffff, 1.25));
  const key = new THREE.DirectionalLight(0xffffff, 2.7);
  key.position.set(-5, 8, 10);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x9fcaff, 1.7);
  rim.position.set(7, -3, 5);
  scene.add(rim);
  const camera = new THREE.OrthographicCamera(-6, 6, 4, -4, 0.1, 100);
  camera.position.z = 24;

  const bodies = PIECES.map((spec) => {
    const group = spec.shape();
    group.rotation.set(...spec.rotation);
    scene.add(group);
    return {
      ...spec,
      group,
      homeX: 0,
      homeY: 0,
      offsetX: 0,
      offsetY: 0,
      vx: 0,
      vy: 0,
    };
  });
  const pointer = { active: false, x: 0, y: 0, vx: 0, vy: 0, lastMove: 0 };
  let width = 1;
  let height = 1;
  let pixelsPerUnit = 1;
  let visible = true;
  let motionPaused = reducedMotion;
  let raf = 0;
  let lastFrame = performance.now();

  function position(body) {
    body.group.position.set(
      (body.homeX + body.offsetX - width / 2) / pixelsPerUnit,
      (height / 2 - body.homeY - body.offsetY) / pixelsPerUnit,
      0,
    );
  }

  function resize() {
    const rect = hero.getBoundingClientRect();
    width = Math.max(1, rect.width);
    height = Math.max(1, rect.height);
    pixelsPerUnit = width / 12;
    const worldHeight = height / pixelsPerUnit;
    camera.left = -6;
    camera.right = 6;
    camera.top = worldHeight / 2;
    camera.bottom = -worldHeight / 2;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height, false);
    const mobileAnchors = [
      [-0.02, 0.25], [1.13, 0.28], [-0.10, 0.52], [0.08, 1.04],
      [1.12, 0.62], [1.05, 1.01], [0.73, 1.13],
    ];
    const mobile = width < 680;
    for (const [index, body] of bodies.entries()) {
      body.homeX = (mobile ? mobileAnchors[index][0] : body.x) * width;
      body.homeY = (mobile ? mobileAnchors[index][1] : body.y) * height;
      body.offsetX = 0;
      body.offsetY = 0;
      body.vx = 0;
      body.vy = 0;
      body.group.scale.setScalar(body.scale * (mobile ? 1.15 : width < 1000 ? 0.88 : 1));
      body.group.visible = width < 1100;
      onBodyVisibility(index, false);
      position(body);
    }
    renderer.render(scene, camera);
    canvas.dataset.rendered = "true";
    canvas.dataset.bodyCount = String(bodies.length);
  }

  function onPointerMove(event) {
    if (motionPaused || event.pointerType === "touch") return;
    const rect = hero.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const now = performance.now();
    const dt = Math.max((now - pointer.lastMove) / 1000, 0.008);
    if (pointer.active) {
      pointer.vx = Math.max(-1800, Math.min(1800, (x - pointer.x) / dt));
      pointer.vy = Math.max(-1800, Math.min(1800, (y - pointer.y) / dt));
    }
    pointer.x = x;
    pointer.y = y;
    pointer.lastMove = now;
    pointer.active = true;
  }

  function onPointerLeave() {
    pointer.active = false;
    pointer.vx = 0;
    pointer.vy = 0;
  }

  function tick(now) {
    if (motionPaused) return;
    raf = requestAnimationFrame(tick);
    const dt = Math.min((now - lastFrame) / 1000, 1 / 30);
    lastFrame = now;
    if (document.hidden || !visible) return;
    if (now - pointer.lastMove > 85) {
      const drag = Math.exp(-13 * dt);
      pointer.vx *= drag;
      pointer.vy *= drag;
    }
    bodies.forEach((body, index) => {
      stepBody(body, pointer, dt);
      position(body);
      if (width >= 1100) {
        const active = Math.hypot(body.offsetX, body.offsetY) > 3;
        if (body.group.visible !== active) {
          body.group.visible = active;
          if (active) canvas.dataset.lastActivatedIndex = String(index);
          onBodyVisibility(index, active);
        }
      }
      body.group.rotation.x = body.rotation[0] + Math.sin(now * 0.00044 + index) * 0.055 - body.offsetY * 0.0009;
      body.group.rotation.y = body.rotation[1] + Math.sin(now * 0.00031 + index * 1.5) * 0.09 + body.offsetX * 0.0011;
      body.group.rotation.z = body.rotation[2] + Math.cos(now * 0.00037 + index) * 0.035;
    });
    if (canvas.dataset.motionObserved !== "true" &&
      bodies.some((body) => Math.hypot(body.offsetX, body.offsetY) > 4)) {
      canvas.dataset.motionObserved = "true";
    }
    renderer.render(scene, camera);
  }

  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(hero);
  const visibilityObserver = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; });
  visibilityObserver.observe(hero);
  hero.addEventListener("pointermove", onPointerMove, { passive: true });
  hero.addEventListener("pointerleave", onPointerLeave);
  resize();
  if (!motionPaused) raf = requestAnimationFrame(tick);

  return {
    setPaused(value) {
      if (motionPaused === value) return;
      motionPaused = value;
      if (value) {
        cancelAnimationFrame(raf);
        onPointerLeave();
        if (width >= 1100) bodies.forEach((body, index) => {
          body.group.visible = false;
          onBodyVisibility(index, false);
        });
      } else {
        lastFrame = performance.now();
        raf = requestAnimationFrame(tick);
      }
    },
    dispose() {
      cancelAnimationFrame(raf);
      resizeObserver.disconnect();
      visibilityObserver.disconnect();
      hero.removeEventListener("pointermove", onPointerMove);
      hero.removeEventListener("pointerleave", onPointerLeave);
      scene.traverse((object) => {
        if (object.isMesh) {
          object.geometry.dispose();
          object.material.dispose();
        }
      });
      renderer.dispose();
    },
  };
}
