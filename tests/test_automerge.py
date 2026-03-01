import pytest

from src.automerge import decide_automerge


def test_automerge_eligible_when_ci_passed_and_score_high_enough():
    d = decide_automerge(pr_score=90, ci_passed=True, min_score=80, pr_number=1)
    assert d.eligible is True
    assert d.pr_number == 1


def test_automerge_ineligible_when_ci_failed():
    d = decide_automerge(pr_score=95, ci_passed=False, min_score=80)
    assert d.eligible is False
    assert "CI" in d.reason


def test_automerge_ineligible_when_score_too_low():
    d = decide_automerge(pr_score=79, ci_passed=True, min_score=80)
    assert d.eligible is False
    assert "below" in d.reason


@pytest.mark.parametrize("score", [-1, 101])
def test_automerge_rejects_out_of_range_scores(score):
    d = decide_automerge(pr_score=score, ci_passed=True)
    assert d.eligible is False
    assert "between 0 and 100" in d.reason
