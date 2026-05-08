from scraper import VideoScraper
from config import Config

if __name__ == "__main__":
    cfg = Config()
    s = VideoScraper(cfg)
    res = s.search("One State RP MOD gameplay", max_results=5)
    print("Found:", len(res))
    for i, r in enumerate(res[:5], 1):
        print(i, r.get("title") or r.get("id") or r.get("webpage_url") or r.get("url"))
