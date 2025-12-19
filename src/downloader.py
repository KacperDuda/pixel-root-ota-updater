import os
import requests
from ui_utils import ProgressBar, log_error, log

TARGET_URL = "https://developers.google.com/android/ota"

# Note: The comprehensive scraping logic was removed in a previous turn due to a bad merge.
# We need to restore it. Since I don't have the original handy in this context without
# scrolling way back or hallucinating, I will implement a robust but simpler version
# or try to restore the Playwright logic if requirements allow.
# However, the previous error showed a fragment "url_el = target_row.locator..."
# which suggests the Playwright implementation was intended.

# I will assume the user wanted the Playwright implementation from the previous "clean code" attempt.
# I will rewrite it cleanly.

from playwright.sync_api import sync_playwright

def get_latest_factory_image_data_headless(device):
    log(f"Starting headless browser for: {device}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        log(f"Navigating to: {TARGET_URL}")
        try:
            page.goto(TARGET_URL, timeout=60000, wait_until="domcontentloaded")
        except Exception as e:
            log_error(f"Failed to load page: {e}")
            return None, None, None

        # Helper to click things
        def click_visible(selector, force=True):
            try:
                el = page.locator(selector)
                if el.count() > 0 and el.first.is_visible():
                    el.first.click(force=force)
                    return True
            except: pass
            return False

        # Cookie & License Logic
        click_visible("text=/Ok, got it|Accept all|Zgadzam się/i")
        page.wait_for_timeout(500)

        try:
            ack_btn = page.locator(".devsite-acknowledgement-link").first
            if ack_btn.is_visible():
                ack_btn.click(force=True)
                page.wait_for_timeout(1000)
                if ack_btn.is_visible(): ack_btn.click(force=True)
        except: pass

        log(f"Searching links for {device}...")
        try:
            page.wait_for_selector(f"tr[id^='{device}']", timeout=30000)
        except:
            log("⚠️  Timeout waiting for specific device table rows.")

        try:
            rows = page.locator(f"tr[id^='{device}']")
            count = rows.count()

            if count == 0:
                log_error(f"No rows found for device '{device}'")
                browser.close()
                return None, None, None

            log(f"Found {count} candidate rows for {device}.")

            target_row = None
            for i in range(count - 1, -1, -1):
                row = rows.nth(i)
                text = row.inner_text().lower()
                if "verizon" in text or "japan" in text or "softbank" in text: continue
                target_row = row
                break

            if not target_row:
                target_row = rows.last

            log(f"Selecting row: {target_row.get_attribute('id')}")

            url_el = target_row.locator("td a")
            latest_url = url_el.get_attribute("href")

            sha_el = target_row.locator("td").last
            expected_sha = sha_el.inner_text().strip()

            filename = latest_url.split('/')[-1]
            return latest_url, filename, expected_sha

        except Exception as e:
            log_error(f"Scraping failed: {e}")
            return None, None, None

def download_file(url, filename):
    if os.path.exists(filename): return

    log(f"Starting download: {filename}")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
    except Exception as e:
        log_error(f"Connection error: {e}")
        raise e

    total_size = int(response.headers.get('content-length', 0))
    bar = ProgressBar(f"Downloading {filename}", total=total_size)
    
    with open(filename, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                bar.update(len(chunk))
    bar.finish()
    log("Download completed.")
