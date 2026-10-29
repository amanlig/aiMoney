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

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

import fx_samples
import option_premiums
import option_rollovers
import closed_holdings
import covered_positions
import holding_records
import transaction_report
import stock_basis
import exit_optimizer
import optimizer_recommendations
import optimizer_assessments
from macro_data import usd_cad
from roll_candidates import INPUTS, SYMBOLS, output_path
from authentication import Authentication, COOKIE, RateLimited

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
    position_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32,64}$')


class SignInRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    email: str = Field(min_length=3, max_length=254)


class VerifySignInRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    challenge_id: str = Field(min_length=20, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')
    code: str = Field(pattern=r'^[0-9]{8}$')
    remember: bool = False


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


def create_app(*, refresh_macro=True, auth_enabled=None, auth_service=None):
    authentication_enabled = (os.environ.get('APP_AUTH_ENABLED', '0') == '1'
                              if auth_enabled is None else auth_enabled)

    @asynccontextmanager
    async def lifespan(app):
        if authentication_enabled:
            app.state.auth = auth_service or Authentication()
            # Missing migrations/configuration stop startup; never bypass authentication.
            with app.state.auth.connection() as db:
                for table in ('app_users', 'auth_challenges', 'auth_sessions', 'auth_rate_limits'):
                    db.execute(f'SELECT 1 FROM {table} LIMIT 1')
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

    def finish(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.middleware('http')
    async def request_boundary(request, call_next):
        public = request.url.path in {
            '/signin', '/api/auth/session', '/api/auth/request-code', '/api/auth/verify', '/api/health',
            '/profile_settings.js',
        } or request.url.path.startswith('/frontend/dist/')
        if authentication_enabled and not public:
            try:
                user = await run_in_threadpool(app.state.auth.session, request.cookies.get(COOKIE))
            except (psycopg.Error, sqlite3.Error, OSError):
                return finish(JSONResponse({'error': 'Sign-in is temporarily unavailable.'}, status_code=503))
            if not user:
                response = (JSONResponse({'error': 'Sign in to continue.'}, status_code=401)
                            if request.url.path.startswith('/api/') or request.url.path == '/openapi.json'
                            else RedirectResponse('/signin', status_code=303))
                return finish(response)
            request.state.user = user
        if request.url.path.startswith('/api/') and request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            try:
                request._body = await bounded_request(request)
            except HTTPException as error:
                return finish(JSONResponse({'error': error.detail}, status_code=error.status_code))
        response = await call_next(request)
        return finish(response)

    def client_ip(request):
        # Caddy overwrites this header; the cloud API publishes no host port.
        if os.environ.get('AUTH_TRUST_PROXY') == '1':
            return request.headers.get('x-aimoney-client-ip', 'unknown')[:64]
        return request.client.host if request.client else 'unknown'

    @app.get('/api/auth/session')
    def auth_session(request: Request):
        if not authentication_enabled:
            return {'enabled': False}
        user = app.state.auth.session(request.cookies.get(COOKIE))
        if not user:
            raise HTTPException(401, 'Sign in to continue.')
        return {'enabled': True, 'email': user['email']}

    @app.post('/api/auth/request-code')
    def request_code(body: SignInRequest, request: Request, tasks: BackgroundTasks):
        if not authentication_enabled:
            raise HTTPException(404, 'Email sign-in is not enabled.')
        try:
            challenge, delivery = app.state.auth.request_code(body.email, client_ip(request))
        except RateLimited:
            raise HTTPException(429, 'Please wait before requesting another code.') from None
        if delivery:
            tasks.add_task(app.state.auth.deliver, *delivery)
        return {'challenge_id': challenge,
                'message': 'If your email is authorized, a code will arrive shortly. It expires in 10 minutes.'}

    @app.post('/api/auth/verify')
    def verify_code(body: VerifySignInRequest, request: Request):
        if not authentication_enabled:
            raise HTTPException(404, 'Email sign-in is not enabled.')
        try:
            result = app.state.auth.verify(body.challenge_id, body.code, body.remember, client_ip(request))
        except RateLimited:
            raise HTTPException(429, 'Too many attempts. Try again later.') from None
        if not result:
            raise HTTPException(400, 'Invalid or expired code. Request a new code if needed.')
        token, email, ttl = result
        response = JSONResponse({'email': email})
        response.set_cookie(COOKIE, token, max_age=ttl if body.remember else None,
                            secure=True, httponly=True, samesite='lax', path='/')
        return response

    @app.post('/api/auth/logout')
    def logout(request: Request):
        if authentication_enabled:
            app.state.auth.logout(request.cookies.get(COOKIE))
        response = JSONResponse({'ok': True})
        response.delete_cookie(COOKIE, secure=True, httponly=True, samesite='lax', path='/')
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
        saved=exit_optimizer.load_capture(position.model_dump(exclude_none=True),root=ROOT)
        if saved is None: raise HTTPException(404, 'No saved analysis for this position.')
        return saved

    @app.post('/api/exit-optimizer/run')
    def run(body: RunRequest):
        return evaluate(body, exit_optimizer.run)

    @app.post('/api/exit-optimizer/scenario')
    def scenario(body: ScenarioRequest):
        return evaluate(body, exit_optimizer.scenario)

    def evaluate(body, operation):
        with serialized(ROLL_REFRESH_LOCK, 'A market-data refresh is already running.'):
            try:
                return operation(body.model_dump(exclude_none=True))
            except exit_optimizer.BrokerNotConfigured as error:
                raise HTTPException(503,str(error)) from None
            except exit_optimizer.StockHistoryUnavailable as error:
                raise HTTPException(502,str(error)) from None
            except (ValueError, TypeError):
                raise
            except Exception:
                raise HTTPException(502, 'Market data is unavailable. Try again or check the data-provider configuration.') from None

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
                return optimizer_recommendations.generate(body.model_dump(exclude_none=True))
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

    @app.post('/api/option-premiums/{record_id:int}/edit')
    def edit_premium(record_id: int, body: dict):
        return option_premiums.save(body, record_id=record_id)

    @app.get('/api/option-premiums/usd')
    def usd_premiums():
        return {'premiums': option_premiums.usd_records()}

    @app.post('/api/option-premiums/usd/{record_id:int}/edit')
    def edit_usd_premium(record_id: int, body: dict):
        return option_premiums.save_usd(body, record_id=record_id)

    @app.post('/api/option-premiums/usd', status_code=201)
    def save_usd_premium(body: dict):
        return option_premiums.save_usd(body)

    @app.get('/api/positions/availability')
    def position_availability():
        exit_optimizer.holdings(include_closed=True)
        return {'stocks': covered_positions.availability(exit_optimizer.inventory())}

    @app.post('/api/positions', status_code=201)
    def create_position(body: dict):
        existing=exit_optimizer.holdings(include_closed=True)
        template=next((h for h in existing if h['account']==body.get('account') and h['symbol']==body.get('symbol')),None)
        return covered_positions.create(body,exit_optimizer.inventory(),template)

    @app.post('/api/holdings',status_code=201)
    def new_stock_holding(body:dict):
        exit_optimizer.holdings(include_closed=True)
        return holding_records.create(body)

    @app.post('/api/positions/{position_id}/purchase')
    def update_holding_purchase(position_id:str,body:dict):
        return holding_records.update_purchase(position_id,body)

    @app.get('/api/positions/{position_id}/delete-preview')
    def holding_delete_preview(position_id:str):
        return holding_records.preview(position_id)

    @app.post('/api/positions/{position_id}/delete')
    def delete_holding(position_id:str,body:dict):
        with serialized(ROLL_REFRESH_LOCK,'Wait for the quote refresh to finish before deleting.'), serialized(ASSESSMENT_LOCK,'Wait for the recommendation to finish before deleting.'):
            return holding_records.delete(position_id,body,reports=ROOT/'reports')

    @app.post('/api/positions/{position_id}/allocation')
    def allocate_position(position_id: str,body: dict):
        return covered_positions.allocate(position_id,body.get('shares'),exit_optimizer.inventory())

    @app.get('/api/positions/{position_id}/history')
    def position_history_records(position_id: str):
        return covered_positions.history(position_id)

    @app.get('/api/positions/{position_id}/transactions')
    def position_transaction_report(position_id: str):
        return transaction_report.report(position_id)

    @app.post('/api/positions/{position_id}/opening', status_code=201)
    def create_position_opening(position_id: str,body: dict):
        return covered_positions.save_opening(position_id,body)

    @app.post('/api/positions/{position_id}/opening/edit')
    def edit_position_opening(position_id: str,body: dict):
        return covered_positions.save_opening(position_id,body,edit=True)

    @app.post('/api/positions/{position_id}/rollovers', status_code=201)
    def record_position_rollover(position_id: str,body: dict):
        return covered_positions.save_rollover(position_id,body)

    @app.get('/api/positions/{position_id}/expiration-preview')
    def expiration_preview(position_id: str):
        return covered_positions.expiration_preview(position_id)

    @app.post('/api/positions/{position_id}/expire-worthless', status_code=201)
    def expire_option_worthless(position_id: str,body: dict):
        return covered_positions.expire_worthless(position_id,body,retain_stock=True,raw=exit_optimizer.source_holdings())

    @app.get('/api/option-expirations')
    def option_expirations():
        return {'expirations':covered_positions.expirations()}

    @app.get('/api/closed-holdings')
    def closed_positions():
        return {'holdings': closed_holdings.records()}

    @app.post('/api/closed-holdings', status_code=201)
    def close_position(body: dict):
        # Seed legacy positions before taking the mutation lock.
        exit_optimizer.holdings(include_closed=True)
        with covered_positions.transaction() as db:
            row=covered_positions.get(db,body.get('position_key'),active=False)
            if covered_positions.is_expired(db,row['id']):
                raise ValueError('This call has expired worthless; its shares remain held.')
            holding=covered_positions.holding(row)
            try:
                reference=exit_optimizer.opening_reference(holding['account'],holding['symbol'],
                    dict(expiry=holding['call_expiry'],strike=holding['call_strike_native_currency']),
                    holding['shares'],holding['call_contracts'],holding['position_id'],transaction=db)
            except ValueError:
                reference=dict(history_status='incomplete',history_note='Stock purchase or linked option history is unavailable; realized P/L cannot be calculated.',historical_option_net_usd=None,stock_cost_usd=None)
            reference['closing_quote_snapshot']=exit_optimizer.closing_quote_snapshot(holding,body.get('quote_captured_at'))
            return closed_holdings.save(body,holding,reference,transaction=db)

    @app.get('/api/option-rollovers')
    def rollovers():
        return {'rollovers': option_rollovers.records()}

    @app.post('/api/option-rollovers', status_code=201)
    def save_rollover(body: dict):
        return option_rollovers.save(body)

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

    @app.get('/signin', include_in_schema=False)
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
