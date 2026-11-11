# OnlineTrackingAssignment2

# Crawler

## Install
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Run (from the repository root)
```bash
python crawler_src/crawl.py -m desktop -l sites.csv
python crawler_src/crawl.py -m mobile -l sites.csv
python crawler_src/crawl.py -m block -l sites.csv
python crawler_src/crawl.py -m ignore -l sites.csv
```
Output goes to `crawl_data_<mode>/`. If the crawler stops, run the same command again;
sites listed in `crawl_data_<mode>/crawled_sites.txt` are skipped.

## Files
- `crawl.py`: command line, visit loop, browser setup, resume
- `page_actions.py`: loading the homepage, scrolling, screenshots, accepting cookie banners (priv-accept keywords in `accept_words.txt` + Dutch keywords)
- `blocking.py`: blocking Disconnect's tracker categories (`disconnect/services.json`)