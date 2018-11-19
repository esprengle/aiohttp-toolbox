import asyncio

import pytest
from aiohttp.test_utils import teardown_test_loop
from aioredis import create_redis
from buildpg import asyncpg

from aiohttptools.db import prepare_database
from aiohttptools.db.helpers import SimplePgPool
from demo.main import create_app
from demo.settings import Settings

settings_args = dict(
    DATABASE_URL='postgres://postgres@localhost:5432/aiohttptools_test',
    redis_settings='redis://localhost:6379/6',
    create_app='demo.main.create_app',
    sql_path='demo/models.sql',
)


@pytest.fixture(scope='session', name='settings')
def _fix_settings():
    return Settings(**settings_args)


@pytest.fixture(scope='session', name='clean_db')
def _fix_clean_db(request, settings):
    # loop fixture has function scope so can't be used here.
    loop = asyncio.new_event_loop()
    loop.run_until_complete(prepare_database(settings, True))
    teardown_test_loop(loop)


@pytest.fixture(name='db_conn')
async def _fix_db_conn(loop, settings, clean_db):
    conn = await asyncpg.connect_b(dsn=settings.pg_dsn, loop=loop)

    tr = conn.transaction()
    await tr.start()

    yield conn

    await tr.rollback()
    await conn.close()


@pytest.yield_fixture
async def redis(loop, settings):
    addr = settings.redis_settings.host, settings.redis_settings.port
    redis = await create_redis(addr, db=settings.redis_settings.database, loop=loop)
    await redis.flushdb()

    yield redis

    redis.close()
    await redis.wait_closed()


async def pre_startup_app(app):
    app['pg'] = SimplePgPool(app['test_conn'])


@pytest.fixture(name='cli')
async def _fix_cli(settings, db_conn, aiohttp_client, redis):
    app = await create_app(settings=settings)
    app['test_conn'] = db_conn
    app.on_startup.insert(0, pre_startup_app)
    cli = await aiohttp_client(app)
    return cli
