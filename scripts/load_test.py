"""Paced local HTTP workload. Never run against an active judge session.

Writes synthetic context/reply records; permits only loopback URLs unless an
explicit --allow-remote flag is passed. No paid API calls in default bot mode.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import statistics
import time
import uuid
from urllib.parse import urlsplit
import httpx
from scripts.fixtures import demo_cases


def run(url: str, count: int, rate: float, token: str = '') -> dict:
    headers={'Authorization':'Bearer '+token} if token else {}
    fixture=next(iter(demo_cases().values()))
    run_id=uuid.uuid4().hex[:12]; mid='load_merchant_'+run_id; tid='load_trigger_'+run_id
    fixture['merchant']['merchant_id']=mid
    fixture['trigger'].update(id=tid,merchant_id=mid,suppression_key=tid)
    now=fixture['now'];latencies=[];errors=[];statuses={};start=time.perf_counter()
    def request(i):
        body=None
        if i%4==0:
            method,path='GET','/v1/healthz'
        elif i%4==1:
            method,path='POST','/v1/context'
            body={'scope':'merchant','context_id':mid,'version':1,'payload':fixture['merchant'],'delivered_at':now}
        elif i%4==2:
            method,path='POST','/v1/tick';body={'now':now,'available_triggers':[tid]}
        else:
            method,path='POST','/v1/reply';body={'conversation_id':f'load_{run_id}_{i}','merchant_id':mid,'from_role':'merchant','message':'What is the price?','received_at':now,'turn_number':1}
        t=time.perf_counter()
        try:
            r=client.request(method,path,json=body)
            return i,r.status_code,(time.perf_counter()-t)*1000,None if r.status_code==200 else r.text[:200]
        except httpx.HTTPError as e:
            return i,0,(time.perf_counter()-t)*1000,type(e).__name__
    with httpx.Client(base_url=url.rstrip('/'),headers=headers,timeout=10,trust_env=False) as client:
        for scope in ('category','merchant','trigger'):
            obj=fixture[scope];key={'category':'slug','merchant':'merchant_id','trigger':'id'}[scope]
            r=client.post('/v1/context',json={'scope':scope,'context_id':obj[key],'version':1,'payload':obj,'delivered_at':now});r.raise_for_status()
        start=time.perf_counter()
        with ThreadPoolExecutor(max_workers=20) as pool:
            futures=[]
            for i in range(count):
                delay=start+i/rate-time.perf_counter()
                if delay>0:time.sleep(delay)
                futures.append(pool.submit(request,i))
            for f in futures:
                i,status,latency,error=f.result();latencies.append(latency);statuses[str(status)]=statuses.get(str(status),0)+1
                if error:errors.append({'request':i,'status':status,'error':error})
    ordered=sorted(latencies)
    return {'label':'Local HTTP engineering workload, not a deployment SLA or message-quality score','requests':count,'target_requests_per_second':rate,'elapsed_seconds':round(time.perf_counter()-start,3),'mix':['health','context_noop','tick','reply'],'status_counts':statuses,'errors':errors,'latency_ms':{'median':round(statistics.median(ordered),3),'p95':round(ordered[min(len(ordered)-1,int(.95*len(ordered)))],3),'max':round(max(ordered),3)}}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',default='http://127.0.0.1:8080');p.add_argument('--requests',type=int,default=120);p.add_argument('--rate',type=float,default=10)
    p.add_argument('--allow-remote',action='store_true');p.add_argument('--out',type=Path,default=Path('reports/http-load.json'));p.add_argument('--token',default=os.getenv('VERA_API_TOKEN',''))
    a=p.parse_args()
    if urlsplit(a.url).hostname not in {'127.0.0.1','localhost','::1'} and not a.allow_remote:p.error('Refusing remote writes without --allow-remote')
    if not 1<=a.requests<=5000 or not 0<a.rate<=100:p.error('requests must be 1..5000; rate must be (0,100]')
    result=run(a.url,a.requests,a.rate,a.token);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    raise SystemExit(bool(result['errors']))

if __name__=='__main__':main()
