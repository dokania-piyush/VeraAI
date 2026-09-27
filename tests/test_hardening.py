from copy import deepcopy
import pytest
from vera.policy import active_offer_indices, known_shapes
from vera.evidence import Book
from vera.timeutil import timestamp
from conftest import NOW


@pytest.mark.parametrize('bad', ['no-date', '2026-99-99', {'unexpected':'type'}])
def test_bad_offer_expiry_is_not_unrestricted(bad):
    merchant={'offers':[{'title':'Haircut @ ₹99', 'status':'active', 'expires_at':bad}]}
    assert active_offer_indices(merchant, timestamp(NOW))==[]


@pytest.mark.parametrize('title', ['Haircut (Monday only)', 'BOGO Mon to Fri', 'Sunday special'])
def test_offer_title_day_restrictions(title):
    # The fixture clock is Sunday. Only the Sunday special may pass.
    merchant={'offers':[{'title':title,'status':'active'}]}
    assert bool(active_offer_indices(merchant,timestamp(NOW))) == ('Sunday' in title)


def test_evidence_collection_does_not_alias_input():
    roots={'merchant':{'offers':[{'title':'old'}]}}
    book=Book(roots);book.get('merchant','offers')
    roots['merchant']['offers'][0]['title']='new'
    assert not book.verify()


@pytest.mark.parametrize('payload', [
    {'performance':{'delta_7d':[]}},
    {'relationship':{'visits_total':'many'}},
    {'consent':{'scope':'everything'}},
    {'performance':{'calls':False}},
])
def test_nested_known_shapes_reject_malformed(payload):
    assert known_shapes('merchant',payload,'m1')


@pytest.mark.parametrize('payload', [{'kind':{}},{'scope':{}},{'suppression_key':[]}])
def test_malformed_trigger_discriminator_rejected(payload):
    assert known_shapes('trigger',payload,'t')
