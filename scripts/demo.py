"""End-to-end synthetic demo against a running local or explicitly permitted URL."""
import argparse
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import os
import httpx
from scripts.fixtures import demo_cases
from vera.timeutil import timestamp,iso


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',default='http://127.0.0.1:8080')
    p.add_argument('--token',default=os.getenv('VERA_API_TOKEN',''))
    p.add_argument('--reset',action='store_true',help='Explicitly erase server state first; never run against an active evaluation')
    p.add_argument('--out',type=Path,default=Path('reports/demo-transcript.json'))
    args=p.parse_args()
    headers={'Authorization':'Bearer '+args.token} if args.token else {}
    events=[]
    with httpx.Client(base_url=args.url.rstrip('/'),headers=headers,timeout=10,trust_env=False) as c:
        def post(path,body=None):
            r=c.post(path,json=body) if body is not None else c.post(path)
            r.raise_for_status();value=r.json();events.append({'endpoint':path,'request':body,'response':value});return value
        if args.reset:post('/v1/teardown')
        fixture=deepcopy(next(iter(demo_cases().values())))
        now=fixture['now']
        def push(scope,obj,version=1):
            fid={'category':'slug','merchant':'merchant_id','customer':'customer_id','trigger':'id'}[scope]
            return post('/v1/context',{'scope':scope,'context_id':obj[fid],'version':version,'payload':obj,'delivered_at':now})
        for scope in ('category','merchant','trigger'):push(scope,fixture[scope])
        a=post('/v1/tick',{'now':now,'available_triggers':[fixture['trigger']['id']]})['actions']
        if not a:raise SystemExit('No action: this demo may already exist. Use --reset only on your dedicated demo instance.')
        print('INITIAL:',a[0]['body'])
        fixture['merchant']['offers'][0]['title']='Hair Spa @ ₹599';push('merchant',fixture['merchant'],2)
        conv=a[0]['conversation_id']
        def reply(message,turn):
            return post('/v1/reply',{'conversation_id':conv,'merchant_id':fixture['merchant']['merchant_id'],'customer_id':None,'from_role':'merchant','message':message,'received_at':iso(timestamp(now)+timedelta(minutes=5+turn)),'turn_number':turn})
        yes=reply('Yes, send me the draft',2)
        print('AFTER PRICE UPDATE + YES:',yes.get('body',yes))
        assert '₹599' in yes.get('body','') and '₹499' not in yes.get('body','')
        stop=reply('Stop messaging me',3);assert stop['action']=='end';print('STOP:',stop)
        fixture['trigger'].update(id='demo_after_stop',suppression_key='demo:new-after-stop')
        push('trigger',fixture['trigger'])
        blocked=post('/v1/tick',{'now':iso(timestamp(now)+timedelta(hours=2)),'available_triggers':['demo_after_stop']})
        assert blocked['actions']==[];print('NEW TRIGGER AFTER STOP:',blocked)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps({'synthetic':True,'events':events},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Transcript:',args.out)

if __name__=='__main__':main()
