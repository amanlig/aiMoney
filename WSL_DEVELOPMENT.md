# WSL development

Use the `Ubuntu-24.04` distribution and the Linux workspace at
`/home/amanlig/Projects/aiMoney`. The project was copied from the Windows working
tree, including uncommitted React changes and private local data. Development,
captures, database updates and token rotation now belong to the Linux copy.
Do not copy an older Windows token over the active Linux token.

Open a WSL terminal:

```powershell
wsl -d Ubuntu-24.04
```

Then:

```sh
cd ~/Projects/aiMoney
source .venv/bin/activate
python -m pip install -r requirements.txt
python frontend/build.py
python dashboard_server.py
```

Open http://localhost:8765/covered-call-optimizer from Windows. Run only
one dashboard server on port 8765; stop it with Ctrl+C when running interactively.
For the initial background server, its PID is in `reports/dashboard-server.pid`
and logs are in `reports/dashboard-server.stdout.log` and
`reports/dashboard-server.stderr.log`. Stop that process before starting an
interactive server.

The initial background server can be stopped from WSL with:

```sh
kill "$(cat reports/dashboard-server.pid)"
```

Use VS Code's WSL extension to open the Linux directory, or browse it at
`\\wsl.localhost\Ubuntu-24.04\home\amanlig\Projects\aiMoney` from Windows.
The old `C:\KodeKomplete\Projects\aiMoney` directory is a separate copy and does
not automatically synchronize with this workspace. Edit and commit in WSL.

The API uses FastAPI and Uvicorn; `.venv/` isolates the pinned dependencies.
See [DOCKER.md](DOCKER.md) for container startup. Docker Desktop must enable WSL
integration for this distribution before running Compose. React dependencies are vendored locally. Credentials stay
in `.secrets/`; the directory must be mode `700`, and `questrade.json` mode `600`.
Keep this workspace on the Linux filesystem so Unix permissions work correctly.

Verification:

```sh
python -m unittest discover -s tests -p 'test_public_*.py'
python -m unittest discover -s models/financials/covered_call_exit/tests
node tests/test_public_calculations.js
```

Browser contracts require the optional Playwright package and a Linux Chromium
executable; set `CHROME_PATH` to its path. They are not required to run the app.
