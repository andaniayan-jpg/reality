"""Verify live 3D motion, smooth themes, and mobile geometry.

Run ``python tools/dev_web.py`` first. Requires Playwright Chromium.
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    output = Path("output/playwright")
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1586, "height": 992}, device_scale_factor=1)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:3000/", wait_until="networkidle")
        page.locator("#hero-3d[data-rendered=true]").wait_for(timeout=15000)
        assert page.locator("#hero-3d").get_attribute("data-body-count") == "7"
        assert page.locator("#home-title").inner_text() == "REALITY"
        assert page.locator(".hero-actions .button").count() == 2
        assert page.locator("body").get_attribute("data-hero-theme") == "light"
        assert page.locator(".nav nav a").count() == 4
        before = page.evaluate("document.querySelector('#hero-3d').heroMotionState")
        page.wait_for_timeout(350)
        drift = page.evaluate("document.querySelector('#hero-3d').heroMotionState")
        assert any(abs(a["x"] - b["x"]) > 1 for a, b in zip(before, drift, strict=True))
        page.screenshot(path=str(output / "reality-hero-light.png"), full_page=False)

        page.wait_for_function("document.body.dataset.heroTheme === 'dark'", timeout=5000)
        page.wait_for_timeout(450)
        mid_color = page.evaluate("getComputedStyle(document.body).backgroundColor")
        assert mid_color not in {"rgb(255, 255, 255)", "rgb(27, 28, 30)"}, mid_color
        page.wait_for_timeout(1500)
        assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(27, 28, 30)"
        page.screenshot(path=str(output / "reality-hero-dark.png"), full_page=False)
        before_push = page.evaluate("document.querySelector('#hero-3d').heroMotionState")
        target = before_push[0]
        page.mouse.move(target["x"] + 220, target["y"])
        page.mouse.move(target["x"] - 35, target["y"], steps=3)
        page.locator("#hero-3d[data-motion-observed=true]").wait_for(timeout=5000)
        page.wait_for_timeout(400)
        after_push = page.evaluate("document.querySelector('#hero-3d').heroMotionState")
        assert abs(after_push[0]["x"] - before_push[0]["x"]) > 2
        assert all(a["scale"] == b["scale"] for a, b in zip(before_push, after_push, strict=True))
        assert any(a["angle"] != b["angle"] for a, b in zip(before_push, after_push, strict=True))
        page.screenshot(path=str(output / "reality-hero-interaction.png"), full_page=False)
        page.locator("#motion-toggle").click()
        paused_theme = page.locator("body").get_attribute("data-hero-theme")
        page.wait_for_timeout(3200)
        assert page.locator("body").get_attribute("data-hero-theme") == paused_theme

        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(output / "reality-hero-mobile.png"), full_page=False)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert page.locator("#home-title").is_visible()
        assert page.locator(".hero-actions .button").first.is_visible()
        assert not errors, errors

        reduced = browser.new_page(viewport={"width": 1200, "height": 800}, reduced_motion="reduce")
        reduced.goto("http://127.0.0.1:3000/", wait_until="networkidle")
        reduced.locator("#hero-3d[data-rendered=true]").wait_for(timeout=15000)
        reduced.wait_for_timeout(3200)
        assert reduced.locator("body").get_attribute("data-hero-theme") == "light"
        assert reduced.locator("#motion-toggle").get_attribute("aria-pressed") == "true"
        browser.close()
        print(
            json.dumps(
                {
                    "webgl_bodies": 7,
                    "continuous_3d": "PASS",
                    "cursor_repulsion": "PASS",
                    "inertial_drift_and_rotation": "PASS",
                    "fixed_object_scale": "PASS",
                    "smooth_three_second_theme": "PASS",
                    "pause_control": "PASS",
                    "mobile_no_horizontal_overflow": "PASS",
                    "reduced_motion": "PASS",
                    "screenshots": [
                        str(output / "reality-hero-light.png"),
                        str(output / "reality-hero-dark.png"),
                        str(output / "reality-hero-interaction.png"),
                        str(output / "reality-hero-mobile.png"),
                    ],
                }
            )
        )


if __name__ == "__main__":
    main()
