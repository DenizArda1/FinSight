"""Local research workspace backed by the existing MCP orchestrator."""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock
from time import perf_counter
from urllib.parse import urlsplit
from uuid import uuid4

from src.agents.runtime import run_mcp_orchestrator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from src.reporting import build_report, source_financial_rows, split_research_note
from src.verification.agent_answer import format_source_references
from src.verification.citations import SOURCE_REFERENCE
from src.utils.utils import load_yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def present_result(question, result):
    """Keep verification decisions and original evidence intact for the UI."""
    supported = (result.get('verification') or {}).get('supported') is True and bool(result.get('answer'))
    rows, evidence = source_financial_rows(result)
    prose, details = split_research_note(result) if supported else ('', '')
    cited = {int(n) for n in SOURCE_REFERENCE.findall(result.get('answer') or '')} if supported else {r['Kaynak'] for r in rows}
    sources = []
    for source in evidence:
        number = source['source_id']
        if number not in cited or source.get('content_omitted'):
            continue
        sources.append({'id': number, 'reference': format_source_references(f'[Source {number}]', [source])})
    return {'supported': supported, 'prose': prose, 'details': details, 'rows': rows, 'sources': sources,
            'issues': (result.get('verification') or {}).get('issues', []), 'usage': result.get('usage'),
            'markdown': build_report(question, result) if supported else None}


async def research(question):
    settings = load_yaml(PROJECT_ROOT / 'configs/settings.yaml')
    return await run_mcp_orchestrator(question, settings['llm'])


class ResearchJobs:
    def __init__(self, runner=research):
        self.runner = runner
        self.jobs = {}
        self.lock = Lock()
        self.executor = ThreadPoolExecutor(max_workers=1)

    def submit(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'company', 'question'}:
            raise ValueError('Geçersiz istek.')
        company, question = payload.get('company', ''), payload.get('question')
        if not isinstance(company, str) or not isinstance(question, str) or not question.strip():
            raise ValueError('Lütfen bir araştırma sorusu yazın.')
        if len(company) > 100 or len(question) > 4000:
            raise ValueError('Şirket veya soru uzunluk sınırını aşıyor.')
        with self.lock:
            if any(job['status'] == 'running' for job in self.jobs.values()):
                raise RuntimeError('Bir araştırma zaten çalışıyor. Tamamlanmasını bekleyin.')
            job = {'id': uuid4().hex, 'company': company.strip(), 'question': question.strip(),
                   'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'running'}
            self.jobs[job['id']] = job
            # Bound in-memory history; diagnostic traces remain managed by the runtime.
            if len(self.jobs) > 50:
                del self.jobs[next(iter(self.jobs))]
            snapshot = dict(job)
        self.executor.submit(self.run, snapshot)
        return snapshot

    def run(self, job):
        started = perf_counter()
        question = job['question']
        if job['company']:
            question += f"\nSelected company: {job['company']}."
        try:
            result = asyncio.run(self.runner(question))
            update = {'status': 'completed', 'result': present_result(question, result)}
        except Exception:
            # Detailed diagnostics are recorded by the existing runtime, not exposed to browsers.
            update = {'status': 'failed', 'error': 'Araştırma tamamlanamadı. Model ve API bağlantısını kontrol edip yeniden deneyin.'}
        update['elapsed_seconds'] = round(perf_counter() - started, 1)
        with self.lock:
            self.jobs[job['id']].update(update)

    def snapshot(self, job_id=None):
        with self.lock:
            if job_id is not None:
                return dict(self.jobs[job_id]) if job_id in self.jobs else None
            return [dict(job) for job in reversed(list(self.jobs.values()))]


class ResearchHandler(SimpleHTTPRequestHandler):
    ASSETS = {
        '/': 'templates/research.html',
        '/static/research.css': 'static/research.css',
        '/static/research.js': 'static/research.js',
    }

    def translate_path(self, path):
        relative = self.ASSETS.get(urlsplit(path).path, '__not_found__')
        return str(PROJECT_ROOT / 'src' / relative)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()

    def log_message(self, format, *args):
        # Request logs contain no useful research diagnostics; runtime traces do.
        return

    def local_request(self):
        expected = f'127.0.0.1:{self.server.server_port}'
        return self.headers.get('Host') == expected and self.headers.get('Origin', f'http://{expected}') == f'http://{expected}'

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.local_request():
            return self.send_json(403, {'error': 'Yalnızca yerel erişim desteklenir.'})
        path = urlsplit(self.path).path
        if path == '/api/research':
            return self.send_json(200, self.server.jobs.snapshot())
        if path.startswith('/api/research/'):
            job = self.server.jobs.snapshot(path.rsplit('/', 1)[-1])
            return self.send_json(200 if job else 404, job or {'error': 'Araştırma bulunamadı.'})
        super().do_GET()

    def do_POST(self):
        if not self.local_request() or self.headers.get('X-FinSight-Request') != 'research':
            return self.send_json(403, {'error': 'Geçersiz istek kaynağı.'})
        if urlsplit(self.path).path != '/api/research':
            return self.send_json(404, {'error': 'Bulunamadı.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 20000 or self.headers.get('Content-Type') != 'application/json':
                raise ValueError('Geçersiz istek gövdesi.')
            payload = json.loads(self.rfile.read(length))
            job = self.server.jobs.submit(payload)
        except (ValueError, UnicodeError) as error:
            return self.send_json(400, {'error': str(error)})
        except RuntimeError as error:
            return self.send_json(409, {'error': str(error)})
        self.send_json(202, job)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--host', choices=['127.0.0.1', '0.0.0.0'], default='127.0.0.1',
                        help='Use 0.0.0.0 only inside a container published to host loopback.')
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ResearchHandler)
    server.jobs = ResearchJobs()
    print(f'FinSight: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.jobs.executor.shutdown(wait=True)


if __name__ == '__main__':
    main()
