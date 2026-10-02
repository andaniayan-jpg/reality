# Reality developer website

The homepage is a continuously rendered Three.js scene with live HTML text and
links. Seven procedural 3D pieces loosely follow the supplied light/dark visual
references. There is no static-image-to-mesh swap when the cursor approaches.
The renderer is bundled locally, so the hero does not need a third-party CDN.
The live `REALITY` headline prefers Arial Black, with desktop-only proportions,
spacing, and theme colors tuned against the 1586 × 992 references.

The supplied references were **still images, not 3D model files**. The meshes
are authored in `hero3d.js`, not reconstructed source models. Exact hidden
faces, material response, shadows, and pixel-identical appearance require the
original 3D assets. The source artwork remains in `assets/` as design references;
neither image is a geometry input to Reality's API.

Mouse approach velocity strengthens a distance-weighted repulsive force. Each
object has mass, low-drag velocity, angular velocity, and elastic viewport
boundaries. Objects drift and tumble continuously without changing scale or
springing back to their original positions. The homepage palette alternates
between white and charcoal every three seconds with a 1.7-second color fade.
The pause button stops both the palette cycle and motion; reduced-motion users
start paused. The copy remains available if WebGL cannot initialize.

To modify the hero, install Node.js 20+ and run:

```bash
cd apps/web
npm ci
npm run build:hero
npm test
```

From the repository root, `python tools/dev_web.py` serves the static website.
With Playwright Chromium installed, `python tools/hero_browser_smoke.py`
verifies continuous drift, velocity-sensitive cursor response, fixed scale,
smooth theme transition, pause, reduced-motion behavior, and mobile layout.
The existing playground still requires a running Reality API.
