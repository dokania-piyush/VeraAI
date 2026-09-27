from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
import pytest
from fastapi.testclient import TestClient
from vera.api import create_app
from vera.config import Settings
from vera.models import Action
from conftest import push, load, tick, reply, NOW


def test_health_metadata(client):
    assert client.get('/v1/healthz').json()['contexts_loaded'] == dict(category=0, merchant=0, customer=0, trigger=0)
    assert 'no LLM' in client.get('/v1/metadata').json()['model']


def test_version_noop_stale_replacement(client, data):
    a = push(client, 'merchant', data['merchant'], 2)
    changed = deepcopy(data['merchant']); changed['offers'] = []
    assert push(client, 'merchant', changed, 2).json() == a.json()
    assert push(client, 'merchant', changed, 1).status_code == 409
    assert push(client, 'merchant', changed, 3).status_code == 200
    stored = client.app.state.service._context('merchant', 'm1')
    assert stored['payload']['offers'] == []
    assert stored['version'] == 3


@pytest.mark.parametrize('mutation', [
    {'scope': 'invalid'}, {'version': 0}, {'version': True}, {'version': '1'},
    {'payload': []}, {'context_id': ''}, {'delivered_at': 'nonsense'},
    {'delivered_at': '2026-04-26T10:00:00'}, {'extra': 'not_allowed'},
])
def test_bad_envelopes(client, mutation):
    body = {'scope': 'merchant', 'context_id': 'm1', 'version': 1, 'payload': {}, 'delivered_at': NOW}
    body.update(mutation)
    assert client.post('/v1/context', json=body).status_code == 400


@pytest.mark.parametrize('field,value', [('identity', []), ('offers', [3]), ('performance', None), ('signals', 'wrong'), ('conversation_history', 7)])
def test_bad_payload_shapes(client, data, field, value):
    data['merchant'][field] = value
    assert push(client, 'merchant', data['merchant']).status_code == 400


def test_missing_inner_id_normalized(client):
    assert push(client, 'category', {'voice': {}}, cid='salons').status_code == 200
    assert client.app.state.service._context('category', 'salons')['payload']['slug'] == 'salons'


def test_mismatched_inner_id(client, data):
    assert push(client, 'merchant', data['merchant'], cid='different').status_code == 400


def test_empty_unknown_tick(client):
    assert tick(client, ['unknown']).json() == {'actions': []}
    assert tick(client, []).json() == {'actions': []}


def test_tick_contract_and_suppression(client, data):
    load(client, data)
    actions = tick(client).json()['actions']
    assert len(actions) == 1
    Action.model_validate(actions[0])
    assert '20%' in actions[0]['body']
    assert actions[0]['send_as'] == 'vera'
    assert tick(client).json()['actions'] == []


def test_explicit_tick_retry_receipt(client, data):
    load(client, data)
    h = {'Idempotency-Key': 'retry1'}
    a = tick(client, headers=h).json()
    assert a['actions']
    assert tick(client, headers=h).json() == a
    assert tick(client, [], headers=h).status_code == 409


def test_concurrent_tick_exactly_one_delivery(client, data):
    load(client, data)
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: tick(client), range(20)))
    assert all(r.status_code == 200 for r in responses)
    assert sum(len(r.json()['actions']) for r in responses) == 1


def test_same_suppression_different_recipient(client, data):
    load(client, data)
    other = deepcopy(data['merchant']); other['merchant_id'] = 'm2'
    push(client, 'merchant', other)
    other_t = deepcopy(data['trigger']); other_t.update(id='t2', merchant_id='m2')
    push(client, 'trigger', other_t)
    assert len(tick(client, ['t1', 't2']).json()['actions']) == 2


def test_one_recipient_per_tick_priority(client, data):
    load(client, data)
    review = deepcopy(data['trigger']); review.update(id='t2', kind='review_theme_emerged', suppression_key='review')
    review['payload'] = {'theme': 'delivery_late', 'occurrences_30d': 4}
    push(client, 'trigger', review)
    actions = tick(client, ['t1', 't2']).json()['actions']
    assert len(actions) == 1 and actions[0]['trigger_id'] == 't2'


def test_twenty_action_cap(client, data):
    push(client, 'category', data['category'])
    ids = []
    for i in range(25):
        m = deepcopy(data['merchant']); m['merchant_id'] = f'm{i}'
        t = deepcopy(data['trigger']); t.update(id=f't{i}', merchant_id=f'm{i}')
        push(client, 'merchant', m); push(client, 'trigger', t); ids.append(t['id'])
    assert len(tick(client, ids).json()['actions']) == 20


def test_customer_sender(client, data):
    data['trigger'].update(scope='customer', customer_id='c1', kind='recall_due', payload={'due_date': '2026-05-05', 'service_due': 'cleaning'})
    load(client, data)
    a = tick(client).json()['actions'][0]
    assert a['send_as'] == 'merchant_on_behalf' and a['customer_id'] == 'c1'
    assert '₹499' not in a['body']  # recall consent does not imply offer eligibility


def test_payload_limit(client):
    response = client.post('/v1/context', content=b' ' * 512001, headers={'Content-Type': 'application/json'})
    assert response.status_code == 413


def test_bad_json(client):
    assert client.post('/v1/context', content=b'{bad', headers={'Content-Type': 'application/json'}).status_code == 400


def test_nested_depth(client):
    p = {}
    for _ in range(28): p = {'inner': p}
    assert push(client, 'merchant', p, cid='m1').status_code == 400


def test_auth_boundary(data):
    with TestClient(create_app(Settings(db_path=':memory:', api_token='secret'))) as c:
        assert c.get('/v1/healthz').status_code == 200
        assert push(c, 'merchant', data['merchant']).status_code == 401
        assert tick(c, headers={'Authorization': 'Bearer secret'}).status_code == 200
        assert 'secret' not in c.get('/v1/metadata').text
        assert c.get('/debug/traces').status_code == 404


def test_admin_protected(client, data):
    load(client, data); tick(client)
    assert client.get('/debug/traces').status_code == 401
    r = client.get('/debug/traces', headers={'Authorization': 'Bearer test-admin'})
    assert r.status_code == 200 and r.json()['traces']
    assert r.json()['traces'][0]['evidence']['source_values_match']
    assert client.get('/debug/traces?limit=1000', headers={'Authorization': 'Bearer test-admin'}).status_code == 400


def test_teardown_erases_all(client, data):
    load(client, data); tick(client)
    assert client.post('/v1/teardown').json() == {'wiped': True}
    state = client.get('/debug/state', headers={'Authorization': 'Bearer test-admin'}).json()
    assert all(n == 0 for n in state['counts'].values())
    assert all(n == 0 for n in client.get('/v1/healthz').json()['contexts_loaded'].values())


def test_restart_persists_context_and_suppression(tmp_path, data):
    settings = Settings(db_path=str(tmp_path/'db.sqlite'))
    with TestClient(create_app(settings)) as c:
        load(c, data); assert tick(c).json()['actions']
    with TestClient(create_app(settings)) as c:
        assert c.get('/v1/healthz').json()['contexts_loaded']['merchant'] == 1
        assert tick(c).json()['actions'] == []
