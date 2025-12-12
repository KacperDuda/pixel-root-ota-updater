import os
import re
import requests
import sys
from playwright.sync_api import sync_playwright
from ui_utils import print_status, Color, ProgressBar, log_error, log

TARGET_URL = "https://developers.google.com/android/images"

def get_latest_factory_image_data_headless(device):
    log(f"Starting headless browser for: {device}...")
    with sync_playwright() as p:
        # Launch browser
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
        # License
        try:
            ack_btn = page.locator(".devsite-acknowledgement-link").first
            if ack_btn.is_visible():
                ack_btn.click(force=True)
                page.wait_for_timeout(1000)
                if ack_btn.is_visible(): ack_btn.click(force=True)
                try: ack_btn.wait_for(state="hidden", timeout=5000)
                except: pass
        except: pass

        # Find Links
        log(f"Searching links for {device}...")
        try: page.wait_for_selector("a[href*='.zip']", timeout=30000)
        except: log("⚠️  Timeout waiting for links table.")

        content = page.content()
        link_regex = f'href="([^"]*?{device}[^"]*?\\.zip)"'
        match = re.search(link_regex, content)
        
        if not match:
            log_error(f"No image found for '{device}'")
            browser.close()
            return None, None, None
        
        latest_url = match.group(1)
        filename = latest_url.split('/')[-1]
        log(f"Found URL: {latest_url}")
        
        expected_sha = None
        try:
            row_handle = page.query_selector(f"//a[contains(@href, '{filename}')]/ancestor::tr")
            if row_handle:
                expected_sha = re.search(r'\\b[a-f0-9]{64}\\b', row_handle.inner_text()).group(0)
                log(f"Found SHA256: {expected_sha}")
        except: pass

        browser.close()
        return latest_url, filename, expected_sha

def download_file(url, filename):
    if os.path.exists(filename): return

    log(f"Starting download: {filename}")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
    except Exception as e:
        log_error(f"Connection error: {e}")
        sys.exit(1)

    total_size = int(response.headers.get('content-length', 0))
    bar = ProgressBar(f"Downloading {filename}", total=total_size)
    
    with open(filename, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                bar.update(len(chunk))
    bar.finish()
    log("Download completed.")
