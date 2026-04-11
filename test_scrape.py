"""Quick test: can Playwright fetch 1688 company search?"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright
import time, re

keyword = "蓝牙耳机"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled','--no-sandbox'])
    ctx = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        locale='zh-CN',
    )

    # Visit 1688 homepage first for cookies
    page = ctx.new_page()
    print("1. Visiting 1688 homepage...")
    page.goto('https://www.1688.com/', wait_until='domcontentloaded', timeout=15000)
    time.sleep(2)
    page.close()

    # Search companies
    from urllib.parse import quote
    url = f'https://s.1688.com/company/company_search.htm?keywords={quote(keyword)}&button_click=top&n=y'
    page = ctx.new_page()
    print(f"2. Searching companies: {url}")
    page.goto(url, wait_until='domcontentloaded', timeout=20000)
    time.sleep(3)

    # Get page title and text length
    title = page.title()
    text = page.evaluate('() => document.body ? document.body.innerText.substring(0, 3000) : "EMPTY"')
    html_len = len(page.content())
    print(f"   Title: {title}")
    print(f"   HTML length: {html_len}")
    print(f"   Text preview (first 1000 chars):")
    print(text[:1000])

    # Check for company names
    companies = re.findall(r'[\u4e00-\u9fa5]{2,30}(?:有限公司|有限责任公司|股份有限公司|工厂|制造厂)', text)
    print(f"\n3. Found {len(companies)} company names:")
    for c in companies[:20]:
        print(f"   - {c}")

    # Also try product search
    url2 = f'https://s.1688.com/selloffer/offer_search.htm?keywords={quote(keyword)}&n=y&netType=1%2C11&sortType=booked'
    page2 = ctx.new_page()
    print(f"\n4. Searching products: {url2}")
    page2.goto(url2, wait_until='domcontentloaded', timeout=20000)
    time.sleep(3)
    text2 = page2.evaluate('() => document.body ? document.body.innerText.substring(0, 3000) : "EMPTY"')
    html_len2 = len(page2.content())
    print(f"   HTML length: {html_len2}")

    companies2 = re.findall(r'[\u4e00-\u9fa5]{2,30}(?:有限公司|有限责任公司|股份有限公司|工厂|制造厂)', text2)
    print(f"   Found {len(companies2)} company names:")
    for c in companies2[:20]:
        print(f"   - {c}")

    page.close()
    page2.close()
    browser.close()

print("\nDone!")
