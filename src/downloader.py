
import os
import re
import requests
import sys
from playwright.sync_api import sync_playwright
from ui_utils import print_status, Color, ProgressBar, log_error, log

TARGET_URL = "https://developers.google.com/android/ota"
KSU_RELEASES_URL = "https://github.com/KernelSU-Next/KernelSU-Next/releases/latest"

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

        # Find Links using robust Table logic based on user provided DOM
        log(f"Searching links for {device}...")
        try: 
            # Wait for any row with ID starting with device name to appear
            # Pattern: <tr id="frankel...">
            page.wait_for_selector(f"tr[id^='{device}']", timeout=30000)
        except: 
            log("⚠️  Timeout waiting for specific device table rows.")

        # Selector strategy:
        # 1. Find the first row whose ID starts with the device name (usually the latest build if sorted, or we grep for latest)
        # Actually Google lists them top-down. The first matching TR usually is the latest.
        # But we specifically want the one that is NOT 'verizon' etc if possible, but for now let's take the first visible one
        # or better, iterate and find the "latest" looking one.
        # But simple start: First match.
        
        try:
            # Get all rows for device
            rows = page.locator(f"tr[id^='{device}']")
            count = rows.count()
            
            if count == 0:
                log_error(f"No rows found for device '{device}'")
                browser.close()
                return None, None, None
                
            # Log found rows to help debug
            log(f"Found {count} candidate rows for {device}.")
            
            # Strategy: Iterate BACKWARDS (latest usually at bottom)
            # Filter for Europe (EMEA) or Global (no suffix/generic).
            # Avoid: Verizon, Japan, Softbank unless user specified (defaulting to Generic/EMEA).
            
            target_row = None
            
            # Iterate range(count-1, -1, -1)
            for i in range(count - 1, -1, -1):
                row = rows.nth(i)
                text = row.inner_text().lower()
                
                # Check region constraints
                # Pref: EMEA > Global > Anything else not excluded
                
                # Exclusions
                if "verizon" in text: continue
                if "japan" in text: continue
                if "softbank" in text: continue
                
                # If we are here, it's a potential candidate (EMEA or Global)
                # Since we iterate backwards, the first one we find is the "Latest Safe Build".
                
                # Optional: If EMEA is strictly preferred over Global even if Global is newer (rare), 
                # we might need more logic. Usually latest date wins.
                # Assuming simple "Latest Valid" is good.
                
                target_row = row
                break
                
            if not target_row:
                log("⚠️  No filtered rows found, falling back to absolute last row (risky).")
                target_row = rows.last
                
            row_id = target_row.get_attribute("id")
            log(f"Selecting row (Latest/Region-safe): {row_id}")
            log(f"Row Text: {target_row.inner_text().strip()}")

            # Extract URL from the link in 2nd column (td index 1)
            url_el = target_row.locator("td a") 
            latest_url = url_el.get_attribute("href")
            
            # Extract SHA256 from 3rd column (td index 2)
            sha_el = target_row.locator("td").last
            expected_sha = sha_el.inner_text().strip()
            
            if not latest_url:
                raise Exception("URL attribute missing")
                
            filename = latest_url.split('/')[-1]
            log(f"Found URL: {latest_url}")
            log(f"Found SHA256: {expected_sha}")
            
        except Exception as e:
            log_error(f"Scraping failed: {e}")
            browser.close()
            return None, None, None

        browser.close()
        return latest_url, filename, expected_sha

def get_latest_magisk_url():
    """
    Fetches the latest Magisk Release ZIP (v27.0+) URL using GitHub API.
    """
    log("Resolving latest Magisk version via API...")
    # Official Magisk Repo
    api_url = "https://api.github.com/repos/topjohnwu/Magisk/releases/latest"
    
    try:
        r = requests.get(api_url, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        tag_name = data.get("tag_name", "unknown")
        log(f"Latest Magisk tag: {tag_name}")
        
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            # Looking for Magisk-vXX.X.apk (Magisk can be renamed to .zip)
            if name.startswith("Magisk-v") and name.endswith(".apk"):
                url = asset.get("browser_download_url")
                log(f"Found Magisk APK (to be used as ZIP): {url}")
                return url
                
    except Exception as e:
        log_error(f"GitHub API failed: {e}")
        
    return None

def download_file(url, filename):
    if os.path.exists(filename): return

    log(f"Starting download: {filename}")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
    except Exception as e:
        log_error(f"Connection error: {e}")
        # Orchestrator handles exit, but here we prefer to fail loud
        # Or re-raise
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
