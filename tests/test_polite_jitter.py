from utils import polite


def test_sleeps_a_random_time_inside_the_range(monkeypatch):
    monkeypatch.delenv(polite.DISABLE_ENV_VAR, raising=False)
    slept = []
    seconds = polite.jitter_sleep(0.5, 1.5, sleep=slept.append, uniform=lambda a, b: 0.9)
    assert seconds == 0.9 and slept == [0.9]


def test_turned_off_in_tests(monkeypatch):
    monkeypatch.setenv(polite.DISABLE_ENV_VAR, "1")
    slept = []
    assert polite.jitter_sleep(0.5, 1.5, sleep=slept.append) == 0.0 and slept == []
