from playwright.sync_api import sync_playwright
import os

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    file_url = f"file://{os.path.abspath('dashboard/index.html')}"

    page.goto(file_url)

    os.makedirs('/home/jules/verification/screenshots', exist_ok=True)

    # Go to videos tab to see the search box
    page.click('#nav-videos')
    page.wait_for_selector('#video-search', state='visible')

    page.focus('#video-search')
    page.screenshot(path='/home/jules/verification/screenshots/search_focus.png')

    # Go to logs tab to see a toggle switch
    page.click('#nav-logs')
    page.wait_for_selector('#log-autoscroll', state='attached')
    page.focus('#log-autoscroll')
    page.screenshot(path='/home/jules/verification/screenshots/toggle_focus.png')

    browser.close()
