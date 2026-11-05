import json
from urllib.parse import urlparse

# List of categories to block, based on Disconnect's services.json
BLOCKED_CATEGORIES = ["Advertising", "Analytics", "Social", "FingerprintingInvasive", "FingerprintingGeneral"]

# Reads the json file from Disconnect, returns a set of blocked domains
def load_blocked(services_json_path):
    with open(services_json_path, "r", encoding="utf-8") as file:
        services = json.load(file)
    blocked_domains = set()
    for category in BLOCKED_CATEGORIES:
        for entity in services["categories"].get(category, []): # ex {"Google": {...}}
            for entity_info in entity.values(): # ex {"http://google.com/": [domains]}
                for value in entity_info.values():
                    if isinstance(value, list): # skip extras like "session-replay": "true"
                        blocked_domains.update(domain.lower() for domain in value)

    return blocked_domains #returns the list of blocked domains from disconnect/services.json

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
