import pytest

from atoolbox.network import async_check_server, async_wait_port_open, check_server, wait_for_services


def test_wait_for_services(settings, loop):
    assert 2 == wait_for_services(settings)


async def test_wait_for_services_not_open(loop):
    with pytest.raises(RuntimeError):
        await async_wait_port_open('localhost', 9876, 0.1, loop=loop)


def test_wait_for_services_no_services(settings, loop):
    settings.pg_dsn = None
    settings.redis_settings = None
    assert 0 == wait_for_services(settings)


def test_check_server_ok(dummy_server, loop):
    assert 0 == check_server(dummy_server.server_name + '/status/200/', 200)


async def test_check_server_fail(dummy_server, loop):
    assert 1 == await async_check_server(dummy_server.server_name + '/status/500/', 200, loop)
