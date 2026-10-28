"""Save a manual token for a separate local Questrade personal app using hidden input."""
import getpass
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parent
LOCAL_TOKEN=ROOT/'.secrets/local-preview/questrade.json'


def save_token(token,target=LOCAL_TOKEN):
    if not isinstance(token,str) or not token.strip() or any(c.isspace() for c in token.strip()):
        raise ValueError('Enter the manual authorization token without whitespace.')
    token=token.strip()
    shared=ROOT/'.secrets/questrade.json'
    if shared.is_file():
        try: previous=json.loads(shared.read_text()).get('refresh_token')
        except (OSError,ValueError,AttributeError): previous=None
        if previous==token:
            raise ValueError('This matches the old shared authorization. Use a token from the separate local personal app.')
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True,mode=0o700);target.parent.chmod(0o700)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=target.parent,prefix='.questrade-',delete=False) as stream:
            temporary=Path(stream.name);os.fchmod(stream.fileno(),0o600)
            json.dump({'refresh_token':token},stream);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,target)
    finally:
        if temporary is not None and temporary.exists(): temporary.unlink()


def main():
    if not sys.stdin.isatty():
        raise SystemExit('Run this command in your local interactive terminal; token input stays hidden.')
    print('Use a manual authorization token from the separate aiMoney Local personal app.')
    token=getpass.getpass('Local Questrade token (hidden): ')
    try: save_token(token)
    except ValueError as error: raise SystemExit(str(error)) from None
    except OSError: raise SystemExit('Could not save local authorization. Check private-directory permissions.') from None
    print('Local authorization saved securely. Return to localhost:8765 and refresh the analysis.')


if __name__=='__main__':main()
