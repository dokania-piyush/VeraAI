"""Explicit synthetic/historical fixture handling. Never preload into the server."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
from vera.timeutil import timestamp, iso

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'vendor'/'magicpin'/'dataset'


def load_dataset(directory: Path | None = None) -> dict:
    directory=directory or BASE
    categories={}
    for f in sorted((directory/'categories').glob('*.json')):
        obj=json.loads(f.read_text(encoding='utf-8'));categories[obj['slug']]=obj
    data={'category':categories}
    for plural,key in [('merchants','merchant_id'),('customers','customer_id'),('triggers','id')]:
        if (directory/plural).is_dir():
            records=[json.loads(f.read_text(encoding='utf-8')) for f in sorted((directory/plural).glob('*.json'))]
        else:
            records=json.loads((directory/f'{plural}_seed.json').read_text(encoding='utf-8'))[plural]
        data[plural[:-1]]={r[key]:r for r in records}
    return data


def fixture_clock(trigger: dict) -> str:
    """Per-case historical clock; actual ISO fields stay unchanged."""
    p=trigger.get('payload',{})
    for field,days in [('due_date',7),('wedding_date',30),('stock_runs_out_iso',1),('appointment_at',1),('match_time_iso',0)]:
        dt=timestamp(p.get(field))
        if dt:
            return iso(dt-timedelta(days=days,minutes=60 if field=='match_time_iso' else 0))
    return '2026-04-26T10:00:00Z'


def demo_cases() -> dict:
    """Clearly synthetic records, independent of the organizer's medical examples."""
    category={'slug':'salons','voice':{'tone':'warm_practical','vocab_taboo':['guaranteed glow']},'peer_stats':{'avg_ctr':.04},'digest':[]}
    merchant={'merchant_id':'demo_studio','category_slug':'salons','identity':{'name':'Mira Studio','owner_first_name':'Mira','languages':['en'],'verified':True},'performance':{'window_days':30,'views':1500,'calls':25,'ctr':.025,'delta_7d':{'calls_pct':-.2}},'offers':[{'id':'spa_offer','title':'Hair Spa @ ₹499','status':'active','started':'2026-01-01'}],'subscription':{'plan':'Pro','days_remaining':10}}
    trigger={'id':'demo_competitor','scope':'merchant','kind':'competitor_opened','merchant_id':'demo_studio','customer_id':None,'payload':{'competitor_name':'Nearby Example Salon','distance_km':1.3,'their_offer':'Hair Spa @ ₹399'},'urgency':2,'suppression_key':'demo:compete:1','expires_at':'2026-12-01T00:00:00Z'}
    price={'category':category,'merchant':merchant,'trigger':trigger,'customer':None,'now':'2026-09-27T10:00:00Z'}
    review=deepcopy(price);review['trigger'].update(id='demo_review',kind='review_theme_emerged',suppression_key='demo:review:1',payload={'theme':'delivery_late','occurrences_30d':4})
    review['category']['slug']='restaurants';review['merchant']['category_slug']='restaurants';review['merchant']['identity'].update(name='Example Pizza Kitchen',owner_first_name='Suresh');review['merchant']['offers']=[{'id':'bogo','title':'Buy 1 Get 1 (Tue-Thu)','status':'active'}]
    recall=deepcopy(price);recall['customer']={'customer_id':'demo_customer','merchant_id':'demo_studio','identity':{'name':'Dev','language_pref':'hi-en mix'},'relationship':{'visits_total':3,'last_visit':'2026-08-01'},'preferences':{'channel':'whatsapp','reminder_opt_in':True},'consent':{'opted_in_at':'2026-01-01','scope':['recall_reminders']}}
    recall['trigger'].update(id='demo_recall',kind='recall_due',scope='customer',customer_id='demo_customer',suppression_key='demo:recall:1',payload={'due_date':'2026-10-01','service_due':'follow_up','available_slots':[{'iso':'2026-09-30T18:00:00+05:30','label':'WRONG weekday label deliberately ignored'}]})
    return {'Price and offer changes':price,'Service issue before a discount':review,'Consent-aware customer reminder':recall}
