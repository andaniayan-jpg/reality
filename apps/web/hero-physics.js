/** Deterministic two-dimensional spring dynamics for hero object centers. */
export function repulsionAcceleration(pointer, objectX, objectY, radius) {
  if (!pointer.active || radius <= 0) return { x: 0, y: 0, approachSpeed: 0 };
  const dx = objectX - pointer.x;
  const dy = objectY - pointer.y;
  const distance = Math.hypot(dx, dy);
  if (distance >= radius) return { x: 0, y: 0, approachSpeed: 0 };

  // The pointer-to-object direction lets us distinguish an approaching cursor
  // from one moving away at the same speed.
  const nx = distance > 1 ? dx / distance : 0;
  const ny = distance > 1 ? dy / distance : -1;
  const approachSpeed = Math.max(0, Math.min(1800, pointer.vx * nx + pointer.vy * ny));
  const proximity = 1 - distance / radius;
  const acceleration = proximity * proximity * (900 + 3 * approachSpeed);
  return { x: nx * acceleration, y: ny * acceleration, approachSpeed };
}

export function stepBody(body, pointer, elapsedSeconds) {
  // A semi-implicit Euler step is stable enough here because the spring is
  // deliberately soft and frame time is bounded after background-tab pauses.
  const dt = Math.max(0, Math.min(elapsedSeconds, 1 / 30));
  const impulse = repulsionAcceleration(
    pointer,
    body.homeX + body.offsetX,
    body.homeY + body.offsetY,
    body.radius,
  );
  const spring = 25;
  const damping = 8;
  const inverseMass = 1 / Math.max(0.2, body.mass ?? 1);
  body.vx += (impulse.x * inverseMass - spring * body.offsetX - damping * body.vx) * dt;
  body.vy += (impulse.y * inverseMass - spring * body.offsetY - damping * body.vy) * dt;
  const speed = Math.hypot(body.vx, body.vy);
  if (speed > 650) {
    body.vx *= 650 / speed;
    body.vy *= 650 / speed;
  }
  body.offsetX += body.vx * dt;
  body.offsetY += body.vy * dt;
  const displacement = Math.hypot(body.offsetX, body.offsetY);
  if (displacement > 145) {
    body.offsetX *= 145 / displacement;
    body.offsetY *= 145 / displacement;
  }
  return body;
}
