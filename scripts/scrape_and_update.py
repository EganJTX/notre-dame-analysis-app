"""Weekly Notre Dame football results scraper.

Re-scrapes the full historical game table from alexanderbess.com and
overwrites data.json with the result. This replaces the old Google
Sheets push (see notre-dame-app/scripts/scrape_and_push.py) now that
the app reads its data straight from this repo's data.json.
"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import os
import sys
import json

# --- Config ---
ALLOWED_MONTHS = [1, 8, 9, 10, 11, 12]  # football season window
DATA_FILE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data.json"))
EXPECTED_COLUMNS = [
    'Date', 'ND Rank', 'ND Final Rank', 'Result', 'Site', 'ND Coach',
    'ND Score', 'Opp Score', 'Opponent', 'Opp Rank', 'Opp Final Rank', 'Opp Coach'
]

# --- Month guard ---
current_month = datetime.now().month
if current_month not in ALLOWED_MONTHS:
    print(f"Not an allowed month ({current_month}). Skipping scrape.")
    sys.exit(0)

# --- Chrome options for GitHub Actions ---
chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")


def create_driver():
    print("Initializing Chrome WebDriver...")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    print("Chrome WebDriver initialized successfully")
    return driver


try:
    driver = create_driver()
except Exception as e:
    print(f"WebDriver init failed: {e}. Retrying...")
    time.sleep(2)
    driver = create_driver()

try:
    print("Loading page...")
    driver.get("http://alexanderbess.com/NDfootball_2.php")

    wait = WebDriverWait(driver, 10)
    search_btn = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Search']"))
    )

    print("Clicking search button...")
    search_btn.click()

    wait.until(EC.presence_of_element_located((By.ID, "gameListTable")))
    time.sleep(3)

    print("Parsing table data...")
    soup = BeautifulSoup(driver.page_source, "html.parser")
    table = soup.find("table", id="gameListTable")

    if not table:
        raise ValueError("No <table> with id='gameListTable' found.")

    headers = []
    thead = table.find('thead')
    if thead:
        header_row = thead.find('tr')
        if header_row:
            headers = [th.get_text(strip=True) for th in header_row.find_all('th')]

    rows = []
    tbody = table.find('tbody')
    row_tags = tbody.find_all('tr') if tbody else table.find_all('tr')[1:]

    for row in row_tags:
        cols = [td.get_text(strip=True) for td in row.find_all('td')]
        if cols:
            rows.append(cols)

    if not headers and rows:
        headers = [f"Column {i+1}" for i in range(len(rows[0]))]

    df = pd.DataFrame(rows, columns=headers)

    if len(df.columns) == 12:
        df.columns = EXPECTED_COLUMNS
    else:
        raise ValueError(f"Expected 12 columns but found {len(df.columns)}: {list(df.columns)}")

    if df.empty:
        raise ValueError("Scraped DataFrame is empty.")

    print(f"Scraped {len(df)} rows with {len(df.columns)} columns")

except Exception as e:
    print(f"Scraping error: {e}")
    driver.quit()
    sys.exit(1)

finally:
    driver.quit()

# The site's raw date text isn't guaranteed to already be ISO (YYYY-MM-DD).
# index.html parses "Date" with JS `new Date(...)`, which is unreliable on
# non-ISO formats, so normalize here to match what data.json already uses.
df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")

df["ND Score"] = pd.to_numeric(df["ND Score"], errors="coerce").fillna(0).astype(int)
df["Opp Score"] = pd.to_numeric(df["Opp Score"], errors="coerce").fillna(0).astype(int)

df = df.sort_values("Date", kind="stable").reset_index(drop=True)

records = df.to_dict(orient="records")

print(f"Writing {len(records)} records to {DATA_FILE}...")
with open(DATA_FILE, "w", encoding="utf-8") as f:
    json.dump(records, f, indent=2)
    f.write("\n")

print("data.json updated successfully.")
