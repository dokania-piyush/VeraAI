"""Reproducible engineering evaluation, NOT an invented judge/quality score."""
import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import platform
import statistics
import time
from vera.composer import plan
from vera.policy import eligible,resolve_recipients
from vera.timeutil import timestamp
from scripts.fixtures import load_dataset,fixture_clock,ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path)
    parser.add_argument('--out',type=Path,default=ROOT/'reports'/'dataset-evaluation.json')
    args=parser.parse_args()
    d=load_dataset(args.dataset)
    cases=[]; timings=[]
    for tid,t in d['trigger'].items():
        mid,cid,err=resolve_recipients(t)
        m=d['merchant'].get(mid);c=d['customer'].get(cid) if cid else None
        cat=d['category'].get(m.get('category_slug')) if m else None
        now=fixture_clock(t)
        start=time.perf_counter()
        reason=err or ('missing_context' if not m or not cat else eligible(cat,m,t,c,timestamp(now)))
        result=plan(cat,m,t,c,timestamp(now)) if not reason else None
        choice=result.chosen if result else None
        if result and not choice:reason=result.reason
        elapsed=(time.perf_counter()-start)*1000;timings.append(elapsed)
        cases.append({'trigger_id':tid,'kind':t.get('kind'),'merchant_id':mid,'customer_id':cid,'clock':now,
                      'decision':'send' if choice else 'skip','reason':reason or choice.rationale,
                      'body':choice.body if choice else None,'pending':choice.pending if choice else None,
                      'evidence':result.book.report() if result else None,'latency_ms':round(elapsed,4)})
    ordered=sorted(timings)
    report={'label':'Engineering replay of supplied fixtures; no quality score or real-world outcome measured.',
            'python':platform.python_version(),'clock_mode':'explicit per-case historical simulation; source fixtures unchanged',
            'counts':{k:len(v) for k,v in d.items()},'kinds':len(set(x['kind'] for x in cases)),
            'decisions':dict(Counter(x['decision'] for x in cases)),
            'skip_reasons':dict(Counter(x['reason'] for x in cases if x['decision']=='skip')),
            'latency_ms':{'median':statistics.median(timings),'p95':ordered[min(len(ordered)-1,int(len(ordered)*.95))], 'max':max(timings)},
            'provenance_value_mismatches':sum(not x['evidence']['source_values_match'] for x in cases if x['evidence']),
            'live_llm_calls':0,'cases':cases}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='cases'},ensure_ascii=False,indent=2))
    print('Saved:',args.out)

if __name__=='__main__':main()
