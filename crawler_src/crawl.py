import csv
from playwright.sync_api import sync_playwright
import argparse
from tld import get_fld

CRAWL_MODES = ["desktop", "mobile", "block", "ignore"]

# Reads the flags -m and -l from the command line
def arg_parser():
    parser = argparse.ArgumentParser()              # Initiates a parser
    
    # Adds the 2 possible arguments found in the command line
    parser.add_argument("-m", "mode")
    parser.add_argument("-l", "list")

    args = parser.parse_args()                      # The arguments from the command line
    
    return args

# Reads the csv-file, returning a list of tuples
def read_site_list(site_files):
    sites = []
    
    with open(site_files, newline="") as file:
        for row in csv.reader(file):
            if not row:
                continue
            domain = row[0].strip()
            country = row[1].strip()
            sites.append((domain, country))         # Appends a tuple (domain, country) to the list sites

# functions to know which websites is crawled already
def get_crawled_site_file(output_dir):
    crawled_site_file = output_dir / "crawled_sites.txt"
    return crawled_site_file
    
def load_crawled_domains(output_dir):
    crawled_sites_file = get_crawled_site_file(output_dir)
    
    if not crawled_sites_file.exists():
        return set()
    
    with open(crawled_sites_file, encoding="utf-8") as file:
        for line in file:
            domain = line.strip() # remove the newline and any spaces
            if domain == "": # skip empty lines
                continue
            crawled_domains.add(domain)                 # TODO: should we define crawled_domains?

    return crawled_domains

def mark_domain_as_crawled(output_dir, domain):
    with open(get_crawled_site_file(output_dir), "a", encoding = "utf-8") as crawled_sites_file:
        crawled_sites_file.write(domain + "\n")

# Reads the json file from Disconnect, returns a set of blocked domains
def load_blocked(disconnect_jscon):
    return

# Ignores blocked requests
def request_blocker(blocked_domains):
    return

def create_browser_context(p, browser, mode, har_path, video):
    return

def accept_cookies():
    return

def load_blocked_domains():
    #should return the list of blocked domains from disconnect/services.json
    return


# get all entries that were not blocked (status != 0)
def get_valid_entries(har):
    valid = []
    for entry in har['log']['entries']:
        if entry['response']['status'] == 0:
            continue
        if entry['response'].get('redirectURL', '').startswith('chrome-extension://'):
            continue
        valid.append(entry)
    return valid

# get number of requests per website
def get_number_of_requests(valid):
    return len(valid)

# given page_url and request_url check if third party access
def is_third_party(page_url, request_url):
    return get_fld(page_url) != get_fld(request_url)

def get_number_of_third_party_requests(valid, page_url):
    count = 0
    for entry in valid:
        if is_third_party(page_url, entry['request']['url']):
            count +=1
    return count

# get length of list with all third pary hostnames
def numberOfDistinctThirdPartyDomains (valid, page_url):
    tp_domains = set()
    for entry in valid:
        req_url = entry ['request']['url']
        if is_third_party(page_url, req_url):
            tp_domains.add(get_fld(req_url))
    return len(tp_domains)

def take_screenshot(url):
    with sync_playwright() as p:
        browser = p.webkit.launch()
        page = browser.new_page()
        page.goto(url)
        page.screenshot
    return


def main():
    return

if __name__ == "__main__":
    main()