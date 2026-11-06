import json
from tld import get_fld
from urllib.parse import urlparse


# get all entries that were not blocked (status != 0), leaving out entries that were blocked by the browser or extensions
def get_valid_entries(har):
    valid = []
    for entry in har['log']['entries']:
        if entry['response']['status'] <= 0:
            continue
        valid.append(entry)
    return valid

# get number of requests per website
def get_number_of_requests(valid):
    return len(valid)

# get the domain of a url
def get_domain(page_url):
    return get_fld(page_url, fail_silently=True)

# given page_url and request_url check if third party access
def is_third_party(page_url, request_url):
    request_domain = get_domain(request_url)
    if request_domain is None:
        return False
    return get_domain(page_url) != request_domain

# get number of third party requests
def get_number_of_third_party_requests(valid_entries, page_url):
    count = 0
    for entry in valid_entries:
        if is_third_party(page_url, entry['request']['url']):
            count +=1
    return count

# get length of list with all third party hostnames
def num_of_distinct_third_party_domains(valid_entries, page_url):
    tp_domains = set()
    for entry in valid_entries:
        req_url = entry ['request']['url']
        if is_third_party(page_url, req_url):
            tp_domains.add(get_domain(req_url))
    return len(tp_domains)

# final URL of the homepage (after redirects): the last successfully loaded document in the main frame
def find_page_url(har):
    entries = har['log']['entries']
    main_frame = entries[0].get('_frameref')
    page_url = entries[0]['request']['url']
    for entry in entries:
        if (entry.get('_resourceType') == 'document'
                and entry.get('_frameref') == main_frame
                and 200 <= entry['response']['status'] < 300):
            page_url = entry['request']['url']
    return page_url


# maps every domain in Disconnect's entities.json to the entity (company) that owns it
def load_entity_by_domain(entities_path):
    with open(entities_path, encoding='utf-8') as entities_file:
        entities = json.load(entities_file)['entities']
    entity_by_domain = {}
    for entity_name, entity_info in entities.items():
        for domain in entity_info.get('properties', []) + entity_info.get('resources', []):
            entity_by_domain[domain.lower()] = entity_name
    return entity_by_domain


# entity of a request URL (checks the hostname and its parent domains), or None if not listed
def get_entity(request_url, entity_by_domain):
    hostname_parts = (urlparse(request_url).hostname or '').lower().split('.')
    for start_index in range(len(hostname_parts) - 1):
        candidate_domain = '.'.join(hostname_parts[start_index:])
        if candidate_domain in entity_by_domain:
            return entity_by_domain[candidate_domain]
    return None


# get number of distinct third party entities (third-party domains not in Disconnect's list are not counted)
def num_of_distinct_third_party_entities(valid_entries, page_url, entity_by_domain):
    tp_entities = set()
    for entry in valid_entries:
        req_url = entry['request']['url']
        if is_third_party(page_url, req_url):
            entity = get_entity(req_url, entity_by_domain)
            if entity is not None:
                tp_entities.add(entity)
    return len(tp_entities)
