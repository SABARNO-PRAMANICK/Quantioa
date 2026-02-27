"""Playwright screenshot capture — connects to already-running dev server."""
import asyncio
from playwright.async_api import async_playwright

SCREENSHOTS_DIR = "/home/sabarno/.gemini/antigravity/brain/bff6ccd0-df50-4540-b3b3-bee3405039f4"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        print("⏳ Connecting to dev server at localhost:3000...")
        await page.goto("http://localhost:3000", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)
        print("✅ Page loaded!")

        await page.screenshot(path=f"{SCREENSHOTS_DIR}/screenshot_hero.png")
        print("✅ Hero screenshot")

        await page.evaluate("window.scrollBy(0, 900)")
        await page.wait_for_timeout(500)
        await page.screenshot(path=f"{SCREENSHOTS_DIR}/screenshot_stats.png")
        print("✅ Stats screenshot")

        await page.evaluate("window.scrollBy(0, 800)")
        await page.wait_for_timeout(500)
        await page.screenshot(path=f"{SCREENSHOTS_DIR}/screenshot_features.png")
        print("✅ Features screenshot")

        await page.evaluate("window.scrollBy(0, 900)")
        await page.wait_for_timeout(500)
        await page.screenshot(path=f"{SCREENSHOTS_DIR}/screenshot_howitworks.png")
        print("✅ How It Works screenshot")

        await page.evaluate("window.scrollBy(0, 900)")
        await page.wait_for_timeout(500)
        await page.screenshot(path=f"{SCREENSHOTS_DIR}/screenshot_cta_footer.png")
        print("✅ CTA/Footer screenshot")

        await page.screenshot(path=f"{SCREENSHOTS_DIR}/screenshot_fullpage.png", full_page=True)
        print("✅ Full page screenshot")

        await browser.close()
        print("\n🎉 All screenshots saved!")

asyncio.run(main())
