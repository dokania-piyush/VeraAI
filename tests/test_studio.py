from scripts.fixtures import demo_cases
from fastapi.testclient import TestClient
from vera.api import create_app
from vera.config import Settings


def test_preview_auth_and_no_persistence(tmp_path):
    with TestClient(create_app(Settings(db_path=str(tmp_path/'studio.sqlite3'),admin_token='test-admin'))) as c:
        fixture=next(iter(demo_cases().values()))
        assert c.post('/debug/preview',json=fixture).status_code==401
        h={'Authorization':'Bearer test-admin'}
        r=c.post('/debug/preview',json=fixture,headers=h)
        assert r.status_code==200 and '₹499' in r.json()['body']
        fixture['merchant']['offers'][0]['title']='Hair Spa @ ₹599'
        r=c.post('/debug/preview',json=fixture,headers=h)
        assert '₹599' in r.json()['body'] and '₹499' not in r.json()['body']
        state=c.get('/debug/state',headers=h).json()
        assert sum(state['counts'].values())==0
        assert c.get('/studio').status_code==200
        assert c.get('/assets/app.js').status_code==200


def test_preview_revoked_consent(tmp_path):
    with TestClient(create_app(Settings(db_path=str(tmp_path/'studio.sqlite3'),admin_token='test-admin'))) as c:
        fixture=demo_cases()['Consent-aware customer reminder'];fixture['customer']['consent']['revoked_at']=fixture['now']
        result=c.post('/debug/preview',json=fixture,headers={'Authorization':'Bearer test-admin'}).json()
        assert result['decision']=='skip' and result['reason']=='consent_revoked'


def test_env_loader_does_not_execute_or_override(tmp_path,monkeypatch):
    from scripts.run import load_env
    file=tmp_path/'.env';file.write_text('HELLO="hello world"\nEXISTING=wrong\nNOEXEC=$(danger)\n',encoding='utf-8')
    monkeypatch.setenv('EXISTING','preserved');monkeypatch.delenv('HELLO',raising=False);monkeypatch.delenv('NOEXEC',raising=False)
    load_env(file)
    import os
    assert os.environ['HELLO']=='hello world' and os.environ['NOEXEC']=='$(danger)' and os.environ['EXISTING']=='preserved'
    monkeypatch.delenv('HELLO');monkeypatch.delenv('NOEXEC')
