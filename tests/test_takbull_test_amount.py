from decimal import Decimal

from todira_common.access import TEST_PASS_PLAN, PASS_PLANS, plan_for_amount, test_amount_from_env


def test_test_amount_off_by_default(monkeypatch):
    monkeypatch.delenv("TAKBULL_TEST_AMOUNT_ILS", raising=False)
    assert test_amount_from_env() is None
    assert plan_for_amount(Decimal("1.00"), test_amount_from_env()) is None


def test_test_amount_grants_the_one_day_test_pass(monkeypatch):
    monkeypatch.setenv("TAKBULL_TEST_AMOUNT_ILS", "1")
    assert plan_for_amount(Decimal("1.00"), test_amount_from_env()) == TEST_PASS_PLAN
    assert TEST_PASS_PLAN not in PASS_PLANS


def test_real_prices_still_win_and_junk_is_ignored(monkeypatch):
    monkeypatch.setenv("TAKBULL_TEST_AMOUNT_ILS", "1")
    assert plan_for_amount(Decimal("19.90"), test_amount_from_env()) == "pass_7"
    assert plan_for_amount(Decimal("2.00"), test_amount_from_env()) is None
    monkeypatch.setenv("TAKBULL_TEST_AMOUNT_ILS", "abc")
    assert test_amount_from_env() is None
