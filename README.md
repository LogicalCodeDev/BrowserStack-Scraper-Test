# BrowserStack-Scraper-Test
Assesment Task Repo

## 📌 Project Overview
This project was developed as part of a technical assessment from BrowserStack to demonstrate practical skills in web scraping, API integration, text processing, and cross-browser automation using Selenium.

The script visits [El País](https://elpais.com/) and navigates to the [Opinion section](https://elpais.com/opinion/).It extracts the first five articles in Spanish, captures the title, the first 500 characters of content, and downloads the cover image when available.

The article titles are translated into English using a translation API. After translation, a word frequency analysis is performed to identify repeated words across all translated headers.

The solution is executed both locally and on BrowserStack across multiple parallel desktop and mobile browsers to validate cross-browser compatibility and parallel test execution.



## 📂 Project Structure

```bash
BrowserStack-Scraper-Test/
│
├── elpais_test.py
├── requirements.txt
├── .env       
├── images/                 # auto-created (debug HTML snapshots)
└── README.md
```

## 🧠 Tech Stack

### 🔹 Automation & Testing
- **Selenium WebDriver** — Browser automation framework  
- **BrowserStack** — Cloud-based cross-browser testing platform  

### 🔹 Web Scraping
- **Requests** — HTTP requests handling  
- **BeautifulSoup4** — HTML parsing and DOM traversal  

### 🔹 Translation & Text Processing
- **deep-translator** — Title translation to English  
- **Python (re, collections)** — Text cleaning and word frequency analysis  

### 🔹 Driver & Environment Management
- **webdriver-manager** — Automatic ChromeDriver management  


### 🔹 Execution Environments
- BrowserStack Cloud (Desktop + Mobile parallel execution)


## 🚀 Get Started

Follow the steps below to set up and run the project locally and on BrowserStack.

---

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/LogicalCodeDev/BrowserStack-Scraper-Test.git
cd BrowserStack-Scraper-Test
```

---

### 2️⃣ Create a Virtual Environment (Recommended)

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

---

### 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

---

### 4️⃣ Configure BrowserStack Credentials

Open the `.env` file and replace:

```bash
BROWSERSTACK_USERNAME= YOUR_USERNAME
BROWSERSTACK_ACCESS_KEY= YOUR_ACCESS_KEY
BROWSERSTACK_PROJECT_NAME=El Pais Scraper
BROWSERSTACK_BUILD_NAME=Build 1.0
```

with your actual BrowserStack credentials.

⚠️ Do not commit real credentials to public repositories.

---

### 5️⃣ Run Locally (Without BrowserStack)

To verify scraping and translation locally:

```bash
python elpais_test.py
```

This will:

- Visit El País
- Scrape 5 Opinion articles
- Extract title and first 500 characters
- Download cover images (if available)
- Translate titles to English
- Perform repeated word analysis
- Run tests across multiple desktop and mobile browsers
- Execute in parallel threads
- Generate a build under your BrowserStack dashboard

---

### 7️⃣ Verify Results

After execution:

- Check console logs for:
  - Spanish titles
  - English translations
  - Word frequency analysis
- Check `images/` folder for downloaded article images
- Check BrowserStack dashboard for cloud execution results

---

## 🧪 What This Project Demonstrates

- Dynamic DOM scraping using Selenium
- API-based translation
- Text preprocessing and frequency analysis
- Image extraction
- Parallel cross-browser cloud execution
- Real-device mobile testing

