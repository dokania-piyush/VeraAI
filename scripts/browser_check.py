"""Optional offline UI check using Chromium + the real in-process FastAPI app.

Uses a mocked fetch transport, not a network/browser deployment test. Install
Playwright separately only to reproduce this optional visual check.
"""
import argparse
import json
from pathlib import Path
import re
import tempfile
from fastapi.testclient import TestClient
from vera.api import create_app
from vera.config import Settings
from scripts.fixtures import demo_cases


def main():
    from playwright.sync_api import sync_playwright
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--chromium',default='/usr/bin/chromium');a=p.parse_args()
    root=Path(__file__).resolve().parents[1];out=root/'reports';out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Settings(db_path=str(Path(tmp)/'test.db'),admin_token='ui-test-token'))) as client:
        case=next(iter(demo_cases().values()))
        for scope,key in [('category','slug'),('merchant','merchant_id'),('trigger','id')]:
            obj=case[scope];client.post('/v1/context',json={'scope':scope,'context_id':obj[key],'version':1,'payload':obj,'delivered_at':case['now']}).raise_for_status()
        client.post('/v1/tick',json={'now':case['now'],'available_triggers':[case['trigger']['id']]}).raise_for_status()
        def backend(path,options):
            # No arbitrary external URLs; no real network traffic from the browser.
            if not path.startswith(('/assets/','/debug/')):raise ValueError('Unsupported UI test route')
            response=client.request(options.get('method','GET'),path,headers=options.get('headers',{}),content=options.get('body'))
            return {'status':response.status_code,'body':response.text,'content_type':response.headers.get('content-type','application/json')}
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=a.chromium,headless=True,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1440,'height':1080});errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            html=(root/'web/index.html').read_text()
            html=re.sub(r'<link[^>]+>|<script[^>]*>.*?</script>','',html,flags=re.S)
            page.set_content(html);page.add_style_tag(path=str(root/'web/styles.css'))
            page.expose_function('compassTestBackend',backend)
            page.evaluate('''() => { window.fetch=async (path,options={})=>{const r=await window.compassTestBackend(path,options);return new Response(r.body,{status:r.status,headers:{'Content-Type':r.content_type}})}; }''')
            page.add_script_tag(path=str(root/'web/app.js'))
            page.wait_for_function("document.querySelectorAll('.scenario').length===3")
            page.fill('#token','ui-test-token');page.click('#preview')
            page.wait_for_function("document.getElementById('message').textContent.includes('₹499')")
            page.click('#change-price');page.click('#preview');page.wait_for_function("document.getElementById('message').textContent.includes('₹599')")
            page.click('[data-name="Consent-aware customer reminder"]');page.click('#preview');page.wait_for_function("document.getElementById('message').textContent.includes('Dev')")
            page.click('#revoke');page.click('#preview');page.wait_for_function("document.getElementById('badge').textContent==='SKIP'")
            assert page.locator('#reason').inner_text()=='consent_revoked'
            page.click('[data-name="Service issue before a discount"]');page.click('#preview');page.wait_for_function("document.getElementById('message').textContent.includes('Suresh')")
            page.click('#refresh');page.wait_for_function("document.getElementById('connection-status').textContent.startsWith('Connected')")
            page.fill('#token','');page.screenshot(path=str(out/'studio-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(out/'studio-mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            report={'browser':'Chromium via Playwright','transport':'Offline DOM + mocked fetch to real FastAPI TestClient; no browser network navigation','checks':['preview current price','price mutation','customer reminder','revoked consent abstains','operational review reply','protected trace loading','mobile no horizontal overflow'],'javascript_errors':errors,'screenshots':['studio-desktop.png','studio-mobile.png'],'limitation':'Direct browser navigation to localhost was blocked by the authoring environment. Local HTTP was tested independently with HTTPX.'}
            (out/'browser-check.json').write_text(json.dumps(report,indent=2));assert not errors;browser.close();print(json.dumps(report,indent=2))

if __name__=='__main__':main()
