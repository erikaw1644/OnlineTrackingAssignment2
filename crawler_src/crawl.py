import csv
from playwright.sync_api import sync_playwright
import argparse
from tld import get_fld
from pathlib import Path
import json
from urllib.parse import urlparse

CRAWL_MODES = ["desktop", "mobile", "block", "ignore"]

OUTPUT_FOLDERS = {
    "desktop": Path("crawl_data_desktop"),
    "mobile": Path("crawl_data_mobile"),
    "block": Path("crawl_data_block"),
    "ignore": Path("crawl_data_ignore")
}

# TODO: Check assignment description for this list
ACCEPT_KEYWORDS = ["accept all", "accept cookies", "allow all", "allow cookies", "i agree", "agree",
                   "accept", "got it", "alles accepteren", "alle cookies accepteren",
                   "accepteer alle", "accepteren", "accepteer", "akkoord", "ik ga akkoord",
                   "toestaan"]

REJECT_KEYWORDS = ["reject", "decline", "refuse", "deny", "disagree", "necessary", "essential", "only",
                   "settings", "manage", "preferences", "customise", "customize",
                   "weiger", "afwijzen", "alleen", "noodzakelijk", "instellingen", "voorkeuren", "beheren"]


# Step 1: Reads the flags -m and -l from the command line
def arg_parser():
    parser = argparse.ArgumentParser()              # Initiates a parser
    
    # Adds the 2 possible arguments found in the command line
    parser.add_argument("-m", "--mode", required=True, choices=CRAWL_MODES)
    parser.add_argument("-l", "--list", required=True)

    args = parser.parse_args()                      # The arguments from the command line
    
    return args                                     # Returns Namespace(mode='desktop/mobile/block/ignore', list='sites.csv')

# Step 2: Reads the sites csv-file, returning a list of tuples
def read_site_list(site_files):
    sites = []
    
    with open(site_files, newline="") as file:
        for row in csv.reader(file):
            if not row:
                continue
            domain = row[0].strip()
            country = row[1].strip()
            sites.append((domain, country))         # Appends a tuple (domainain, country) to the list sites
    
    return sites

# Gets the file with the crawled sites
def get_crawled_site_file(output_dir):
    crawled_site_file = output_dir / "crawled_sites.txt"
    return crawled_site_file

# Loads all already crawled domain
def load_crawled_domain(output_dir):
    crawled_sites_file = get_crawled_site_file(output_dir)
    
    if not crawled_sites_file.exists():
        return set()
    
    crawled_domain = set()
    with open(crawled_sites_file, encoding="utf-8") as file:
        for line in file:
            domainain = line.strip() # remove the newline and any spaces
            if domainain == "": # skip empty lines
                continue
            crawled_domain.add(domainain)

    return crawled_domain

# Appends a domainain that is now crawled to the file with crawled sites
def mark_domainain_as_crawled(output_dir, domainain):
    with open(get_crawled_site_file(output_dir), "a", encoding = "utf-8") as crawled_sites_file:
        crawled_sites_file.write(domainain + "\n")

# Helper function to get the domain
def get_company_domain(info):
    domainain_set = set()                                                                          # Set of domain that belong to the company

    for value in info.values():
        if isinstance(value, list):                                                             # Gets the value that is a list of domain
            for domain in value:
                domainain_set.add(domain.lower())                                                     # Adds each domainain in the list to the set of domain
    
    return domainain_set

# Returns the set of blocked domain from disconnect/services.json
def load_blocked_domain():
    disconnect_path = Path(__file__).parent / "disconnect" / "services.json"                    # Gets the parent folder file path and builds a path to the services.json file

    BLOCKED_CATEGORIES = ["Advertising", "Analytics", "Social", 
                          "FingerprintingInvasive", "FingerprintingGeneral"]                    # All the blocked categories from the task
    
    with open(disconnect_path) as file:
        services = json.load(file)
    
        blocked_domains = set()                                                                    # Uses a set so we do not get any duplicate domain

        for category in BLOCKED_CATEGORIES:                                                     # Iterates through all the blocked categories
            for entry in services["categories"][category]:
                for info in entry.values():
                    current_blocked = get_company_domain(info)
                    blocked_domains.update(current_blocked)


    return blocked_domains

# Helper function to visit_site() and creates context that records a HAR and a video
def create_browser_context(p, browser, mode, har_path, video):
    context_options = {
        "record_har_path": har_path,                                                            # This is the path where we save the HAR file
        "record_video_dir": video                                                               # This is the path where we save the video
    }

    if mode == "mobile":                                                                        # If the mode is mobile, we update the mobile type
        context_options.update(p.devices["Pixel 10"])
    
    return browser.new_context(**context_options)                                               # **context_options unpacks the dictionary into keyword arguments

# Visits one website and saves its HAR and video
def visit_site(p, browser, domain, mode, output_dir, blocked_domain):
    har_path = output_dir / f"{domain}.har"                                                     # Gets the path to the HAR file
    pre_consent_path = output_dir / f"{domain}_pre_consent.png"
    post_consent_path = output_dir / f"{domain}_post_consent.png"

    context = create_browser_context(p, browser, mode, har_path, output_dir)                    # Creates a fresh context for this site visit
    page = context.new_page()                                                                   # Opens a new tab

    if mode == "block":
        context.route("**/*", block_request)
    page = context.new_page()

    page.goto(f"https://{domain}")                                                          # Loads the current site
    page.wait_for_timeout(10_000)                                                               # Waits 10 seconds

    take_screenshot(page, pre_consent_path)

    if mode != "ignore":
        accept_cookies(page)
        page.wait_for_timeout(5_000)
        take_screenshot(page, post_consent_path)

    
    scroll_to_bottom(page)
    page.wait_for_timeout(5_000)

    video_path = page.video.path()
    context.close()                                                                             # Closes this session, writes to the HAR file and finishes the video
    Path(video_path).rename(output_dir / f"{domain}.webm")

# Automatically scrolls down the page like a visitor on the site
def scroll_to_bottom(page, max_steps=40):
    for step in range(max_steps):                                                               # Max steps so that the scroll ends at a certain point for pages with no bottom
        page.evaluate("window.scrollBy(0, 600)")
        page.wait_for_timeout(500)

        # Evaluates to true if we have reached the bottom of the page
        scrolled_to_bottom = page.evaluate(
            "window.scrollY + window.innerHeight >= document.documentElement.scrollHeight"
        )

        if scrolled_to_bottom:
            break

def is_accept_button_text(text):
    text = " ".join(text.lower().split())
    if len(text) > 40:
        return False
    if any(word in text for word in REJECT_KEYWORDS):
        return False
    return any(word in text for word in ACCEPT_KEYWORDS)

def accept_cookies(page):
    for fram in page.frames:
        candidates = fram.locator("button, a, [role='button']")
        for index in range(candidates.count()):
            candidate = candidates.nth(index)
            try:
                if not candidate.is_visible():
                    continue
                if not is_accept_button_text(candidate.inner_text(timeout=1000)):
                    continue
                candidate.click(timeout=3000)
                return True
            except Exception:
                continue
    return False

def is_blocked_hostname(hostname, blocked_domains):
    labels = hostname.lower().split(".")
    
    for start in range(len(labels) - 1):
        if ".".join(labels[start:]) in blocked_domains:
            return True
    
    return False

def block_request(route, blocked_domains):
    hostname = urlparse(route.request.url).hostname

    blocked_domains = load_blocked_domain()

    if hostname and is_blocked_hostname(hostname, blocked_domains):
        route.abort()
    else:
        route.continue_()

def take_screenshot(page, path):
    page.screenshot(path=path)

def main():
    args = arg_parser()                                 # Step 1: Parse the arguments on the command line
    mode = args.mode
    site_file = args.list
    sites = read_site_list(site_file)                   # Step 2: Reads the sites csv file
    
    output_dir = OUTPUT_FOLDERS[mode]                   # Step 3: Picks the output folder of the current mode

    crawled_domain = load_crawled_domain(output_dir)  # Step 4: Keeps track of which sites are already crawled

    if mode == "block":                                 # Step 5: Gets the blocked domain from Disconnect's services.json
        blocked_domain = load_blocked_domain()
    else:                                               # If not in the block mode, we do not have any blocked domain
        blocked_domain = None

    with sync_playwright() as p:                        # Step 6: Start Playwright and Chromium
        browser = p.chromium.launch()

        for domain, country in sites:
            if domain in crawled_domain:                # Skips domain we already have crawled
                continue

            visit_site(p, browser, domain, mode, output_dir, blocked_domain)
            mark_domainain_as_crawled(output_dir, domain)
        
        browser.close()

if __name__ == "__main__":
    main()