import assert from "node:assert/strict";
import test from "node:test";

import { repulsionAcceleration, stepBody } from "../hero-physics.js";

test("an approaching cursor repels more strongly than a slow one", () => {
  const slow = repulsionAcceleration({ active: true, x: 0, y: 0, vx: 30, vy: 0 }, 50, 0, 150);
  const fast = repulsionAcceleration({ active: true, x: 0, y: 0, vx: 900, vy: 0 }, 50, 0, 150);
  const retreating = repulsionAcceleration({ active: true, x: 0, y: 0, vx: -900, vy: 0 }, 50, 0, 150);
  assert.ok(fast.x > slow.x);
  assert.ok(slow.x > retreating.x);
  assert.equal(retreating.approachSpeed, 0);
});

test("a cursor outside the interaction radius has no effect", () => {
  assert.deepEqual(
    repulsionAcceleration({ active: true, x: 0, y: 0, vx: 1000, vy: 0 }, 250, 0, 150),
    { x: 0, y: 0, approachSpeed: 0 },
  );
});

test("spring returns a displaced object toward home and clamps long frames", () => {
  const body = { homeX: 100, homeY: 100, offsetX: 70, offsetY: 0, vx: 0, vy: 0, radius: 150 };
  stepBody(body, { active: false }, 30);
  assert.ok(body.offsetX < 70);
  for (let i = 0; i < 240; i += 1) stepBody(body, { active: false }, 1 / 60);
  assert.ok(Math.abs(body.offsetX) < 0.01);
});

test("repulsion stays within the displacement cap", () => {
  const body = { homeX: 100, homeY: 100, offsetX: 0, offsetY: 0, vx: 0, vy: 0, radius: 200 };
  const pointer = { active: true, x: 90, y: 100, vx: 1800, vy: 0 };
  for (let i = 0; i < 300; i += 1) stepBody(body, pointer, 1 / 60);
  assert.ok(Math.hypot(body.offsetX, body.offsetY) <= 145.000001);
});

test("a lighter object accelerates more than a heavier one", () => {
  const makeBody = (mass) => ({
    homeX: 100, homeY: 100, offsetX: 0, offsetY: 0, vx: 0, vy: 0, radius: 180, mass,
  });
  const light = makeBody(0.5);
  const heavy = makeBody(3);
  const pointer = { active: true, x: 50, y: 100, vx: 500, vy: 0 };
  stepBody(light, pointer, 1 / 60);
  stepBody(heavy, pointer, 1 / 60);
  assert.ok(light.offsetX > heavy.offsetX);
});
