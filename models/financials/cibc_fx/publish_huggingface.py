"""Package the fitted model and optionally upload to a private Hugging Face repo.

No third-party dependencies. Only the explicit FILES allowlist is uploaded.
"""
import argparse
import base64
from getpass import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

HERE=Path(__file__).resolve().parent
PACKAGE=HERE/'artifacts/huggingface-package'
TOKEN_FILE=HERE/'.secrets/hf-token'
FILES=('README.md','model.py','predict.py','artifacts/model.json','evaluation.json','manifest.json')


def prepare():
    model=json.loads((HERE/'artifacts/model.json').read_text())
    evaluation=json.loads((HERE/'evaluation/holdout.json').read_text())
    summary={key:evaluation[key] for key in ['evaluation','limitation','train_samples','test_samples','train_end','test_start','overall','by_direction','by_usd_size']}
    files={'model.py':(HERE/'model.py').read_text(),'predict.py':(HERE/'predict.py').read_text(),
           'artifacts/model.json':json.dumps(model,indent=2)+'\n','evaluation.json':json.dumps(summary,indent=2)+'\n'}
    files['README.md']=f'''---
language: en
tags:
- finance
- regression
- currency-conversion
- statistical-model
model-index:
- name: CIBC FX conversion baseline
  results: []
---

# CIBC FX conversion baseline

A small statistical regression model estimating CIBC CAD/USD conversion rates
relative to an explicitly supplied CAD-per-USD reference. This is a custom Python
model, not a language model or Transformers checkpoint. It requires Python 3.10+
and only the standard library. Uploading it does not create a hosted inference API.

## Method and usage

Separate median proportional adjustments are fitted for buying and selling USD:

`estimated_rate = reference_rate * (1 + adjustment[direction])`

`estimated_cad = USD subtotal * estimated_rate`

The USD subtotal must already include transaction commissions where applicable.
Do not add the original commission twice. Use `buy_usd` to fund a USD purchase
from CAD; use `sell_usd` to convert USD proceeds to CAD.

After downloading this repository:

```sh
python3 predict.py --direction sell_usd --reference-rate 1.40 --usd 1000
```

```python
import json
from model import predict
with open('artifacts/model.json') as source:
    fitted = json.load(source)
print(predict(fitted, 'sell_usd', 1.40, 1000))
```

## Training and validation

Trained on {model['samples']} reviewed private transaction samples, with settlement
dates from {model['settlement_start']} through {model['settlement_end']}.
Raw transactions, account identifiers, screenshots, cost bases, broker credentials
and OpenAI assessments are not included in this repository.

Chronological evaluation used {evaluation['train_samples']} earlier training samples
and {evaluation['test_samples']} later holdout samples, keeping each settlement date
entirely within one side of the split. The published final model is subsequently
refitted on all eligible samples; the holdout metrics describe the earlier model.

- Mean absolute CAD error: {evaluation['overall']['mean_absolute_cad_error']:.2f} CAD.
- Mean absolute percentage CAD error: {evaluation['overall']['mean_absolute_percentage_cad_error']:.3f}%.
- Maximum absolute CAD error: {evaluation['overall']['max_absolute_cad_error']:.2f} CAD.

Aggregate evaluation details are in `evaluation.json`. Private training data is
not distributed, so this repository supports inference but not reproducing the
original fit from raw data.

## Limits

Training uses retrospective Yahoo settlement-day daily closes, which can differ
from broker conversion-time references. Adjustments mix pricing and timing effects;
they are not isolated broker fees. Accuracy with live or future reference rates
is unvalidated. Samples sharing dates are correlated. This small historical sample
does not establish current broker policy or a guaranteed error bound.

The model does not forecast market FX, stock prices, option prices or investment
returns. Amount-range warnings are not prediction intervals. Downstream tools must
state their conversion treatment and fee assumptions. No OpenAI dependency or
recommendation logic is included.

## Files

- `model.py`: pure fitting and prediction functions.
- `predict.py`: command-line inference.
- `artifacts/model.json`: fitted parameters and model provenance.
- `evaluation.json`: aggregate holdout metrics.
- `manifest.json`: SHA-256 checksums of the published payload.
'''
    manifest={name:hashlib.sha256(content.encode()).hexdigest() for name,content in files.items()}
    files['manifest.json']=json.dumps(manifest,indent=2)+'\n'
    for name,content in files.items():
        target=PACKAGE/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content)
    return {name:content.encode() for name,content in files.items()}


def request(path,token,body=None,content_type='application/json'):
    headers={'Authorization':'Bearer '+token,'User-Agent':'cibc-fx-publisher/1'}
    if body is not None:headers['Content-Type']=content_type
    req=urllib.request.Request('https://huggingface.co'+path,data=body,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=60) as response:return json.load(response)
    except urllib.error.HTTPError as error:
        # Return only a status code, never credential-bearing payloads.
        raise RuntimeError(f'Hugging Face returned HTTP {error.code}. Check token permissions and repository access.') from None
    except (OSError,ValueError):raise RuntimeError('Hugging Face connection failed. Check the network and retry.') from None


def token_value():
    value=os.environ.get('HF_TOKEN') or os.environ.get('HUGGING_FACE_HUB_TOKEN')
    if value:return value.strip()
    for file in [TOKEN_FILE,Path(os.environ.get('HF_HOME',Path.home()/'.cache/huggingface'))/'token',Path.home()/'.huggingface/token']:
        if file.exists():return file.read_text().strip()
    raise ValueError('No Hugging Face token. Run this script with --login and enter a write-capable token in the hidden prompt.')


def publish(token,files,name='cibc-fx'):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}',name):raise ValueError('Use a simple repository name.')
    if set(files)!=set(FILES):raise ValueError('Upload payload does not match the explicit model-file allowlist.')
    owner=request('/api/whoami-v2',token)['name']
    if not re.fullmatch(r'[A-Za-z0-9_-]+',owner):raise ValueError('Unexpected account name.')
    repo=f'{owner}/{name}'
    # Personal namespace only; never change visibility of an existing repository.
    try:info=request(f'/api/models/{repo}',token)
    except RuntimeError as error:
        if 'HTTP 404' not in str(error):raise
        request('/api/repos/create',token,json.dumps({'name':name,'type':'model','private':True}).encode())
        info=request(f'/api/models/{repo}',token)
    if info.get('private') is not True:raise ValueError('The destination already exists and is public. Choose a new private repository name.')
    header={'summary':'Upload CIBC FX fitted model and aggregate evaluation','description':'Inference-only model package; no raw transaction data.'}
    if info.get('sha'):header['parentCommit']=info['sha']
    operations=[{'key':'header','value':header}]+[{'key':'file','value':{'path':name,'content':base64.b64encode(files[name]).decode(),'encoding':'base64'}} for name in FILES]
    payload=b''.join(json.dumps(item).encode()+b'\n' for item in operations)
    committed=request(f'/api/models/{repo}/commit/main',token,payload,'application/x-ndjson')
    oid=committed['commitOid']
    info=request(f'/api/models/{repo}/revision/{oid}',token)
    if info.get('private') is not True:raise RuntimeError('Post-upload repository privacy check failed.')
    for name in FILES:
        req=urllib.request.Request(f'https://huggingface.co/{repo}/resolve/{oid}/{name}',headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(req,timeout=60) as response:remote=response.read()
        if hashlib.sha256(remote).digest()!=hashlib.sha256(files[name]).digest():raise RuntimeError(f'Uploaded checksum mismatch: {name}')
    result={'url':f'https://huggingface.co/{repo}','commit':oid,'private':True,'files':list(FILES),'verified':True}
    (HERE/'artifacts/huggingface-upload.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--login',action='store_true',help='Verify and save a token entered through a hidden terminal prompt.')
    parser.add_argument('--upload',action='store_true',help='Upload the reviewed package to a private personal repository.')
    parser.add_argument('--repo-name',default='cibc-fx')
    args=parser.parse_args()
    files=prepare()
    print('Prepared model package:',PACKAGE)
    print('Files:',', '.join(FILES))
    if args.login:
        token=getpass('Hugging Face write token (hidden): ').strip()
        if not token:raise ValueError('No token entered.')
        owner=request('/api/whoami-v2',token)['name']
        TOKEN_FILE.parent.mkdir(parents=True,exist_ok=True)
        descriptor=os.open(TOKEN_FILE,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600);os.fchmod(descriptor,0o600)
        with os.fdopen(descriptor,'w') as out:out.write(token)
        print('Authenticated as:',owner)
    if args.upload:print(json.dumps(publish(token_value(),files,args.repo_name),indent=2))
    elif not args.login:print('Package ready. Upload requires Hugging Face authentication.')


if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,KeyError,OSError) as error:raise SystemExit(str(error)) from None
