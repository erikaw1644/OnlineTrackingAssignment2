import csv
from playwright.sync_api import sync_playwright
import argparse
from pathlib import Path
from page_actions import load_homepage, scroll_to_bottom, take_screenshot, accept_cookies
from blocking import load_blocked, request_blocker

# Playwright takes milliseconds
WAIT_AFTER_PAGE_LOAD_MS = 10000
WAIT_AFTER_CONSENT_MS = 5000
WAIT_AFTER_SCROLL_MS = 5000

DISCONNECT_SERVICES_PATH = Path(__file__).resolve().parent / "disconnect" / "services.json"

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

# Resume feature: keeps track of which domains have already been crawled, so we can skip them on the next run
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


# Saves the URL the page ended up at (after redirects), needed for third-party checks in the analysis
def save_final_url(output_dir, domain, final_url):
    with open(output_dir / "final_urls.csv", "a", encoding="utf-8") as final_urls_file:
        final_urls_file.write(f"{domain},{final_url}\n")


# Creates a fresh browser context that records a HAR file and a video
def create_browser_context(p, browser, mode, har_path, video_dir):
    context_options = {
        "record_har_path": str(har_path),
        "record_har_content": "omit", # we only need headers, not page contents
        "record_video_dir": str(video_dir),
    }
    if mode == "mobile":
        pixel_10 = dict(p.devices["Pixel 10"]) 
        context_options.update(pixel_10)
    else:
        context_options["viewport"] = {"width": 1280, "height": 800}
    return browser.new_context(**context_options)



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
        save_final_url(output_dir, domain, page.url) # save the final URL after redirects
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
        browser = p.chromium.launch(headless=False) # one browser for the whole crawl
        for domain, country in sites:
            if domain in crawled_domains:
                print(f"Skipping {domain} as it has already been crawled.")
                continue
            print(f"Crawling {domain} in mode {args.mode}...")
            try:
                visit_site(p, browser, domain, args.mode, output_dir, blocked_domains)
                mark_domain_as_crawled(output_dir, domain) # only after a successful visit
            except Exception as error:
                print(f"  Failed to crawl {domain}: {error}")
        browser.close()
        
        # removes the temporary video directory if it is empty
        videos_tmp_dir = output_dir / "videos_tmp"
        if videos_tmp_dir.exists() and not any(videos_tmp_dir.iterdir()):
            videos_tmp_dir.rmdir()
    return

if __name__ == "__main__":
    main()