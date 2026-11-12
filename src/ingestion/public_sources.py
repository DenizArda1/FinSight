#Bounded, cached access to official SEC, Federal Reserve and BLS sources
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests

from src.utils.utils import load_json, save_json

ROOT = Path(__file__).resolve().parents[2] / 'financial_data' / 'supplemental'
HOSTS = {'www.sec.gov', 'data.sec.gov', 'www.federalreserve.gov', 'api.bls.gov'}


class PublicSourceClient:
    def __init__(self, user_agent='FinSight research', root=ROOT, ttl=21600):
        self.root, self.ttl, self.user_agent = Path(root), ttl, user_agent
        self.last_request = 0.0

    def get(self, url):
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname not in HOSTS or parsed.username or parsed.port:
            raise ValueError('Unsupported official source URL')
        path = self.root / (hashlib.sha256(url.encode()).hexdigest() + '.json')
        if path.is_file():
            cached = load_json(path)
            if (cached['url'] == url and time.time() - cached['timestamp'] < self.ttl
                    and hashlib.sha256(cached['text'].encode()).hexdigest() == cached['sha256']):
                return cached
        for attempt in range(3):
            time.sleep(max(0, .3 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            with requests.get(url, headers={'User-Agent': self.user_agent}, timeout=(10, 45),
                              allow_redirects=False, stream=True) as response:
                if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                response.raise_for_status()
                if 300 <= response.status_code < 400:
                    raise ValueError('Unexpected redirect from official source')
                content = bytearray()
                for chunk in response.iter_content(65536):
                    content.extend(chunk)
                    if len(content) > 15000000:
                        raise ValueError('Official source exceeds download size limit')
                text = content.decode('utf-8', errors='replace')
                if not text.strip():
                    raise ValueError('Empty official source response')
                cached = {'url': url, 'timestamp': time.time(),
                          'retrieved_at': datetime.now(timezone.utc).isoformat(),
                          'sha256': hashlib.sha256(text.encode()).hexdigest(), 'text': text}
                save_json(cached, path)
                return cached
        raise ValueError('Official source request failed')

    def json(self, url):
        response = self.get(url)
        return json.loads(response['text']), response
