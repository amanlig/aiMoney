"""Prepare an allowlisted standalone package; explicitly upload to a public HF repo."""
import argparse
import base64
from getpass import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
PACKAGE = HERE/'artifacts/huggingface-package'
TOKEN_FILE = HERE/'.secrets/hf-token'
FILES = ('README.md', 'model.py', 'run_example.py', 'examples/sample_input.json',
         'examples/make_sample.py', 'examples/expected_result.json',
         'examples/expected_rollovers.csv', 'tests/test_model.py', 'examples/simulation-profit.png',
         'examples/render_aimoney_chart.py', 'examples/simulation-chart-provenance.json', 'manifest.json')


def prepare():
    # Read only explicitly selected source and synthetic files. Never copy a repo tree.
    source = {'README.md': HERE/'MODEL_CARD.md'}
    for name in ('model.py', 'run_example.py', 'examples/sample_input.json',
                 'examples/make_sample.py', 'tests/test_model.py', 'examples/simulation-profit.png',
                 'examples/render_aimoney_chart.py', 'examples/simulation-chart-provenance.json'):
        source[name] = HERE/name
    files = {name: path.read_bytes() for name, path in source.items()}
    with tempfile.TemporaryDirectory() as temp:
        output, csv = Path(temp)/'result.json', Path(temp)/'rollovers.csv'
        subprocess.run([sys.executable, str(HERE/'run_example.py'), '--output', str(output),
                        '--csv', str(csv)], check=True, capture_output=True)
        files['examples/expected_result.json'] = output.read_bytes()
        files['examples/expected_rollovers.csv'] = csv.read_bytes()
    provenance=json.loads(files['examples/simulation-chart-provenance.json'])
    for source, key in [('examples/sample_input.json','sample_input_sha256'),
                        ('examples/expected_result.json','expected_result_sha256'),
                        ('examples/simulation-profit.png','chart_sha256')]:
        if hashlib.sha256(files[source]).hexdigest()!=provenance[key]:
            raise ValueError('Chart is stale; regenerate with examples/render_aimoney_chart.py before publishing.')
    files['manifest.json'] = (json.dumps({
        'model_version': '1.15', 'data': 'synthetic only',
        'files': {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}
    }, indent=2)+'\n').encode()
    assert set(files) == set(FILES)
    for name, content in files.items():
        path=PACKAGE/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    return files


class HubError(RuntimeError):
    def __init__(self, status):
        self.status=status
        super().__init__(f'Hugging Face returned HTTP {status}; check account and token access.')


def request(path, token, body=None, content_type='application/json', raw=False):
    headers={'Authorization':'Bearer '+token, 'User-Agent':'covered-call-exit-publisher/1'}
    if body is not None: headers['Content-Type']=content_type
    req=urllib.request.Request('https://huggingface.co'+path, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            content=response.read()
        return content if raw else json.loads(content)
    except urllib.error.HTTPError as error:
        raise HubError(error.code) from None
    except (OSError, ValueError):
        raise RuntimeError('Hugging Face connection failed; credentials withheld.') from None


def token_value():
    value=os.environ.get('HF_TOKEN') or os.environ.get('HUGGING_FACE_HUB_TOKEN')
    if value: return value.strip()
    paths=[TOKEN_FILE, HERE.parent/'cibc_fx/.secrets/hf-token',
           Path(os.environ.get('HF_HOME', Path.home()/'.cache/huggingface'))/'token',
           Path.home()/'.huggingface/token']
    for path in paths:
        if path.is_file(): return path.read_text().strip()
    raise ValueError('No Hugging Face login found. Run with --login to enter a write token in a hidden prompt.')


def publish(token, files, name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', name):
        raise ValueError('Use a simple repository name.')
    if set(files)!=set(FILES): raise ValueError('Upload must match the explicit package allowlist.')
    owner=request('/api/whoami-v2', token)['name']
    if not re.fullmatch(r'[A-Za-z0-9_-]+', owner): raise ValueError('Unexpected account name.')
    repo=f'{owner}/{name}'
    try:
        info=request(f'/api/models/{repo}', token)
    except HubError as error:
        if error.status!=404: raise
        request('/api/repos/create', token,
                json.dumps(dict(name=name, type='model', private=False)).encode())
        info=request(f'/api/models/{repo}', token)
    if info.get('private') is not False:
        raise ValueError('Destination exists and is private; visibility was not changed. Choose a new public repo name.')
    # Require a new/empty repo or a repo containing our previously published manifest.
    existing={s['rfilename'] for s in info.get('siblings', [])}
    if existing- {'.gitattributes'} and 'manifest.json' not in existing:
        raise ValueError('Destination contains unrelated files; choose a new repository name.')
    if 'manifest.json' in existing:
        prior=json.loads(request(f'/{repo}/resolve/{info["sha"]}/manifest.json', token, raw=True))
        if prior.get('data')!='synthetic only' or 'model.py' not in prior.get('files', {}):
            raise ValueError('Destination manifest is not recognized; stopped before upload.')
    header={'summary':'Publish covered-call exit model, mathematical model card and synthetic examples',
            'description':'Black–Scholes option pricing and historical-return bootstrap; no private financial data.'}
    if info.get('sha'): header['parentCommit']=info['sha']
    operations=[{'key':'header','value':header}]+[{'key':'file','value':{
        'path':name,'content':base64.b64encode(files[name]).decode(),'encoding':'base64'}} for name in FILES]
    payload=b''.join(json.dumps(item).encode()+b'\n' for item in operations)
    if any(content.startswith(b'\x89PNG\r\n\x1a\n') for content in files.values()):
        # Binary images must use Hub's supported preupload / large-file storage path.
        try:
            from huggingface_hub import HfApi, CommitOperationAdd, CommitOperationDelete
            from io import BytesIO
        except ImportError:
            raise ValueError('Publishing images requires: python3 -m pip install huggingface_hub') from None
        api=HfApi(token=token)
        additions=[CommitOperationAdd(path_in_repo=name,path_or_fileobj=BytesIO(files[name])) for name in FILES]
        if 'examples/plot_simulation.py' in existing:
            additions.append(CommitOperationDelete(path_in_repo='examples/plot_simulation.py'))
        committed=api.create_commit(repo_id=repo, repo_type='model',
            operations=additions,
            commit_message=header['summary'],commit_description=header['description'],
            parent_commit=info.get('sha'))
        commit=committed.oid
    else:
        commit=request(f'/api/models/{repo}/commit/main', token, payload, 'application/x-ndjson')['commitOid']
    info=request(f'/api/models/{repo}/revision/{commit}', token)
    if info.get('private') is not False: raise RuntimeError('Post-upload public visibility check failed.')
    for name, content in files.items():
        remote=request(f'/{repo}/resolve/{commit}/{name}', token, raw=True)
        if hashlib.sha256(remote).digest()!=hashlib.sha256(content).digest():
            raise RuntimeError(f'Uploaded checksum mismatch: {name}')
    receipt=dict(url=f'https://huggingface.co/{repo}', commit=commit, private=False,
                 files=list(FILES), verified=True)
    (HERE/'artifacts/huggingface-upload.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--login', action='store_true', help='Save a verified token from a hidden terminal prompt.')
    parser.add_argument('--upload', action='store_true', help='Publish the allowlisted package to a PUBLIC model repo.')
    parser.add_argument('--repo-name', default='covered-call-exit-model')
    args=parser.parse_args()
    files=prepare()
    print('Prepared:',PACKAGE)
    if args.login:
        if not sys.stdin.isatty(): raise ValueError('Login requires an interactive terminal; do not paste tokens into chat.')
        token=getpass('Hugging Face write token (hidden): ').strip()
        if not token: raise ValueError('No token entered.')
        owner=request('/api/whoami-v2',token)['name']
        TOKEN_FILE.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=os.open(TOKEN_FILE,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as stream: stream.write(token)
        print('Authenticated as:',owner)
    if args.upload:
        print(json.dumps(publish(token_value(),files,args.repo_name),indent=2))
    else:
        print('Package ready. --upload publishes publicly using your authenticated personal namespace.')


if __name__=='__main__':
    try: main()
    except (ValueError,RuntimeError,KeyError,OSError,subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from None
