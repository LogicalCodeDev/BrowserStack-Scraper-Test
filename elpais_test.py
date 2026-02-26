import json
import os
import re
import time
import requests
import urllib.parse
import logging

from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from deep_translator import GoogleTranslator

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException


# *****************************************************
# CONFIG
# *****************************************************

load_dotenv()

BROWSERSTACK_USERNAME = os.getenv("BROWSERSTACK_USERNAME")
BROWSERSTACK_ACCESS_KEY = os.getenv("BROWSERSTACK_ACCESS_KEY")
BROWSERSTACK_PROJECT_NAME = os.getenv("BROWSERSTACK_PROJECT_NAME", "El Pais Scraper")
BROWSERSTACK_BUILD_NAME   = os.getenv("BROWSERSTACK_BUILD_NAME", "Build 1.0")

# Directories & logging
IMAGES_DIR = "images"
os.makedirs(IMAGES_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] - %(levelname)s - %(message)s"
)

REQUESTS_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; bot/0.1)"}
OPINION_URL      = "https://elpais.com/opinion/"
DATE_PATTERN     = re.compile(r'/opinion/\d{4}-\d{2}-\d{2}/')
STOPWORDS = {
    "the", "a", "an", "in", "on", "of", "and", "to", "for",
    "is", "it", "its", "at", "by", "or", "that", "this",
    "with", "from", "as", "are", "be", "was", "but", "not"
}


# *****************************************************
# BROWSER FACTORY 
# *****************************************************

class BrowserFactory:

    @staticmethod
    def create_local():
        try:
            return BrowserFactory._create_edge()
        except WebDriverException:
            return BrowserFactory._create_chrome()

    @staticmethod
    def _create_chrome():
        logging.info("Launching Chrome...")
        options = ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--start-maximized")
        return webdriver.Chrome(options=options)

    @staticmethod
    def _create_edge():
        logging.info("Launching Edge...")
        options = EdgeOptions()
        options.use_chromium = True
        options.add_argument("--headless=new")
        options.add_argument("--start-maximized")
        return webdriver.Edge(options=options)

    @staticmethod
    def create_browserstack(capability):
        logging.info(f"Launching BrowserStack session: {capability.get('name')}")
        print(capability.get("name"))
        bstack_options = {
            "sessionName": capability.get("name"),
            "userName":    BROWSERSTACK_USERNAME,
            "accessKey":   BROWSERSTACK_ACCESS_KEY,
            "consoleLogs": "info",
            "projectName": BROWSERSTACK_PROJECT_NAME,  
            "buildName":   BROWSERSTACK_BUILD_NAME,    
            "networkLogs": True,
        }

        # Desktop vs Mobile
        if capability.get("os"):
            bstack_options["os"]        = capability["os"]
            bstack_options["osVersion"] = capability["osVersion"]
        else:
            bstack_options["deviceName"]  = capability["deviceName"]
            bstack_options["osVersion"]   = capability["osVersion"]
            bstack_options["realMobile"]  = "true"

        browser_name = capability.get("browserName", "Chrome")

        # Safari needs its own options class
        if browser_name.lower() == "safari":
            options = webdriver.SafariOptions()
        else:
            options = ChromeOptions()

        options.set_capability("browserName", browser_name)

        if capability.get("browserVersion"):
            options.set_capability("browserVersion", capability["browserVersion"])

        options.set_capability("bstack:options", bstack_options)

        driver = webdriver.Remote(
            command_executor="https://hub-cloud.browserstack.com/wd/hub",
            options=options
        )

        logging.info(f"Session ID: {driver.session_id}")
        return driver


# *****************************************************
# SCRAPING UTILITIES 
# *****************************************************

def translate_text(text, source="auto", target="en"):
    if not text:
        return ""
    try:
        translated = GoogleTranslator(source=source, target=target).translate(text)
        return translated if translated else text
    except Exception as e:
        logging.warning(f"Translation failed: {e}")
        return text


def download_image(url, filename):
    try:
        r = requests.get(url, stream=True, timeout=12, headers=REQUESTS_HEADERS)
        r.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)
        logging.info(f"Image saved: {filename}")
    except Exception as e:
        logging.warning(f"Failed to download {url}: {e}")


def accept_cookies(driver):
    try:
        btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Aceptar')]"))
        )
        btn.click()
        logging.info("Cookie banner accepted.")
    except Exception:
        logging.info("No cookie banner found.")


def fetch_static_html(url):
    try:
        r = requests.get(url, headers=REQUESTS_HEADERS, timeout=10)
        r.raise_for_status()
        return r.text
    except Exception as e:
        logging.warning(f"requests fetch failed for {url}: {e}")
        return None


def extract_article_urls_from_soup(soup, max_urls=5):
    urls, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = href if href.startswith("http") else urllib.parse.urljoin(OPINION_URL, href)
        if DATE_PATTERN.search(full) and full not in seen:
            normalized = urllib.parse.urljoin(full, urllib.parse.urlparse(full).path)
            if normalized not in seen:
                urls.append(normalized)
                seen.add(normalized)
                if len(urls) >= max_urls:
                    return urls
    return urls


def extract_title_from_article_html(html):
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.select_one("meta[property='og:title']")
    return meta.get("content", "").strip() if meta else ""


def extract_article_content(html, max_chars=500):
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find("article")
    if not article:
        return ""
    paragraphs = article.find_all("p")
    text = " ".join(p.get_text(separator=" ", strip=True) for p in paragraphs)
    return text[:max_chars]


def extract_image_url_from_article(html):
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.select_one("meta[property='og:image']")
    return meta.get("content", "").strip() if meta else None


def analyze_word_frequency(headers):
    freq = {}
    for header in headers:
        words = [
            w.strip("',.-!?\"")
            for w in (header or "").lower().split()
            if w.strip("',.-!?\"") not in STOPWORDS
        ]
        for word in words:
            freq[word] = freq.get(word, 0) + 1
    return {w: c for w, c in freq.items() if c > 2}


# *****************************************************
# CORE TEST LOGIC  
# *****************************************************

def run_test(driver=None, session_label="local", bs_config=None):
    """
    Execute the full scrape-and-translate flow.

    Parameters
    ----------
    driver        : pre-built WebDriver (BrowserStack) or None (local Chrome)
    session_label : human-readable name for log messages
    bs_config     : full BrowserStack config dict (used to mark session pass/fail)
    """
    use_bs     = bs_config is not None
    own_driver = driver is None

    if own_driver:
        driver = BrowserFactory.create_local()

    def _bs_status(status, reason):
        if use_bs:
            try:
                driver.execute_script(
                    "browserstack_executor: "
                    + json.dumps({"action": "setSessionStatus",
                                  "arguments": {"status": status, "reason": reason}})
                )
            except Exception:
                pass

    try:
        driver.get("https://elpais.com/")
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        accept_cookies(driver)
        logging.info(f"[{session_label}] Landed on: {driver.current_url}")

        for _ in range(2):
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
            except Exception:
                break

        # ── Collect article URLs ─────────────────────────────────────────────
        article_urls = []
        index_html = fetch_static_html(OPINION_URL)
        if index_html:
            soup = BeautifulSoup(index_html, "html.parser")
            article_urls = extract_article_urls_from_soup(soup, max_urls=5)
            logging.info(f"[{session_label}] Found via requests: {len(article_urls)}")

        if len(article_urls) < 5:
            logging.info(f"[{session_label}] Falling back to driver rendering…")
            driver.get(OPINION_URL)
            WebDriverWait(driver, 12).until(
                EC.presence_of_all_elements_located((By.TAG_NAME, "a"))
            )
            accept_cookies(driver)
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                time.sleep(0.8)
            except Exception:
                pass
            soup = BeautifulSoup(driver.page_source, "html.parser")
            article_urls = extract_article_urls_from_soup(soup, max_urls=5)
            logging.info(f"[{session_label}] Found via driver: {len(article_urls)}")

        if not article_urls:
            logging.warning(f"[{session_label}] No article URLs found. Exiting.")
            _bs_status("failed", "No article URLs found")
            return

        # ── Extract content from each article ────────────────────────────────
        results = []
        for idx, url in enumerate(article_urls, 1):
            logging.info(f"[{session_label}] Processing article {idx}: {url}")

            article_html = fetch_static_html(url)
            if not article_html or (
                "<article" not in article_html.lower() and len(article_html) < 2000
            ):
                try:
                    driver.get(url)
                    WebDriverWait(driver, 12).until(
                        EC.presence_of_element_located((By.TAG_NAME, "article"))
                    )
                    accept_cookies(driver)
                    article_html = driver.page_source
                except TimeoutException:
                    logging.warning(
                        f"[{session_label}] Timed out waiting for article {idx}; "
                        "proceeding with best-effort content."
                    )

            title       = extract_title_from_article_html(article_html)
            content_500 = extract_article_content(article_html, max_chars=500)
            image_url   = extract_image_url_from_article(article_html)

            if image_url:
                safe_label  = re.sub(r"[^a-zA-Z0-9_-]", "_", session_label)[:30]
                image_fname = os.path.join(IMAGES_DIR, f"{safe_label}_article_{idx}.jpg")
                download_image(image_url, image_fname)

            logging.warning(f"[{session_label}] Title: {title or '[NO TITLE FOUND]'}")
            logging.warning(
                f"[{session_label}] Content (first 500 chars):\n"
                f"{content_500 or '[NO CONTENT FOUND]'}"
            )
            results.append({"url": url, "title": title, "content_500": content_500})

        # ── Translate titles & word-frequency analysis ───────────────────────
        logging.info(f"[{session_label}] --- Translated Titles (English) ---")
        translated_headers = []
        for i, r in enumerate(results, 1):
            translated = translate_text(r["title"]) if r["title"] else ""
            translated_headers.append(translated)
            logging.info(f"[{session_label}] {i}. {translated}")

        logging.info(f"[{session_label}] --- Words repeated more than twice ---")
        word_freq = analyze_word_frequency(translated_headers)
        if word_freq:
            for word, count in word_freq.items():
                logging.info(f"[{session_label}]   {word}: {count}")
        else:
            logging.info(f"[{session_label}] No words repeated more than twice.")

        _bs_status("passed", "Extracted titles and content (500 chars)")

    except Exception as err:
        msg = f"{err.__class__.__name__}: {err}"
        logging.warning(f"[{session_label}] Exception → {msg}")
        _bs_status("failed", msg)

    finally:
        if own_driver:
            driver.quit()
            logging.info(f"[{session_label}] Local browser closed.")
        elif use_bs:
            driver.quit()
            logging.info(f"[{session_label}] BrowserStack session closed.")


def run_local():
    logging.info("=" * 50)
    logging.info("Running Locally...")
    logging.info("=" * 50)
    run_test(session_label="local")


def run_browserstack(capability):
    """Run a single BrowserStack session for the given capability dict."""
    session_name = capability.get("name", "BrowserStack Project")
    driver = None
    try:
        driver = BrowserFactory.create_browserstack(capability)
        logging.info(f"[{session_name}] Running scrape...")
        run_test(driver=driver, session_label=session_name, bs_config=capability)

    except Exception as e:
        logging.error(f"[{session_name}] Failed: {e}")
        if driver:
            driver.execute_script(
                f'browserstack_executor: {{"action": "setSessionStatus", "arguments": '
                f'{{"status": "failed", "reason": "{str(e)[:100]}"}}}}'
            )
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
            logging.info(f"[{session_name}] Browser closed.")


def run_parallel_browserstack():
    logging.info("=" * 50)
    logging.info("Running on BrowserStack (5 parallel threads)...")
    logging.info("=" * 50)

    capabilities = [
        #desktop
        {
            "browserName":    "Chrome",
            "browserVersion": "latest",
            "os":             "Windows",
            "osVersion":      "11",
            "name":           "Chrome on Windows 11",
        },
        {
            "browserName":    "Edge",
            "browserVersion": "latest",
            "os":             "Windows",
            "osVersion":      "10",
            "name":           "Edge on Windows 10",
        },
        {
            "browserName":    "Safari",
            "browserVersion": "17",
            "os":             "OS X",
            "osVersion":      "Sonoma",
            "name":           "Safari on macOS Sonoma",
        },
        #mobile 
        {
            "browserName": "Chrome",
            "deviceName":  "Samsung Galaxy S23",
            "osVersion":   "13.0",
            "name":        "Chrome on Samsung Galaxy S23",
        },
        {
            "browserName": "Safari",
            "deviceName":  "iPhone 15",
            "osVersion":   "17",
            "name":        "Safari on iPhone 15",
        },
    ]

    with ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(run_browserstack, capabilities)


# main

if __name__ == "__main__":
    #  run locally first to verify
    run_local()

    # run on BrowserStack if credentials are set
    if BROWSERSTACK_USERNAME and BROWSERSTACK_ACCESS_KEY:
        run_parallel_browserstack()
    else:
        logging.warning(
            "BrowserStack credentials not found in .env. "
            "Set BROWSERSTACK_USERNAME and BROWSERSTACK_ACCESS_KEY to run cloud tests."
        )