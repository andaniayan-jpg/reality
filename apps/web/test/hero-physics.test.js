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

test("an exact-center hit follows cursor motion instead of jumping upward", () => {
  const force = repulsionAcceleration(
    { active: true, x: 100, y: 100, vx: 900, vy: 0 }, 100, 100, 150,
  );
  assert.ok(force.x > 0);
  assert.equal(force.y, 0);
});

const makeBody = (mass = 1) => ({
  x: 100, y: 100, vx: 0, vy: 0, radius: 180, mass,
  spin: 0.1, angle: 0, tiltX: 0, tiltY: 0, tiltVX: 0.07, tiltVY: -0.05,
});

test("free-flight retains momentum and rotation instead of returning home", () => {
  const body = makeBody();
  body.vx = 80;
  stepBody(body, { active: false }, 30);
  const firstX = body.x;
  for (let i = 0; i < 60; i += 1) stepBody(body, { active: false }, 1 / 60);
  assert.ok(body.x > firstX + 60);
  assert.ok(body.angle > 0);
  assert.ok(body.tiltX > 0);
});

test("repulsion pushes away and motion stays within finite hero bounds", () => {
  const body = makeBody();
  body.radius = 200;
  const pointer = { active: true, x: 90, y: 100, vx: 1800, vy: 0 };
  stepBody(body, pointer, 1 / 60, { width: 300, height: 200 });
  assert.ok(body.x > 100);
  for (let i = 0; i < 1000; i += 1) stepBody(body, { active: false }, 1 / 60,
    { width: 300, height: 200 });
  assert.ok(body.x >= 0 && body.x <= 300);
});

test("a lighter object accelerates more than a heavier one", () => {
  const light = makeBody(0.5);
  const heavy = makeBody(3);
  const pointer = { active: true, x: 50, y: 100, vx: 500, vy: 0 };
  stepBody(light, pointer, 1 / 60);
  stepBody(heavy, pointer, 1 / 60);
  assert.ok(light.x > heavy.x);
});
