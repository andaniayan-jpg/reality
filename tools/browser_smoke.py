"""Exercise the local website with a real browser and real Reality geometry.

Start the API on 127.0.0.1:8000 and the static website on 127.0.0.1:3000,
then run ``python tools/browser_smoke.py``. Requires optional Playwright and
its Chromium browser. SMS delivery is not exercised without provider keys.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

import trimesh
from playwright.sync_api import sync_playwright


def main() -> None:
    email = f"browser-{secrets.token_hex(6)}@example.com"
    password = secrets.token_urlsafe(18)
    mesh = trimesh.creation.box(extents=(1.0, 2.0, 3.0))
    payload = mesh.export(file_type="obj").encode("utf-8")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        page.goto("http://127.0.0.1:3000/dashboard")
        page.locator("#email-login input[name=email]").fill(email)
        page.locator("#email-login input[name=password]").fill(password)
        page.locator("#email-register").click()
        page.wait_for_timeout(800)
        if page.locator("#status.error").count():
            raise RuntimeError(page.locator("#status.error").inner_text())
        page.get_by_text("Your workspace.").wait_for()

        page.goto("http://127.0.0.1:3000/dashboard/keys")
        page.locator("#key-create button").click()
        page.locator("#key-reveal").wait_for(state="visible")
        raw_key = page.locator("#new-key").inner_text()
        assert raw_key.startswith("rlt_test_")

        page.goto("http://127.0.0.1:3000/playground")
        page.locator('#upload input[name="file"]').set_input_files(
            {"name": "browser-cube.obj", "mimeType": "text/plain", "buffer": payload}
        )
        page.locator("#upload button").click()
        page.get_by_text("Model ready").wait_for(timeout=30000)
        page.wait_for_function(
            "document.querySelector('#viewer')?.getAttribute('src')?.startsWith('blob:')"
        )
        viewer_registered = page.evaluate("Boolean(customElements.get('model-viewer'))")
        summary = json.loads(page.locator("#output").inner_text())
        assert summary["format"] == "obj"

        page.locator('#query select[name="query"]').select_option("parts")
        page.locator("#query button").click()
        page.get_by_text("Query complete").wait_for()
        parts = json.loads(page.locator("#output").inner_text())
        assert len(parts) == 1

        page.locator('#query select[name="query"]').select_option("measure")
        page.locator('#query input[name="first"]').fill(parts[0]["name"])
        page.locator("#query button").click()
        page.get_by_text("Query complete").wait_for()
        measurement = json.loads(page.locator("#output").inner_text())
        assert measurement["backend"] and measurement["value"] is not None, measurement
        assert not errors, errors
        screenshot = Path("output/playwright/reality-playground.png")
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(
            path=str(screenshot.with_name("reality-playground-mobile.png")), full_page=True
        )
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        print(
            json.dumps(
                {
                    "browser": browser.version,
                    "login": "PASS",
                    "api_key": "PASS",
                    "upload": "PASS",
                    "summary": "PASS",
                    "preview_fetch": "PASS",
                    "viewer_registered": viewer_registered,
                    "parts": "PASS",
                    "measure": "PASS",
                    "screenshot": str(screenshot),
                    "mobile_no_horizontal_overflow": "PASS",
                }
            )
        )
        browser.close()


if __name__ == "__main__":
    main()
