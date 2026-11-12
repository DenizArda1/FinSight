#Prepare container-only configuration, then replace this process with the app.
import os
from pathlib import Path
import shutil
import sys
from urllib.parse import urlsplit

import yaml


def configure(source, destination, ollama_url):
    parsed = urlsplit(ollama_url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('OLLAMA_BASE_URL must be an HTTP(S) service URL without credentials')
    destination.mkdir(parents=True, exist_ok=True)
    for path in source.glob('*.yaml'):
        shutil.copyfile(path, destination / path.name)
    settings_path = destination / 'settings.yaml'
    settings = yaml.safe_load(settings_path.read_text(encoding='utf-8'))
    settings['embedding']['base_url'] = ollama_url.rstrip('/')
    settings['llm']['base_url'] = ollama_url.rstrip('/')
    for role in settings['llm'].get('roles', {}).values():
        if role.get('provider', 'ollama') == 'ollama':
            role['base_url'] = ollama_url.rstrip('/')
    settings_path.write_text(yaml.safe_dump(settings, sort_keys=False), encoding='utf-8')


def main():
    configure(Path('/opt/finsight/configs'), Path('/app/configs'),
              os.environ.get('OLLAMA_BASE_URL', 'http://host.docker.internal:11434'))
    if len(sys.argv) < 2:
        raise ValueError('A container command is required')
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == '__main__':
    main()
