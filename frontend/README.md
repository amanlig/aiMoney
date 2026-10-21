# React dashboard

The home page and optimizer are React components. All runtime dependencies are
pinned and vendored locally: React / React DOM 19.2.0 (MIT) and HTM 3.1.1
(Apache-2.0).
HTM provides tagged HTML templates compiled to React elements at runtime; no
JSX compilation, CDN, Node installation or package download is needed to run.

From the repository root:

```sh
python -m pip install -r requirements.txt
python frontend/build.py
python dashboard_server.py
```

Open http://localhost:8765/covered-call-optimizer. `/` and `/index.html`
render the React home page. Rebuild after changing `frontend/src/` or
`frontend/vendor/`. The checked-in distribution lets an existing installation
start the Python server immediately.

`src/App.js` owns holdings, captured baseline, scenario requests and UI state.
`src/Chart.js` renders the cash-flow SVG and per-roll controls through React.
`src/Settings.js` owns the profile dialog and both opening-premium forms.
`src/Recommendations.js` owns explicit assessment generation and saved history.
`src/api.js` centralizes JSON requests. The existing pure `profile_settings.js`
cost-basis calculation is shared with the archived interface.

FastAPI serves the built assets through explicit routes. React loads all position
data, including saved captures, from `/api/` endpoints. Docker can serve the UI and
API together; see [Docker setup](../DOCKER.md). Broker authentication,
pricing, ranking, SQLite and OpenAI calls stay in the existing Python services.
Mounting the UI reads saved data only; refresh and assessment generation require
button clicks. Captured Close today is retained during hypothetical scenarios.

Dependency sources: `https://esm.sh/react@19.2.0/es2022/react.bundle.mjs`,
`https://esm.sh/react-dom@19.2.0/es2022/client.bundle.mjs?external=react`,
`https://esm.sh/htm@3.1.1/es2022/htm.mjs`. Licenses are in `vendor/`.

Browser contracts use synthetic API responses and the actual Python asset routes:

```sh
python -m pip install -r requirements-dev.txt
python -m pip install playwright
python -m playwright install chromium
python -m unittest discover -s tests -p test_react_dashboard.py
```

Tests start the FastAPI app under Uvicorn with the macro refresh disabled.
They use `CHROME_PATH`, an installed Chromium/Chrome, or Playwright's Chromium. Tests never call Questrade or OpenAI.
