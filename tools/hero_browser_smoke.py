"""Verify approved desktop art, real 3D hover, themes, and mobile geometry.

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
        assert page.locator(".hero-reference").get_attribute("data-body-count") == "7"
        assert page.locator("#home-title").inner_text() == "REALITY"
        assert page.locator(".hero-actions .button").count() == 2
        assert page.locator("body").get_attribute("data-hero-theme") == "light"
        # The reference artwork is visual; these real anchors must align with
        # the buttons and navigation that a user sees in that artwork.
        hit_targets = {
            (590, 44): "/#why-reality",
            (695, 44): "/docs",
            (802, 44): "/playground",
            (932, 44): "/dashboard",
            (1080, 44): "/dashboard/keys",
            (675, 719): "/playground",
            (927, 719): "/docs",
        }
        for point, href in hit_targets.items():
            actual = page.evaluate(
                "([x, y]) => document.elementFromPoint(x, y)?.closest('a')?.getAttribute('href')",
                list(point),
            )
            assert actual == href, (point, actual, href)
        page.screenshot(path=str(output / "reality-hero-light.png"), full_page=False)

        page.wait_for_function("document.body.dataset.heroTheme === 'dark'", timeout=5000)
        page.wait_for_timeout(900)
        assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(27, 28, 30)"
        page.screenshot(path=str(output / "reality-hero-dark.png"), full_page=False)
        page.mouse.move(650, 470)
        page.mouse.move(120, 470, steps=4)
        page.locator("#hero-3d[data-motion-observed=true]").wait_for(timeout=5000)
        page.wait_for_function(
            "Number(document.querySelector('.hero-reference')?.dataset.active3dCount) > 0",
            timeout=5000,
        )
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
                    "approved_artwork_planes": 7,
                    "real_3d_hover": "PASS",
                    "cursor_repulsion": "PASS",
                    "three_second_theme": "PASS",
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
