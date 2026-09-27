import pytest
from scripts.quality_check import parse_score,DIMENSIONS


def test_valid_quality_response():
    response={'scores':{k:7 for k in DIMENSIONS},'unsupported_claims':[],'rationale':'Independent explanation'}
    assert parse_score(response)==response


@pytest.mark.parametrize('value',[{}, {'scores':{}}, {'scores':{k:True for k in DIMENSIONS},'unsupported_claims':[],'rationale':'x'}, {'scores':{k:11 for k in DIMENSIONS},'unsupported_claims':[],'rationale':'x'}, {'scores':{k:7 for k in DIMENSIONS},'unsupported_claims':'none','rationale':'x'}])
def test_bad_quality_response_is_error_not_fake_score(value):
    with pytest.raises(ValueError):parse_score(value)
