# Reality developer website

The desktop hero uses the two approved 1586 × 992 images as its visual source.
At that viewport, its resting light and dark frames are pixel-identical to the
provided designs. When the cursor pushes an object, a real procedural Three.js
mesh replaces that object's painted appearance and moves with spring dynamics.
Actual links sit over the navigation and buttons in the artwork. At narrow
widths, the procedural three.js scene and live text take over completely.
The renderer is bundled locally, so the hero does not need a third-party CDN.

The supplied references were **still images, not 3D model files**. The hovering
meshes are volumetric but are authored in `hero3d.js`, not reconstructed source
models. Their appearance during movement is an approximation; exact hidden
faces, material response, and shadows require the original 3D assets. The
source artwork is stored in `assets/hero-light.png` and `assets/hero-dark.png`;
neither is a geometry input to Reality's API.

Mouse approach velocity strengthens a distance-weighted repulsive force. Each
object has mass, damping, and a spring that returns it toward its home position.
The homepage palette alternates between white and charcoal every three seconds.
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
verifies the desktop rest frames, link hit targets, cursor response,
three-second theme, pause, reduced-motion behavior, WebGL mobile fallback, and
mobile layout. The existing playground still requires a running Reality API.
