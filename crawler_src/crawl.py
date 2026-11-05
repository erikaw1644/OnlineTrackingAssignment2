import csv
from playwright.sync_api import sync_playwright
import argparse
from tld import get_fld
from pathlib import Path
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import Error as PlaywrightError
import json
import re
from urllib.parse import urlparse

WAIT_AFTER_PAGE_LOAD_MS = 10_000
WAIT_AFTER_CONSENT_MS = 5_000
WAIT_AFTER_SCROLL_MS = 5_000
MAX_SCROLL_STEPS = 40
PAUSE_BETWEEN_SCROLL_STEPS_MS = 500

BLOCKED_CATEGORIES = ["Advertising", "Analytics", "Social", "FingerprintingInvasive", "FingerprintingGeneral"]
DISCONNECT_SERVICES_PATH = Path(__file__).resolve().parent / "disconnect" / "services.json"

CONSENT_ACCEPT_KEYWORDS = [
    # English
    "accept", "accept all", "accept all cookies", "accept cookies", "allow all", "allow all cookies",
    "allow cookies", "i accept", "i agree", "agree", "agree and close", "accept and close",
    "accept and continue", "ok", "okay", "got it", "yes, i agree", "consent", "allow",
    "accept recommended settings",
    # Dutch
    "accepteren", "alles accepteren", "alle cookies accepteren", "cookies accepteren", "accepteer",
    "accepteer alle cookies", "accepteer cookies", "akkoord", "ik ga akkoord", "alle cookies toestaan",
    "alles toestaan", "toestaan", "ja, ik ga akkoord", "akkoord en doorgaan",
]
CLICKABLE_ELEMENTS = "button, a, [role='button'], input[type='button'], input[type='submit']"


#-------------------------------------
#        HAR-helpers 
#-------------------------------------

# get all entries that were not blocked (status != 0)
def get_valid_entries(har):
    valid = []
    for entry in har['log']['entries']:
        if entry['response']['status'] <= 0:
            continue
        if entry['response'].get('redirectURL', '').startswith('chrome-extension://'):
            continue
        valid.append(entry)
    return valid

# get number of requests per website
def get_number_of_requests(valid):
    return len(valid)

def get_domain(page_url):
    return get_fld(page_url, fail_silently=True)

# given page_url and request_url check if third party access
def is_third_party(page_url, request_url):
    request_domain = get_domain(request_url)
    if request_domain is None:
        return False
    return get_domain(page_url) != request_domain

def get_number_of_third_party_requests(valid_entries, page_url):
    count = 0
    for entry in valid_entries:
        if is_third_party(page_url, entry['request']['url']):
            count +=1
    return count

# get length of list with all third pary hostnames
def num_of_distinct_third_party_domains(valid_entries, page_url):
    tp_domains = set()
    for entry in valid_entries:
        req_url = entry ['request']['url']
        if is_third_party(page_url, req_url):
            tp_domains.add(get_fld(req_url))
    return len(tp_domains)


#-------------------------------------
#        Crawl-helpers
#-------------------------------------

CRAWL_MODES = ["desktop", "mobile", "block", "ignore"]

# Reads the flags -m and -l from the command line
def arg_parser():
    parser = argparse.ArgumentParser()  # Initiates a parser
    
    # Adds the 2 possible arguments found in the command line
    parser.add_argument("-m", "--mode", required = True, choices = CRAWL_MODES)
    parser.add_argument("-l", "--list", required = True)

    args = parser.parse_args() # The arguments from the command line
    
    return args

# Reads the csv-file, returning a list of tuples
def read_site_list(site_files):
    sites = []
    
    with open(site_files, newline="") as file:
        for row in csv.reader(file):
            if not row:
                continue
            if len(row) < 2 or row[0].strip() == "domain":
                continue
            domain = row[0].strip()
            country = row[1].strip()
            sites.append((domain, country))         # Appends a tuple (domain, country) to the list sites
    return sites

# functions to know which websites is crawled already
def get_crawled_site_file(output_dir):
    crawled_sites_file = output_dir / "crawled_sites.txt"
    return crawled_sites_file

def load_crawled_domains(output_dir):
    crawled_sites_file = get_crawled_site_file(output_dir)
    
    if not crawled_sites_file.exists():
        return set()
    
    crawled_domains = set()
    with open(crawled_sites_file, encoding="utf-8") as file:
        for line in file:
            domain = line.strip() # remove the newline and any spaces
            if domain == "": # skip empty lines
                continue
            crawled_domains.add(domain)

    return crawled_domains

def mark_domain_as_crawled(output_dir, domain):
    with open(get_crawled_site_file(output_dir), "a", encoding = "utf-8") as crawled_sites_file:
        crawled_sites_file.write(domain + "\n")


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


# Reads the json file from Disconnect, returns a set of blocked domains
def load_blocked(services_json_path):
    with open(services_json_path, "r", encoding="utf-8") as file:
        services = json.load(file)
    blocked_domains = set()
    for category in BLOCKED_CATEGORIES:
        for entity in services["categories"].get(category, []):     # e.g. {"Google": {...}}
            for entity_info in entity.values():                     # e.g. {"http://google.com/": [domains]}
                for value in entity_info.values():
                    if isinstance(value, list):                     # skip extras like "session-replay": "true"
                        blocked_domains.update(domain.lower() for domain in value)

    return blocked_domains#returns the list of blocked domains from disconnect/services.json

#True if the hostname or one of its parent domains is blocked (stats.g.doubleclick.net -> doubleclick.net)
def is_blocked_hostname(hostname, blocked_domains):
    parts = hostname.lower().split(".")
    for i in range(len(parts) - 1):
        if ".".join(parts[i:]) in blocked_domains:
            return True
    return False

# Ignores blocked requests
def request_blocker(context, blocked_domains):
    def handle_request(route):
        hostname = urlparse(route.request.url).hostname or ""
        if is_blocked_hostname(hostname, blocked_domains):
            route.abort("blockedbyclient")
        else:
            route.continue_()
 
    context.route("**/*", handle_request)

# Creates a fresh browser context that records a HAR file and a video
def create_browser_context(p, browser, mode, har_path, video_dir):
    context_options = {
        "record_har_path": str(har_path),
        "record_har_content": "omit",   # we only need headers, not page contents
        "record_video_dir": str(video_dir),
    }
    if mode == "mobile":
        pixel_10 = dict(p.devices["Pixel 10"])   # user agent, screen size, touch, ...
        pixel_10.pop("default_browser_type")      # new_context doesn't accept this key
        context_options.update(pixel_10)
    else:
        context_options["viewport"] = {"width": 1280, "height": 800}
    return browser.new_context(**context_options)

def accept_cookies(page):
    keyword_pattern = "|".join(re.escape(keyword) for keyword in CONSENT_ACCEPT_KEYWORDS)
    accept_text = re.compile(rf"^\s*({keyword_pattern})\s*[.!]?\s*$", re.IGNORECASE)
 
    for frame in page.frames:                      # main page + all iframes
        try:
            elements = frame.locator(CLICKABLE_ELEMENTS)
            for i in range(elements.count()):
                element = elements.nth(i)
                text = element.inner_text(timeout=1000) or element.get_attribute("value", timeout=1000) or ""
                if accept_text.match(text) and element.is_visible():
                    element.click(timeout=3000)
                    print(f"  Clicked consent button: {text.strip()!r}")
                    return True
        except PlaywrightError:
            continue                               # frame disappeared or element changed: try the next frame
    print("  No consent button found")
    return False

def accept_cookies(page):
    keyword_pattern = "|".join(re.escape(keyword) for keyword in CONSENT_ACCEPT_KEYWORDS)
    accept_text = re.compile(rf"^\s*({keyword_pattern})\s*[.!]?\s*$", re.IGNORECASE)
 
    for frame in page.frames:                      # main page + all iframes
        try:
            elements = frame.locator(CLICKABLE_ELEMENTS)
            for i in range(elements.count()):
                element = elements.nth(i)
                text = element.inner_text(timeout=1000) or element.get_attribute("value", timeout=1000) or ""
                if accept_text.match(text) and element.is_visible():
                    element.click(timeout=3000)
                    print(f"  Clicked consent button: {text.strip()!r}")
                    return True
        except PlaywrightError:
            continue                               # frame disappeared or element changed: try the next frame
    print("  No consent button found")
    return False

# Scrolls down one screen at a time until the bottom (or until scrolling is blocked)
def scroll_to_bottom(page):
    for _ in range(MAX_SCROLL_STEPS):
        position_before = page.evaluate("window.scrollY")
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        page.wait_for_timeout(PAUSE_BETWEEN_SCROLL_STEPS_MS)
        position_after = page.evaluate("window.scrollY")
        at_bottom = page.evaluate(
            "window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2")
        if at_bottom or position_after == position_before:
            break

def take_screenshot(page, screenshot_path):
    page.screenshot(path=str(screenshot_path))

# Visits one website: load -> wait 10s -> screenshot -> accept -> wait 5s -> screenshot -> scroll -> wait 5s -> close
def visit_site(p, browser, domain, mode, output_dir, blocked_domains):
    har_path = output_dir / f"{domain}.har"
    video_dir = output_dir / "videos_tmp"
    context = create_browser_context(p, browser, mode, har_path, video_dir)
    if mode == "block":
        request_blocker(context, blocked_domains)
    page = context.new_page()
    try:
        load_homepage(page, domain)
        page.wait_for_timeout(WAIT_AFTER_PAGE_LOAD_MS)
        take_screenshot(page, output_dir / f"{domain}_pre_consent.png")

        if mode != "ignore":
            accept_cookies(page)
            page.wait_for_timeout(WAIT_AFTER_CONSENT_MS)
            take_screenshot(page, output_dir / f"{domain}_post_consent.png")

        scroll_to_bottom(page)
        page.wait_for_timeout(WAIT_AFTER_SCROLL_MS)
    finally:
        context.close()                                         # writes the HAR, finishes the video
        page.video.save_as(output_dir / f"{domain}.webm")       # save under the domain name
        page.video.delete()                                     # remove Playwright's randomly named copy

def main():
    args = arg_parser()
    output_dir = Path(f"crawl_data_{args.mode}")
    output_dir.mkdir(exist_ok=True)

    sites = read_site_list(args.list)
    crawled_domains = load_crawled_domains(output_dir)

    blocked_domains = set()
    if args.mode == "block":
        blocked_domains = load_blocked(DISCONNECT_SERVICES_PATH)
        print(f"Loaded {len(blocked_domains)} blocked domains from Disconnect")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)               # one browser for the whole crawl
        for domain, country in sites:
            if domain in crawled_domains:
                print(f"Skipping {domain} as it has already been crawled.")
                continue
            print(f"Crawling {domain} in mode {args.mode}...")
            try:
                visit_site(p, browser, domain, args.mode, output_dir, blocked_domains)
                mark_domain_as_crawled(output_dir, domain)   # only after a successful visit
            except Exception as error:
                print(f"  Failed to crawl {domain}: {error}")
        browser.close()
    return

if __name__ == "__main__":
    main()