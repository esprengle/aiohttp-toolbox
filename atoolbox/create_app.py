import asyncio
import logging
from typing import Optional

from aiohttp import ClientSession, ClientTimeout, web
from aiohttp_session import session_middleware
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from arq import create_pool_lenient
from buildpg import asyncpg
from cryptography import fernet

from .db import prepare_database
from .logs import setup_logging
from .middleware import csrf_middleware, error_middleware, pg_middleware
from .settings import BaseSettings

logger = logging.getLogger('atoolbox.web')


async def startup(app: web.Application):
    settings: Optional[BaseSettings] = app['settings']
    # if pg is already set the database doesn't need to be created
    if hasattr(settings, 'pg_dsn') and 'pg' not in app:
        await prepare_database(settings, False)
        app['pg'] = await asyncpg.create_pool_b(dsn=settings.pg_dsn, min_size=2)

    if hasattr(settings, 'redis_settings'):
        app['redis'] = await create_pool_lenient(settings.redis_settings, app.loop)

    app['http_client'] = ClientSession(timeout=ClientTimeout(total=settings.http_client_timeout), loop=app.loop)


async def cleanup(app: web.Application):
    close_coros = [app['http_client'].close()]

    redis = app.get('redis')
    if redis and not redis.closed:
        redis.close()
        close_coros.append(redis.wait_closed())

    pg = app.get('pg')
    if pg:
        close_coros.append(pg.close())

    await asyncio.gather(*close_coros)

    logging_client = app['logging_client']
    transport = logging_client and logging_client.remote.get_transport()
    transport and await transport.close()


async def create_default_app(*, settings: BaseSettings = None, logging_client=None, middleware=None, routes=None):
    logging_client = logging_client or setup_logging()

    middleware = middleware or (
        session_middleware(EncryptedCookieStorage(settings.auth_key, cookie_name=settings.cookie_name)),
        error_middleware,
        pg_middleware,
        csrf_middleware,
    )

    kwargs = {}
    if hasattr(settings, 'max_request_size'):
        kwargs['client_max_size'] = settings.max_request_size

    app = web.Application(logger=None, middlewares=middleware, **kwargs)

    app.update(settings=settings, logging_client=logging_client)
    if hasattr(settings, 'auth_key'):
        app['auth_fernet'] = fernet.Fernet(settings.auth_key)

    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)
    if routes:
        app.add_routes(routes)
    return app
