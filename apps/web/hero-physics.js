/** Deterministic, low-drag motion in the two-dimensional hero plane. */
export function repulsionAcceleration(pointer, objectX, objectY, radius) {
  if (!pointer.active || radius <= 0) return { x: 0, y: 0, approachSpeed: 0 };
  const dx = objectX - pointer.x;
  const dy = objectY - pointer.y;
  const distance = Math.hypot(dx, dy);
  if (distance >= radius) return { x: 0, y: 0, approachSpeed: 0 };

  // The pointer-to-object direction lets us distinguish an approaching cursor
  // from one moving away at the same speed.
  // At exact overlap, continue along the cursor's incoming direction instead
  // of inventing an upward impulse.
  const pointerSpeed = Math.hypot(pointer.vx, pointer.vy);
  const nx = distance > 1 ? dx / distance : pointerSpeed > 1 ? pointer.vx / pointerSpeed : 0;
  const ny = distance > 1 ? dy / distance : pointerSpeed > 1 ? pointer.vy / pointerSpeed : 0;
  const approachSpeed = Math.max(0, Math.min(1800, pointer.vx * nx + pointer.vy * ny));
  const proximity = 1 - distance / radius;
  const acceleration = proximity * proximity * (900 + 3 * approachSpeed);
  return { x: nx * acceleration, y: ny * acceleration, approachSpeed };
}

/** Integrate velocity and spin without any spring to an original position. */
export function stepBody(body, pointer, elapsedSeconds, bounds = null) {
  const dt = Math.max(0, Math.min(elapsedSeconds, 1 / 30));
  const force = repulsionAcceleration(pointer, body.x, body.y, body.radius);
  const inverseMass = 1 / Math.max(0.2, body.mass ?? 1);
  body.vx += force.x * inverseMass * dt;
  body.vy += force.y * inverseMass * dt;
  const speed = Math.hypot(body.vx, body.vy);
  if (speed > 680) {
    body.vx *= 680 / speed;
    body.vy *= 680 / speed;
  }
  const drag = Math.exp(-0.14 * dt);
  body.vx *= drag;
  body.vy *= drag;
  body.x += body.vx * dt;
  body.y += body.vy * dt;

  // Tangential cursor force adds tumble; a straight push adds no arbitrary lift.
  const torque = pointer.active
    ? force.x * (pointer.y - body.y) - force.y * (pointer.x - body.x)
    : 0;
  body.spin += Math.max(-2.8, Math.min(2.8, torque * 0.000008 * inverseMass)) * dt;
  body.spin *= Math.exp(-0.09 * dt);
  body.angle += body.spin * dt;
  body.tiltX += body.tiltVX * dt;
  body.tiltY += body.tiltVY * dt;

  if (bounds) {
    const margin = body.edgeMargin ?? 0;
    const minX = -margin;
    const maxX = bounds.width + margin;
    const minY = -margin;
    const maxY = bounds.height + margin;
    if (body.x < minX || body.x > maxX) {
      body.x = Math.max(minX, Math.min(maxX, body.x));
      body.vx = -body.vx * 0.88;
      body.spin += body.vy * 0.0003;
    }
    if (body.y < minY || body.y > maxY) {
      body.y = Math.max(minY, Math.min(maxY, body.y));
      body.vy = -body.vy * 0.88;
      body.spin -= body.vx * 0.0003;
    }
  }
  return body;
}
