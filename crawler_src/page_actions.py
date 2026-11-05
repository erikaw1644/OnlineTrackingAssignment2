from playwright.sync_api import Error as PlaywrightError
from pathlib import Path

PRIV_ACCEPT_WORDS_PATH = Path(__file__).resolve().parent / "accept_words.txt"

# Priv-accept's list has no Dutch keywords, we add them here
DUTCH_ACCEPT_KEYWORDS = [
    "accepteren", "alles accepteren", "alle cookies accepteren", "cookies accepteren", "accepteer",
    "accepteer alle cookies", "accepteer cookies", "akkoord", "ik ga akkoord", "alle cookies toestaan",
    "alles toestaan", "toestaan", "ja, ik ga akkoord", "akkoord en doorgaan",
]

# Elements priv-accept clicks: buttons, links and spans
CLICKABLE_ELEMENTS = "button, a, span"


# Tries https://domain first, then https://www.domain if nothing loaded.
def load_homepage(page, domain):
    candidate_urls = [f"https://{domain}"]
    if not domain.startswith("www."):
        candidate_urls.append(f"https://www.{domain}")

    for url in candidate_urls:
        try:
            page.goto(url, wait_until="load", timeout=60_000)
            return
        except PlaywrightError as error:
            if page_has_loaded_something(page):
                print(f"  {url} loaded slowly, continuing anyway")
                return
            print(f"  Could not load {url}: {error.message.splitlines()[0]}")
    raise RuntimeError(f"Could not load {domain}")


# True if the page shows a real website (not about:blank or a Chrome error page)
def page_has_loaded_something(page):
    if not page.url.startswith("http"):
        return False
    try:
        return page.evaluate("document.body !== null && document.body.innerHTML.length > 0")
    except PlaywrightError:
        return False


# remove leading/trailing/repeated spaces and ignore upper/lower case
def normalize_text(text):
    return " ".join(text.split()).lower()


# priv-accept's keywords (one per line) + our Dutch keywords
def load_accept_keywords(priv_accept_words_path):
    accept_keywords = set()
    with open(priv_accept_words_path, encoding="utf-8") as words_file:
        for line in words_file:
            keyword = normalize_text(line)
            if keyword:
                accept_keywords.add(keyword)
    for keyword in DUTCH_ACCEPT_KEYWORDS:
        accept_keywords.add(normalize_text(keyword))
    return accept_keywords


ACCEPT_KEYWORDS = load_accept_keywords(PRIV_ACCEPT_WORDS_PATH)

# Clicks the first visible button/link/span whose whole text exactly matches a keyword,
# searching the main page and all iframes. Returns True if something was clicked.
def accept_cookies(page):
    for frame in page.frames:
        try:
            elements = frame.locator(CLICKABLE_ELEMENTS)
            element_texts = elements.all_inner_texts()        # all texts in one call (fast)
            for element_index, element_text in enumerate(element_texts):
                if normalize_text(element_text) not in ACCEPT_KEYWORDS:
                    continue
                element = elements.nth(element_index)
                if not element.is_visible():
                    continue
                element.click(timeout=3000)
                print(f"  Clicked consent button: {element_text.strip()!r}")
                return True
        except PlaywrightError:
            continue  # if the frame disappeared: try the next one

    print("  No consent button found")
    return False


# scrolls to the bottom of the page in steps as a bot detection mitigation measure
def scroll_to_bottom(page):
    for step in range(7):
        page.evaluate(f"window.scrollTo({step}*document.body.scrollHeight/7, {step+1}*document.body.scrollHeight/7);")

# takes a screenshot of the page and saves it to the given path
def take_screenshot(page, screenshot_path):
    page.screenshot(path=str(screenshot_path))