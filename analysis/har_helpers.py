from tld import get_fld


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

# get length of list with all third pary hostnames
def num_of_distinct_third_party_domains(valid_entries, page_url):
    tp_domains = set()
    for entry in valid_entries:
        req_url = entry ['request']['url']
        if is_third_party(page_url, req_url):
            tp_domains.add(get_fld(req_url))
    return len(tp_domains)

