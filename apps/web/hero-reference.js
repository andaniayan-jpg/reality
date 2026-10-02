import { stepBody } from "/hero-physics.js";

// These silhouettes isolate the seven objects in the approved 1586 × 992
// artwork. The exact source artwork remains the resting frame; each object
// becomes an independently movable image plane only during interaction.
const PIECES = [
  { center: [0.105, 0.15], radius: 235, mass: 1, shape: "polygon(0 0, 16% 0, 23% 12%, 22% 21%, 4% 32%, 0 27%)" },
  { center: [0.87, 0.20], radius: 300, mass: 2.2, shape: "polygon(76% 0, 100% 0, 100% 56%, 92% 53%, 81% 47%, 74% 31%)" },
  { center: [0.08, 0.48], radius: 225, mass: 0.9, shape: "polygon(1% 39%, 4.5% 35%, 8% 35%, 11% 40%, 15.5% 56%, 15% 59%, 11% 62%, 5% 60%, 1% 54%)" },
  { center: [0.16, 0.83], radius: 320, mass: 2.5, shape: "polygon(0 59%, 25% 63%, 34% 100%, 0 100%)" },
  { center: [0.86, 0.63], radius: 195, mass: 0.7, shape: "polygon(83% 51%, 92% 52%, 95% 62%, 91% 74%, 81% 72%, 79% 64%)" },
  { center: [0.94, 0.84], radius: 230, mass: 1, shape: "polygon(92% 65%, 100% 65%, 100% 100%, 86% 100%, 83% 75%)" },
  { center: [0.72, 0.92], radius: 180, mass: 0.75, shape: "polygon(69% 78%, 80% 82%, 84% 100%, 60% 100%, 60% 91%)" },
];

export function mountReferenceScene(hero, reference, reducedMotion = false) {
  const active3d = new Set();
  const bodies = PIECES.map((spec) => {
    const erase = document.createElement("div");
    erase.className = "hero-reference-erase";
    erase.style.clipPath = spec.shape;
    const image = document.createElement("div");
    image.className = "hero-reference-piece";
    image.style.clipPath = spec.shape;
    reference.append(erase, image);
    return {
      ...spec, erase, image, homeX: 0, homeY: 0,
      offsetX: 0, offsetY: 0, vx: 0, vy: 0,
    };
  });
  const pointer = { active: false, x: 0, y: 0, vx: 0, vy: 0, lastMove: 0 };
  let paused = reducedMotion;
  let frame = 0;
  let lastFrame = performance.now();

  function resize() {
    const { width, height } = hero.getBoundingClientRect();
    for (const body of bodies) {
      body.homeX = body.center[0] * width;
      body.homeY = body.center[1] * height;
      body.offsetX = body.offsetY = body.vx = body.vy = 0;
      body.erase.style.opacity = "0";
      body.image.style.opacity = "0";
      body.image.style.transform = "translate3d(0, 0, 0)";
    }
    active3d.clear();
    reference.dataset.active3dCount = "0";
    reference.dataset.bodyCount = String(bodies.length);
  }

  function onPointerMove(event) {
    if (paused || event.pointerType === "touch" || window.innerWidth < 1100) return;
    const bounds = hero.getBoundingClientRect();
    const x = event.clientX - bounds.left;
    const y = event.clientY - bounds.top;
    const now = performance.now();
    const dt = Math.max((now - pointer.lastMove) / 1000, 0.008);
    if (pointer.active) {
      pointer.vx = Math.max(-1800, Math.min(1800, (x - pointer.x) / dt));
      pointer.vy = Math.max(-1800, Math.min(1800, (y - pointer.y) / dt));
    }
    Object.assign(pointer, { active: true, x, y, lastMove: now });
  }

  function onPointerLeave() {
    pointer.active = false;
    pointer.vx = pointer.vy = 0;
  }

  function tick(now) {
    if (paused) return;
    frame = requestAnimationFrame(tick);
    const dt = Math.min((now - lastFrame) / 1000, 1 / 30);
    lastFrame = now;
    if (document.hidden || window.innerWidth < 1100) return;
    if (now - pointer.lastMove > 85) {
      const drag = Math.exp(-13 * dt);
      pointer.vx *= drag;
      pointer.vy *= drag;
    }
    for (const body of bodies) {
      stepBody(body, pointer, dt);
      const displaced = Math.hypot(body.offsetX, body.offsetY) > 0.5;
      body.erase.style.opacity = displaced ? "1" : "0";
      body.image.style.opacity = displaced ? "1" : "0";
      body.image.style.transform = `translate3d(${body.offsetX}px, ${body.offsetY}px, 0)`;
      if (Math.hypot(body.offsetX, body.offsetY) > 4) reference.dataset.motionObserved = "true";
    }
  }

  const observer = new ResizeObserver(resize);
  observer.observe(hero);
  hero.addEventListener("pointermove", onPointerMove, { passive: true });
  hero.addEventListener("pointerleave", onPointerLeave);
  resize();
  if (!paused) frame = requestAnimationFrame(tick);
  return {
    set3dActive(index, active) {
      const body = bodies[index];
      if (!body) return;
      if (active) active3d.add(index);
      else active3d.delete(index);
      body.erase.style.opacity = active ? "1" : "0";
      body.image.style.opacity = "0";
      reference.dataset.active3dCount = String(active3d.size);
    },
    setPaused(value) {
      if (paused === value) return;
      paused = value;
      if (paused) {
        cancelAnimationFrame(frame);
        onPointerLeave();
      } else {
        lastFrame = performance.now();
        frame = requestAnimationFrame(tick);
      }
    },
    dispose() {
      cancelAnimationFrame(frame);
      observer.disconnect();
      hero.removeEventListener("pointermove", onPointerMove);
      hero.removeEventListener("pointerleave", onPointerLeave);
    },
  };
}
