import string

from buildpg import MultipleValues, Values
from pydantic import BaseModel
from pytest_toolbox.comparison import AnyInt

from atoolbox.bread import Bread


async def test_list_empty(cli):
    r = await cli.get('/orgs/')
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj == {'items': [], 'count': 0, 'pages': 0}


async def test_list_lots(cli, db_conn):
    orgs = [Values(name=f'Org {string.ascii_uppercase[i]}', slug=f'org-{i}') for i in range(7)]
    await db_conn.execute_b('INSERT INTO organisations (:values__names) VALUES :values', values=MultipleValues(*orgs))
    r = await cli.get('/orgs/')
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj == {
        'items': [
            {'id': AnyInt(), 'name': 'Org A', 'slug': 'org-0'},
            {'id': AnyInt(), 'name': 'Org B', 'slug': 'org-1'},
            {'id': AnyInt(), 'name': 'Org C', 'slug': 'org-2'},
            {'id': AnyInt(), 'name': 'Org D', 'slug': 'org-3'},
            {'id': AnyInt(), 'name': 'Org E', 'slug': 'org-4'},
        ],
        'count': 7,
        'pages': 2,
    }
    r = await cli.get('/orgs/?page=2')
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj == {
        'items': [
            {'id': AnyInt(), 'name': 'Org F', 'slug': 'org-5'},
            {'id': AnyInt(), 'name': 'Org G', 'slug': 'org-6'},
        ],
        'count': 7,
        'pages': 2,
    }


async def test_get(cli, db_conn):
    org_id = await db_conn.fetchval_b(
        'INSERT INTO organisations (:values__names) VALUES :values RETURNING id',
        values=Values(name='Test Org', slug='test-org'),
    )
    r = await cli.get(f'/orgs/{org_id}/')
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj == {'id': org_id, 'name': 'Test Org', 'slug': 'test-org'}


async def test_add(cli, db_conn):
    assert 0 == await db_conn.fetchval('SELECT COUNT(*) FROM organisations')
    r = await cli.post_json('/orgs/add/', dict(name='Test Org', slug='whatever'))
    assert r.status == 201, await r.text()
    assert 1 == await db_conn.fetchval('SELECT COUNT(*) FROM organisations')
    data = await r.json()
    org = dict(await db_conn.fetchrow('SELECT * FROM organisations'))
    assert data == {'status': 'ok', 'pk': org.pop('id')}
    assert org == {'name': 'Test Org', 'slug': 'whatever'}


async def test_edit(cli, db_conn):
    org_id = await db_conn.fetchval_b(
        'INSERT INTO organisations (:values__names) VALUES :values RETURNING id',
        values=Values(name='Test Org', slug='test-org'),
    )

    r = await cli.post_json(f'/orgs/{org_id}/', dict(name='Different'))
    assert r.status == 200, await r.text()
    data = await r.json()
    assert data == {'status': 'ok'}
    assert 1 == await db_conn.fetchval('SELECT COUNT(*) FROM organisations')
    org = dict(await db_conn.fetchrow('SELECT * FROM organisations'))
    assert org == {'id': org_id, 'name': 'Different', 'slug': 'test-org'}


async def test_edit_both(cli, db_conn):
    org_id = await db_conn.fetchval_b(
        'INSERT INTO organisations (:values__names) VALUES :values RETURNING id',
        values=Values(name='Test Org', slug='test-org'),
    )

    r = await cli.post_json(f'/orgs/{org_id}/', dict(name='x', slug='y'))
    assert r.status == 200, await r.text()
    data = await r.json()
    assert data == {'status': 'ok'}
    assert 1 == await db_conn.fetchval('SELECT COUNT(*) FROM organisations')
    org = dict(await db_conn.fetchrow('SELECT * FROM organisations'))
    assert org == {'id': org_id, 'name': 'x', 'slug': 'y'}


async def test_delete(cli, db_conn):
    org_id = await db_conn.fetchval_b(
        'INSERT INTO organisations (:values__names) VALUES :values RETURNING id',
        values=Values(name='Test Org', slug='test-org'),
    )

    r = await cli.post_json(f'/orgs/{org_id}/delete/')
    assert r.status == 200, await r.text()
    data = await r.json()
    assert data == {'message': f'Organisation {org_id} deleted', 'pk': org_id}
    assert 0 == await db_conn.fetchval('SELECT COUNT(*) FROM organisations')


async def test_add_edit_options(cli):
    r = await cli.options('/orgs/add/')
    assert r.status == 200, await r.text()
    obj_add = await r.json()
    assert obj_add == {
        'title': 'Model',
        'type': 'object',
        'properties': {
            'name': {'title': 'Name', 'type': 'string'},
            'slug': {'title': 'Slug', 'maxLength': 10, 'type': 'string'},
        },
        'required': ['name', 'slug'],
    }
    r = await cli.options('/orgs/123/')
    assert r.status == 200, await r.text()
    obj_edit = await r.json()
    assert obj_add == obj_edit


async def test_add_conflict(cli, db_conn):
    await db_conn.execute_b(
        'INSERT INTO organisations (:values__names) VALUES :values RETURNING id',
        values=Values(name='Test Org', slug='test-org'),
    )
    data = dict(name='Test Org', slug='test-org')
    r = await cli.post_json('/orgs/add/', data)
    assert r.status == 409, await r.text()
    obj = await r.json()
    assert obj == {
        'message': 'Conflict',
        'details': [
            {
                'loc': ['slug'],
                'msg': 'This value conflicts with an existing "slug", try something else.',
                'type': 'value_error.conflict',
            }
        ],
    }


async def test_update_conflict(cli, db_conn):
    orgs = [Values(name='Test Org 1', slug='test-org-1'), Values(name='Test Org 2', slug='test-org-2')]
    await db_conn.execute_b('INSERT INTO organisations (:values__names) VALUES :values', values=MultipleValues(*orgs))
    org_id = await db_conn.fetchval("select id from organisations where slug='test-org-2'")
    data = dict(slug='test-org-1')
    r = await cli.post_json(f'/orgs/{org_id}/', data)
    assert r.status == 409, await r.text()
    obj = await r.json()
    assert obj == {
        'message': 'Conflict',
        'details': [
            {
                'loc': ['slug'],
                'msg': 'This value conflicts with an existing "slug", try something else.',
                'type': 'value_error.conflict',
            }
        ],
    }


async def test_invalid_page(cli):
    r = await cli.get('/orgs/?page=-1')
    assert r.status == 400, await r.text()
    obj = await r.json()
    assert obj == {'message': "invalid page '-1'"}


async def test_add_invalid_data(cli, db_conn):
    r = await cli.post_json('/orgs/add/', dict(name='Test Org', slug='x' * 11))
    assert r.status == 400, await r.text()
    obj = await r.json()
    assert obj == {
        'message': 'Invalid Data',
        'details': [
            {
                'loc': ['slug'],
                'msg': 'ensure this value has at most 10 characters',
                'type': 'value_error.any_str.max_length',
                'ctx': {'limit_value': 10},
            }
        ],
    }
    assert 0 == await db_conn.fetchval('SELECT COUNT(*) FROM organisations')


async def test_add_invalid_json(cli, db_conn):
    r = await cli.post_json('/orgs/add/', '{"name": "Test Org", "slug": "foobar"')
    assert r.status == 400, await r.text()
    obj = await r.json()
    assert obj == {'message': 'Invalid JSON'}
    assert 0 == await db_conn.fetchval('SELECT COUNT(*) FROM organisations')


async def test_edit_no_data(cli, db_conn):
    org_id = await db_conn.fetchval_b(
        'INSERT INTO organisations (:values__names) VALUES :values RETURNING id',
        values=Values(name='Test Org', slug='test-org'),
    )

    r = await cli.post_json(f'/orgs/{org_id}/', dict())
    assert r.status == 400, await r.text()
    obj = await r.json()
    assert obj == {'message': 'no data to save'}


async def test_edit_invalid_json(cli, db_conn):
    org_id = await db_conn.fetchval_b(
        'INSERT INTO organisations (:values__names) VALUES :values RETURNING id',
        values=Values(name='Test Org', slug='test-org'),
    )

    r = await cli.post_json(f'/orgs/{org_id}/', 'xx')
    assert r.status == 400, await r.text()
    obj = await r.json()
    assert obj == {'message': 'Invalid JSON'}


async def test_edit_invalid_data(cli, db_conn):
    org_id = await db_conn.fetchval_b(
        'INSERT INTO organisations (:values__names) VALUES :values RETURNING id',
        values=Values(name='Test Org', slug='test-org'),
    )

    r = await cli.post_json(f'/orgs/{org_id}/', dict(slug='x' * 11))
    assert r.status == 400, await r.text()
    obj = await r.json()
    assert obj == {
        'message': 'Invalid Data',
        'details': [
            {
                'loc': ['slug'],
                'msg': 'ensure this value has at most 10 characters',
                'type': 'value_error.any_str.max_length',
                'ctx': {'limit_value': 10},
            }
        ],
    }


async def test_edit_not_dict(cli, db_conn):
    org_id = await db_conn.fetchval_b(
        'INSERT INTO organisations (:values__names) VALUES :values RETURNING id',
        values=Values(name='Test Org', slug='test-org'),
    )

    r = await cli.post_json(f'/orgs/{org_id}/', [1, 2, 3])
    assert r.status == 400, await r.text()
    obj = await r.json()
    assert obj == {'message': 'data not a dictionary'}


async def test_handler(cli):
    r = await cli.get('/orgs/?bad=1')
    assert r.status == 400, await r.text()
    obj = await r.json()
    assert obj == {'message': 'very bad'}


async def test_no_routes():
    class MyBread(Bread):
        class Model(BaseModel):
            name: str

        table = 'organisations'

    assert len(MyBread.routes('/')) == 0
