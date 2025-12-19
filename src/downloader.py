```python
import os
import requests
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
