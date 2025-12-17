
import asyncio
from playwright.async_api import async_playwright

async def check_pages():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        base_url = "https://sandbox.oxylabs.io/products"
        
        for i in range(1, 3):
            url = f"{base_url}?page={i}" if i > 1 else base_url
            print(f"Checking {url}...")
            await page.goto(url)
            # Wait for any .product-card
            try:
                # Wait up to 5s
                await page.wait_for_selector('div.product-card', timeout=5000)
                cards = page.locator('div.product-card')
                count = await cards.count()
                print(f"Page {i}: Found {count} cards.")
                if count > 0:
                    first_card = cards.first
                    h4_count = await first_card.locator('h4').count()
                    print(f"   First card has {h4_count} h4 elements.")
                    if h4_count > 0:
                        title = await first_card.locator('h4').inner_text()
                        print(f"   Title via h4: {title}")
                    else:
                        print("   ❌ No h4 found in card!")
                        # Debug HTML
                        html = await first_card.inner_html()
                        print(f"   Card HTML snippet: {html[:100]}...")
            except Exception as e:
                print(f"Page {i}: Result: 0 cards (Error: {e})")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(check_pages())
