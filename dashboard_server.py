"""FastAPI boundary for the React dashboard and existing application services."""
import argparse
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import psycopg
import subprocess
import sys
import threading
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

import fx_samples
import option_premiums
import stock_basis
import exit_optimizer
import optimizer_recommendations
import optimizer_assessments
from macro_data import usd_cad
from roll_candidates import INPUTS, SYMBOLS, output_path

ROOT = Path(__file__).resolve().parent
ROLL_REFRESH_LOCK = threading.Lock()
ASSESSMENT_LOCK = threading.Lock()


class MacroFeed:
    def __init__(self, path, interval=60):
        self.path, self.interval = path, interval
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.quote = None
        self.error = None
        self.attempted_at = None
        try:
            self.quote = json.loads(path.read_text())
        except (OSError, ValueError):
            pass

    def refresh(self):
        attempted = datetime.now(timezone.utc).isoformat()
        try:
            quote = usd_cad()
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(quote, indent=2))
            temporary.replace(self.path)
            with self.lock:
                self.quote, self.error, self.attempted_at = quote, None, attempted
        except (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError):
            with self.lock:
                self.error = 'Yahoo refresh failed; showing the last successful capture.'
                self.attempted_at = attempted

    def snapshot(self):
        with self.lock:
            return dict(quote=self.quote, error=self.error, attempted_at=self.attempted_at,
                        refresh_seconds=self.interval)

    def run(self):
        while not self.stop.is_set():
            self.refresh()
            self.stop.wait(self.interval)


class PositionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    account: Literal['LIRA', 'RRSP', 'TFSA']
    symbol: str = Field(min_length=1, max_length=16, pattern=r'^[A-Z0-9.\-]+$')


class RunRequest(PositionRequest):
    account: Literal['LIRA', 'RRSP', 'TFSA'] = 'RRSP'
    symbol: str = 'ASTS'
    horizon: int = Field(default=30, ge=1, le=63)


class ScenarioRequest(PositionRequest):
    stock_price: float = Field(gt=0, allow_inf_nan=False)


class RecommendationRequest(ScenarioRequest):
    goal: Literal['free_cash', 'reduce_risk', 'keep_exposure', 'compare']
    captured_at: str = Field(min_length=1, max_length=100)
    modes: dict[str, Literal['close', 'expire']] = Field(default_factory=dict)


class BasisRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    bases: list[dict]


class DeleteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: int = Field(gt=0)


class RollRequest(PositionRequest):
    account: Literal['LIRA', 'RRSP', 'TFSA'] = 'LIRA'
    symbol: str = 'QBTS'
    purchasePriceUsd: float | None = Field(default=None, gt=0, allow_inf_nan=False)


@contextmanager
def serialized(lock, message):
    if not lock.acquire(blocking=False):
        raise HTTPException(409, message)
    try:
        yield
    finally:
        lock.release()


async def bounded_request(request: Request):
    """Retain local-origin protection and bound actual bodies, including chunked uploads."""
    origin = request.headers.get('origin')
    host = urlsplit(str(request.base_url))
    allowed = {value.strip() for value in os.environ.get('APP_ALLOWED_ORIGINS', '').split(',') if value.strip()}
    if host.hostname in {'localhost', '127.0.0.1'}:
        allowed.add(f'{host.scheme}://{host.netloc}')
    if not origin or origin not in allowed:
        raise HTTPException(403, 'Use this dashboard origin.')
    limit = 8 * 1024 * 1024 if request.url.path.endswith('/ocr') else 2048 if request.url.path in {
        '/api/exit-optimizer/run', '/api/exit-optimizer/scenario', '/api/roll-candidates/refresh'
    } else 16384
    size = 0
    chunks = []
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, 'Request is too large (image limit: 8 MB).')
        chunks.append(chunk)
    if not size:
        raise HTTPException(400, 'Request body is empty.')
    return b''.join(chunks)


def create_app(*, refresh_macro=True):
    @asynccontextmanager
    async def lifespan(app):
        (ROOT/'data').mkdir(exist_ok=True)
        (ROOT/'reports').mkdir(exist_ok=True)
        feed = MacroFeed(ROOT/'reports/macro-data.json')
        app.state.feed = feed
        worker = threading.Thread(target=feed.run, daemon=True) if refresh_macro else None
        if worker:
            worker.start()
        try:
            yield
        finally:
            feed.stop.set()
            if worker:
                await run_in_threadpool(worker.join, 35)

    app = FastAPI(title='aiMoney API', version='1.0.0', lifespan=lifespan)

    @app.middleware('http')
    async def request_boundary(request, call_next):
        if request.url.path.startswith('/api/') and request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            try:
                request._body = await bounded_request(request)
            except HTTPException as error:
                return JSONResponse({'error': error.detail}, status_code=error.status_code)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, error):
        return JSONResponse({'error': error.detail}, status_code=error.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Do not echo request bodies or credential-shaped input in validation errors.
        issues = [dict(field='.'.join(map(str, item['loc'])), message=item['msg']) for item in error.errors()]
        return JSONResponse({'error': 'Invalid request.', 'issues': issues}, status_code=422)

    @app.exception_handler(ValueError)
    @app.exception_handler(TypeError)
    @app.exception_handler(KeyError)
    async def domain_error(request, error):
        return JSONResponse({'error': str(error)}, status_code=400)

    @app.exception_handler(psycopg.Error)
    @app.exception_handler(sqlite3.Error)
    @app.exception_handler(OSError)
    @app.exception_handler(subprocess.SubprocessError)
    async def storage_error(request, error):
        return JSONResponse({'error': 'Local storage or external service unavailable; previous records retained.'}, status_code=503)

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'service': 'aiMoney FastAPI'}

    @app.get('/api/macro')
    def macro(request: Request):
        return request.app.state.feed.snapshot()

    @app.get('/api/profile/holdings')
    def profile_holdings():
        from portfolio_data import account_widget
        try:
            return {'accounts': [account_widget(json.loads((ROOT/'data'/name).read_text())) for name in INPUTS.values()]}
        except (OSError, ValueError, KeyError, TypeError):
            raise HTTPException(503, 'Saved profile holdings unavailable.') from None

    @app.get('/api/exit-optimizer/holdings')
    def holdings():
        return {'holdings': exit_optimizer.holdings()}

    @app.get('/api/exit-optimizer/capture')
    def capture(position: Annotated[PositionRequest, Depends()]):
        path = ROOT/'reports'/f'exit-optimizer-{position.account.lower()}-{position.symbol.lower()}.json'
        if not path.is_file():
            raise HTTPException(404, 'No saved analysis for this holding.')
        return json.loads(path.read_text())

    @app.post('/api/exit-optimizer/run')
    def run(body: RunRequest):
        return evaluate(body, exit_optimizer.run)

    @app.post('/api/exit-optimizer/scenario')
    def scenario(body: ScenarioRequest):
        return evaluate(body, exit_optimizer.scenario)

    def evaluate(body, operation):
        with serialized(ROLL_REFRESH_LOCK, 'A market-data refresh is already running.'):
            try:
                return operation(body.model_dump())
            except (ValueError, TypeError):
                raise
            except Exception:
                raise HTTPException(502, 'Market data unavailable; check Questrade authorization and market-data access. Previous results retained.') from None

    @app.get('/api/optimizer-recommendations/status')
    def recommendation_status():
        return optimizer_assessments.status()

    @app.get('/api/optimizer-recommendations/history')
    def recommendation_history():
        return {'runs': optimizer_assessments.history()}

    @app.post('/api/optimizer-recommendations')
    def recommendation(body: RecommendationRequest):
        with serialized(ASSESSMENT_LOCK, 'A recommendation is already running.'):
            try:
                return optimizer_recommendations.generate(body.model_dump())
            except (ValueError, TypeError):
                raise
            except optimizer_assessments.AssessmentError as error:
                raise HTTPException(502, str(error)) from None
            except Exception:
                raise HTTPException(503, 'Recommendation unavailable. Check saved analysis and local storage.') from None

    @app.get('/api/stock-cost-basis')
    def bases():
        return {'bases': stock_basis.records()}

    @app.post('/api/stock-cost-basis')
    def save_bases(body: BasisRequest):
        return {'bases': stock_basis.save_many(body.bases)}

    @app.get('/api/option-premiums')
    def premiums():
        return {'premiums': option_premiums.records()}

    @app.post('/api/option-premiums', status_code=201)
    def save_premium(body: dict):
        return option_premiums.save(body)

    @app.get('/api/option-premiums/usd')
    def usd_premiums():
        return {'premiums': option_premiums.usd_records()}

    @app.post('/api/option-premiums/usd', status_code=201)
    def save_usd_premium(body: dict):
        return option_premiums.save_usd(body)

    @app.get('/api/fx-samples')
    def samples():
        return {'samples': fx_samples.records()}

    @app.post('/api/fx-samples', status_code=201)
    def save_sample(body: dict):
        return fx_samples.save(body)

    @app.post('/api/fx-samples/ocr')
    async def ocr(request: Request):
        return await run_in_threadpool(fx_samples.ocr, await request.body())

    @app.post('/api/fx-samples/delete')
    def delete_sample(body: DeleteRequest):
        with fx_samples.connect() as db:
            db.execute('DELETE FROM samples WHERE id=?', (body.id,))
        return {'deleted': body.id}

    @app.post('/api/roll-candidates/refresh')
    def roll_candidates(body: RollRequest):
        if body.account not in INPUTS or body.symbol not in SYMBOLS:
            raise HTTPException(400, 'Choose a supported account and stock.')
        with serialized(ROLL_REFRESH_LOCK, 'Candidate refresh already in progress'):
            command = [sys.executable, str(ROOT/'roll_candidates.py'), '--account', body.account, '--symbol', body.symbol]
            if body.purchasePriceUsd is not None:
                command += ['--purchase-price-usd', str(body.purchasePriceUsd)]
            try:
                subprocess.run(command, cwd=ROOT, check=True, timeout=90, capture_output=True)
                return json.loads(output_path(body.account, body.symbol).read_text())
            except (OSError, subprocess.SubprocessError):
                raise HTTPException(502, 'Questrade candidate refresh failed; previous capture retained') from None

    @app.get('/', include_in_schema=False)
    @app.get('/index.html', include_in_schema=False)
    @app.get('/covered-call-optimizer', include_in_schema=False)
    def react():
        return FileResponse(ROOT/'frontend/dist/index.html', media_type='text/html')

    @app.get('/investment-architecture.svg', include_in_schema=False)
    def architecture_diagram():
        return FileResponse(ROOT/'docs/physical-architecture.svg', media_type='image/svg+xml')

    @app.get('/equity-chart.html', include_in_schema=False)
    def legacy():
        return RedirectResponse('/covered-call-optimizer', status_code=302)

    @app.get('/archive/equity-chart.html', include_in_schema=False)
    def archived():
        path = ROOT/'archive/equity-dashboard/equity-chart.html'
        if not path.is_file():
            raise HTTPException(404, 'Archived dashboard not found')
        return FileResponse(path, media_type='text/html')

    @app.get('/profile_settings.js', include_in_schema=False)
    def profile_calculations():
        return FileResponse(ROOT/'profile_settings.js', media_type='text/javascript')

    @app.get('/frontend/dist/{folder}/{name}', include_in_schema=False)
    def asset(folder: str, name: str):
        if folder not in {'src', 'vendor'} or Path(name).name != name or Path(name).suffix not in {'.js', '.css'}:
            raise HTTPException(404, 'Asset not found')
        path = ROOT/'frontend/dist'/folder/name
        if not path.is_file():
            raise HTTPException(404, 'Asset not found')
        return FileResponse(path, media_type='text/css' if path.suffix == '.css' else 'text/javascript')

    return app


app = create_app()


def main():
    import uvicorn
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, workers=1)


if __name__ == '__main__':
    main()
