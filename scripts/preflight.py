"""Read-only public deployment checks. Does not seed or erase evaluation data."""
import argparse
import json
import os
import sys
import time
import httpx


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',default='http://127.0.0.1:8080')
    p.add_argument('--token',default=os.getenv('VERA_API_TOKEN',''))
    p.add_argument('--submission',action='store_true',help='Require HTTPS and non-placeholder metadata')
    args=p.parse_args();checks=[]
    headers={'Authorization':'Bearer '+args.token} if args.token else {}
    with httpx.Client(base_url=args.url.rstrip('/'),headers=headers,timeout=10,follow_redirects=False,trust_env=False) as c:
        for path in ['/v1/healthz','/v1/metadata']:
            start=time.perf_counter()
            try:
                response=c.get(path);response.raise_for_status();body=response.json()
                checks.append({'path':path,'ok':True,'latency_ms':round((time.perf_counter()-start)*1000,2),'body':body})
            except (httpx.HTTPError,ValueError) as e:
                checks.append({'path':path,'ok':False,'error':type(e).__name__})
        if args.submission:
            checks.append({'check':'https','ok':args.url.startswith('https://')})
            meta=next((x.get('body',{}) for x in checks if x.get('path')=='/v1/metadata'),{})
            checks.append({'check':'real_metadata','ok':bool(meta.get('contact_email')) and 'SET_YOUR' not in json.dumps(meta) and len(meta.get('team_members',[]))==1})
    print(json.dumps({'checks':checks,'note':'Read-only preflight does not replace behavioral tests or confirm hidden judge quality.'},indent=2))
    sys.exit(0 if all(x['ok'] for x in checks) else 1)

if __name__=='__main__':main()
