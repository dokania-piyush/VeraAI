import json
from dataclasses import replace
import httpx
import pytest
from vera.config import Settings
from vera.semantic import SemanticClassifier


def classifier(content):
    def handler(req):
        body=json.loads(req.content)
        assert 'merchant_id' not in body['messages'][1]['content']
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(content)}}]})
    return SemanticClassifier(Settings(semantic_enabled=True,llm_model='test-model',llm_api_key='fake-test-key'),httpx.MockTransport(handler))


def test_classifier_valid():
    result=classifier({'intent':'commit','confidence':.95,'evidence':'proceed'}).classify('Please proceed')
    assert result['intent']=='commit'


@pytest.mark.parametrize('content',[
    {'intent':'delete_database','confidence':1,'evidence':'go'},
    {'intent':'commit','confidence':.1,'evidence':'go'},
    {'intent':'commit','confidence':1,'evidence':'not in input'},
    {'intent':'commit','confidence':True,'evidence':'go'},
    {'intent':'commit','confidence':1,'evidence':''},
    {},
])
def test_invalid_model_output_cannot_execute(content):
    assert classifier(content).classify('go')['intent']=='unknown'


def test_disabled_mode_never_calls_provider():
    def fail(req):raise AssertionError('Network must not be called')
    c=SemanticClassifier(Settings(),httpx.MockTransport(fail))
    assert c.classify('hello')['status']=='disabled'


def test_provider_timeout_fallback():
    def timeout(req):raise httpx.ReadTimeout('synthetic timeout')
    c=SemanticClassifier(Settings(semantic_enabled=True,llm_model='test',llm_api_key='test'),httpx.MockTransport(timeout))
    assert c.classify('go')['status']=='provider_error'


def test_total_deadline_cancels_slow_provider():
    import asyncio
    import time
    async def slow(req):
        await asyncio.sleep(1)
        return httpx.Response(200, json={})
    c=SemanticClassifier(Settings(semantic_enabled=True, llm_model='test', llm_api_key='test', llm_timeout_seconds=.05), httpx.MockTransport(slow))
    start=time.perf_counter()
    assert c.classify('please proceed')['status']=='provider_error'
    assert time.perf_counter()-start < .5
