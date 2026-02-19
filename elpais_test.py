import json
import os
import re
import time
import requests
import urllib.parse

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from deep_translator import GoogleTranslator 

IMAGES_DIR = "images"
os.makedirs(IMAGES_DIR, exist_ok=True)

USE_BROWSERSTACK = True
REQUESTS_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; bot/0.1)"} 

OPINION_URL = "https://elpais.com/opinion/"
DATE_PATTERN = re.compile(r'/opinion/\d{4}-\d{2}-\d{2}/')  

def translate_text(text, source="auto", target="en"):

    if not text:
        return ""
    try:
        translated = GoogleTranslator(source=source, target=target).translate(text)
        return translated if translated else text
    except Exception as e:
        print(f"Translation failed (deep-translator): {e} -- returning original text")
        return text

def download_image(url, filename):
    try:
        headers = REQUESTS_HEADERS
        response = requests.get(url, stream=True, timeout=12, headers=headers)
        response.raise_for_status()
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        print(f"Image saved: {filename}")
    except Exception as e:
        print(f"Failed to download {url}: {e}")

def analyze_word_frequency(headers):
    all_words = []
    for header in headers:
        words = re.findall(r'\w+', (header or "").lower())
        all_words.extend(words)
    freq = {}
    for word in all_words:
        freq[word] = freq.get(word, 0) + 1
    repeated = {word: count for word, count in freq.items() if count > 2}
    return repeated

def fetch_static_html(url):
    """Attempt to fetch page HTML with requests as a fast primary method."""
    try:
        r = requests.get(url, headers=REQUESTS_HEADERS, timeout=10)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"requests fetch failed for {url}: {e}")
        return None

def extract_article_urls_from_soup(soup, max_urls=5):
    """Extract first N opinion article URLs from the index page."""
    urls = []
    seen = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        full = href if href.startswith('http') else urllib.parse.urljoin(OPINION_URL, href)
        if DATE_PATTERN.search(full) and full not in seen:
            # normalize by removing query params/trailing fragments
            normalized = urllib.parse.urljoin(full, urllib.parse.urlparse(full).path)
            if normalized not in seen:
                urls.append(normalized)
                seen.add(normalized)
                if len(urls) >= max_urls:
                    return urls
    return urls

def extract_title_from_article_html(html):
    """Robust title extraction from an article HTML fragment (meta og:title, h1, document.title). (CHANGED)"""
    if not html:
        return ""
    soup = BeautifulSoup(html, 'html.parser')

    # 1) meta og:title or twitter:title
    meta = soup.select_one("meta[property='og:title'], meta[name='twitter:title']")
    if meta and meta.get("content"):
        return meta.get("content").strip()

    # 2) h1 inside article or document
    h1 = soup.select_one("article h1, h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)

    # 3) JSON-LD (ld+json) may contain headline
    try:
        for script in soup.select("script[type='application/ld+json']"):
            try:
                data = json.loads(script.string or "{}")
                # data might be a list or dict
                if isinstance(data, list):
                    for v in data:
                        if isinstance(v, dict) and v.get("headline"):
                            return v.get("headline").strip()
                elif isinstance(data, dict):
                    if data.get("headline"):
                        return data.get("headline").strip()
                    if isinstance(data.get("mainEntityOfPage"), dict) and data["mainEntityOfPage"].get("headline"):
                        return data["mainEntityOfPage"]["headline"].strip()
            except Exception:
                continue
    except Exception:
        pass

    # 4) document.title fallback
    title_tag = soup.title
    if title_tag and title_tag.string:
        return title_tag.string.strip()

    return ""

def extract_article_content(html, max_chars=500):
    """Extract body text from article HTML and return first max_chars characters."""
    if not html:
        return ""
    soup = BeautifulSoup(html, 'html.parser')

    # Prefer <article> container
    article = soup.find('article')
    text = ""
    if article:
        paragraphs = article.find_all('p')
        text = " ".join(p.get_text(separator=" ", strip=True) for p in paragraphs)
    else:
        selectors = [
            "div[itemprop='articleBody']",
            "div[class*='article']",
            "main"
        ]
        for sel in selectors:
            node = soup.select_one(sel)
            if node:
                text = node.get_text(separator=" ", strip=True)
                if text:
                    break

    text = re.sub(r'\s+', ' ', (text or "")).strip()
    return text[:max_chars]

def run_test():
    if USE_BROWSERSTACK:
        options = ChromeOptions()
        options.set_capability('sessionName', 'El Pais Opinion Test')
        driver = webdriver.Remote(
            command_executor='http://localhost:4444/wd/hub',
            options=options
        )
    else:
        chrome_opts = ChromeOptions()
        chrome_opts.add_argument("--disable-gpu")
        chrome_opts.add_argument("--no-sandbox")
        chrome_opts.add_argument("--lang=es-ES")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_opts)

    try:
        driver.get("https://elpais.com/")
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        print("Landed on:", driver.current_url)

        for _ in range(2):
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
            except Exception:
                break

        print("\nAttempting to collect first 5 opinion article URLs from index:", OPINION_URL)

        # 1) Fast attempt: requests -> BeautifulSoup
        article_urls = []
        index_html = fetch_static_html(OPINION_URL)
        if index_html:
            soup = BeautifulSoup(index_html, 'html.parser')
            article_urls = extract_article_urls_from_soup(soup, max_urls=5)
            print("Found via requests:", len(article_urls))
        else:
            print("Requests for index failed or returned nothing.")

        # 2) Fallback: render with the driver (will use BrowserStack Remote if enabled)
        if len(article_urls) < 5:
            print(f"Falling back to driver rendering (found {len(article_urls)} via requests)...")
            driver.get(OPINION_URL)
            WebDriverWait(driver, 12).until(EC.presence_of_all_elements_located((By.TAG_NAME, "a")))
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                time.sleep(0.8)
            except Exception:
                pass
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            article_urls = extract_article_urls_from_soup(soup, max_urls=5)
            print("Found via driver:", len(article_urls))

        if not article_urls:
            print("No article URLs found on the opinion index. Exiting.")
            if USE_BROWSERSTACK:
                try:
                    driver.execute_script(
                        'browserstack_executor: {"action": "setSessionStatus", "arguments": {"status":"failed", "reason": "No article URLs found"}}'
                    )
                except Exception:
                    pass
            return

        print("\n--- Collected Article URLs ---")
        for i, u in enumerate(article_urls, 1):
            print(f"{i}. {u}")

        print("\n--- Extracting title + first 500 chars of content for each article ---")
        results = []
        for idx, url in enumerate(article_urls, 1):
            print(f"\nProcessing article {idx}: {url}")

            article_html = fetch_static_html(url)

            if not article_html or ("<article" not in article_html.lower() and len(article_html or "") < 2000):
                try:
                    driver.get(url)
                    WebDriverWait(driver, 12).until(EC.presence_of_element_located((By.TAG_NAME, "article")))
                    article_html = driver.page_source
                except TimeoutException:
                    print("Timed out waiting for article to load via driver; proceeding with best-effort content.")

            # Extract title and content
            title = extract_title_from_article_html(article_html)
            content_500 = extract_article_content(article_html, max_chars=500)

            if not title:
                try:
                    with open(os.path.join(IMAGES_DIR, f"debug_title_missing_{idx}.html"), "w", encoding="utf-8") as fh:
                        fh.write((article_html or "")[:400000])
                except Exception:
                    pass
            if not content_500:
                try:
                    with open(os.path.join(IMAGES_DIR, f"debug_content_missing_{idx}.html"), "w", encoding="utf-8") as fh:
                        fh.write((article_html or "")[:400000])
                except Exception:
                    pass

            print(f"Title: {title if title else '[NO TITLE FOUND]'}")
            print(f"Content (first 500 chars):\n{content_500 if content_500 else '[NO CONTENT FOUND]'}")

            results.append({
                "url": url,
                "title": title,
                "content_500": content_500
            })

        print("\n--- Translated Titles (English) ---")
        translated_headers = []
        for i, r in enumerate(results, 1):
            original = r["title"] or ""
            translated = translate_text(original) if original else ""
            translated_headers.append(translated)
            print(f"{i}. {translated}")

        print("\n--- Words repeated more than twice ---")
        word_freq = analyze_word_frequency(translated_headers)
        if word_freq:
            for word, count in word_freq.items():
                print(f"{word}: {count}")
        else:
            print("No words repeated more than twice.")

        if USE_BROWSERSTACK:
            try:
                driver.execute_script(
                    'browserstack_executor: {"action": "setSessionStatus", "arguments": {"status":"passed", "reason": "Extracted titles and content (500 chars)"}}'
                )
            except Exception:
                pass

    except Exception as err:
        message = f"Exception: {err.__class__.__name__} - {str(err)}"
        print(message)
        if USE_BROWSERSTACK:
            try:
                driver.execute_script(
                    'browserstack_executor: {"action": "setSessionStatus", "arguments": {"status":"failed", "reason": ' + json.dumps(message) + '}}'
                )
            except Exception:
                pass
    finally:
        driver.quit()

if __name__ == "__main__":
    run_test()
