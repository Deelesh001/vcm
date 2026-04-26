"""
Verra VCM Registry - CSV Downloader
Uses Playwright to load the page (getting Cloudflare cookies),
then uses the browser's own fetch() to call the CSV API directly.
"""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

VERRA_URL = "https://registry.verra.org/app/search/VCS"
CSV_URL = "https://registry.verra.org/uiapi/resource/resource/search?$skip=0&count=true&$format=csv&$exportFileName=allprojects.csv"
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

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'platform', { get: () => 'MacIntel' });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
            window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
        """)

        page = await context.new_page()

        print(f"🌐 Navigating to {VERRA_URL}...")
        await page.goto(VERRA_URL, wait_until="networkidle", timeout=60000)

        print("⏳ Waiting for page to fully load...")
        await page.wait_for_timeout(4000)

        title = await page.title()
        print(f"   Page title: {title}")
        if "just a moment" in title.lower() or "cloudflare" in title.lower():
            print("⚠️  Cloudflare challenge — waiting longer...")
            await page.wait_for_timeout(10000)

        # Intercept the search POST to capture the request body
        print("🔍 Intercepting search request body...")
        search_body = None

        async def handle_request(request):
            nonlocal search_body
            if "resource/search" in request.url and request.method == "POST" and "$format=csv" not in request.url:
                search_body = request.post_data
                print(f"   📦 Captured search body ({len(search_body or '')} bytes): {(search_body or '')[:200]}")

        page.on("request", handle_request)

        # Click Search
        print("🔍 Clicking Search...")
        search_button = page.locator("button:has-text('Search'), input[type='submit'][value*='Search'], [class*='search'] button").first
        await search_button.wait_for(state="visible", timeout=20000)
        await search_button.click()

        # Wait for results
        print("⏳ Waiting for search results to load...")
        await page.wait_for_timeout(8000)
        await page.wait_for_load_state("networkidle", timeout=30000)

        if not search_body:
            print("⚠️  No search body captured — using empty body")
            search_body = "{}"

        print(f"📥 Calling CSV API via browser fetch (with live cookies)...")

        # Use browser's own fetch — automatically carries cf_clearance + all cookies
        js_code = """
            async (csvUrl, bodyStr) => {
                const response = await fetch(csvUrl, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Accept": "text/csv",
                        "Referer": "https://registry.verra.org/app/search/VCS"
                    },
                    body: bodyStr
                });
                const status = response.status;
                const contentType = response.headers.get("content-type") || "";
                if (!response.ok) {
                    const text = await response.text();
                    throw new Error("HTTP " + status + ": " + text.substring(0, 200));
                }
                const text = await response.text();
                return { status, contentType, data: text, size: text.length };
            }
        """

        result = await page.evaluate(js_code, CSV_URL, search_body)

        print(f"   Status: {result['status']}")
        print(f"   Content-Type: {result['contentType']}")
        print(f"   Size: {result['size']:,} chars")

        if result['size'] < 100:
            raise Exception(f"❌ Response too small: {result['data'][:300]}")

        # Save the file
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(result['data'])

        lines = result['data'].split("\n")
        print(f"📊 Rows: {len(lines):,} (including header)")
        print(f"💾 Saved to: {OUTPUT_FILE}")

        await browser.close()
        print("✅ Done!")


if __name__ == "__main__":
    asyncio.run(download_verra_csv())
