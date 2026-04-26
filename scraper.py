"""
Verra VCM Registry - CSV Downloader
Uses Playwright to control a real browser, bypassing Cloudflare protection.
Clicks Search, then Export CSV, and saves the file.
"""

import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright

VERRA_URL = "https://registry.verra.org/app/search/VCS"
OUTPUT_FILE = "verra_allprojects.csv"


async def download_verra_csv():
    async with async_playwright() as p:
        print("🚀 Launching browser...")

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]
        )

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )

        # Hide webdriver flag from Cloudflare
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)

        page = await context.new_page()

        # Manual stealth — patches Cloudflare detection points
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'platform', { get: () => 'MacIntel' });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
            window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );
            Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                return getParameter(parameter);
            };
        """)

        print(f"🌐 Navigating to {VERRA_URL}...")
        await page.goto(VERRA_URL, wait_until="networkidle", timeout=60000)

        # Wait for Cloudflare challenge to pass if present
        print("⏳ Waiting for page to fully load...")
        await page.wait_for_timeout(4000)

        # Check if we hit a Cloudflare block
        title = await page.title()
        print(f"   Page title: {title}")
        if "just a moment" in title.lower() or "cloudflare" in title.lower():
            print("⚠️  Cloudflare challenge detected — waiting longer...")
            await page.wait_for_timeout(8000)

        # Click Search button (no filters = all projects)
        print("🔍 Clicking Search...")
        search_button = page.locator("button:has-text('Search'), input[type='submit'][value*='Search'], [class*='search'] button").first
        await search_button.wait_for(state="visible", timeout=20000)
        await search_button.click()

        # Wait for results to load
        print("⏳ Waiting for search results...")
        await page.wait_for_timeout(5000)
        await page.wait_for_load_state("networkidle", timeout=30000)

        # Set up download handler and click Export/CSV button
        print("📥 Clicking CSV Export button...")
        async with page.expect_download(timeout=60000) as download_info:
            csv_button = page.locator("button[title='Download CSV']")
            await csv_button.wait_for(state="visible", timeout=20000)
            await csv_button.click()

        download = await download_info.value
        print(f"✅ Download started: {download.suggested_filename}")

        # Save the file
        await download.save_as(OUTPUT_FILE)
        file_size = Path(OUTPUT_FILE).stat().st_size
        print(f"💾 Saved to: {OUTPUT_FILE} ({file_size:,} bytes)")

        # Quick check on row count
        with open(OUTPUT_FILE, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        print(f"📊 Rows in CSV: {len(lines):,} (including header)")

        await browser.close()
        print("✅ Done!")


if __name__ == "__main__":
    asyncio.run(download_verra_csv())
