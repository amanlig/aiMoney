"""Configure the server-side OpenAI key without echoing or exposing it in HTML."""
from getpass import getpass
import json
import os
from close_recommendations import CONFIG


def main():
    key=getpass('OpenAI API key (hidden input): ').strip()
    if not key:raise SystemExit('No key entered; configuration unchanged.')
    model=input('OpenAI model [gpt-6-astra]: ').strip() or 'gpt-6-astra'
    CONFIG.parent.mkdir(parents=True,exist_ok=True)
    descriptor=os.open(CONFIG,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    os.fchmod(descriptor,0o600)
    with os.fdopen(descriptor,'w') as out:json.dump({'api_key':key,'model':model},out)
    print('Saved server-only configuration. Return to the simulator; no server restart needed.')


if __name__=='__main__':main()
