"""Original seed scenarios through actual HTTP routes, not only pure composition."""
from copy import deepcopy
from datetime import timedelta
import pytest
from scripts.fixtures import load_dataset, fixture_clock
from vera.timeutil import timestamp, iso
from vera.policy import resolve_recipients

DATA=load_dataset()


@pytest.mark.parametrize('tid',sorted(DATA['trigger']))
def test_original_seed_http_roundtrip(client,tid):
    t=deepcopy(DATA['trigger'][tid]);mid,cid,err=resolve_recipients(t);assert not err
    m=deepcopy(DATA['merchant'][mid]);cat=deepcopy(DATA['category'][m['category_slug']]);customer=deepcopy(DATA['customer'].get(cid)) if cid else None
    now=fixture_clock(t)
    for scope,obj,field in [('category',cat,'slug'),('merchant',m,'merchant_id'),('trigger',t,'id'),('customer',customer,'customer_id')]:
        if obj is None:continue
        r=client.post('/v1/context',json={'scope':scope,'context_id':obj[field],'version':1,'payload':obj,'delivered_at':now})
        assert r.status_code==200,r.text
    response=client.post('/v1/tick',json={'now':now,'available_triggers':[tid]})
    assert response.status_code==200,response.text
    actions=response.json()['actions']
    if not actions:
        records=client.app.state.store.items('traces')
        assert any(v.get('type')=='skips' and v.get('decisions') for _,v in records)
        return
    assert len(actions)==1
    action=actions[0];assert action['merchant_id']==mid and action['customer_id']==cid
    assert action['send_as']==('merchant_on_behalf' if cid else 'vera')
    assert action['body'].strip() and action['template_name']
    duplicate=client.post('/v1/tick',json={'now':now,'available_triggers':[tid]})
    assert duplicate.json()['actions']==[]
    req={'conversation_id':action['conversation_id'],'merchant_id':mid,'customer_id':cid,'from_role':'customer' if cid else 'merchant','message':'yes','received_at':iso(timestamp(now)+timedelta(minutes=1)),'turn_number':2}
    result=client.post('/v1/reply',json=req)
    assert result.status_code==200,result.text
    assert result.json()['action'] in ('send','end')
    assert client.post('/v1/reply',json=req).json()==result.json()
