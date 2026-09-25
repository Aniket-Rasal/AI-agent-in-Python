import unittest
from unittest.mock import patch

from app.scheduler import run_forever


class FakeConfig:
    interval_minutes = 1
    max_documents = 100


class SchedulerTests(unittest.TestCase):
    def test_runs_immediately_waits_for_interval_then_runs_again(self):
        class FakeEvent:
            def __init__(self):
                self.waits = 0
                self.stopped = False

            def is_set(self):
                return self.stopped

            def wait(self, seconds):
                self.asserted_seconds = seconds
                self.waits += 1
                if self.waits == 1:
                    return False
                self.stopped = True
                return True

        class FakeRunner:
            def __init__(self):
                self.calls = 0

            def run_once(self, owner=None):
                self.calls += 1
                return "limit" if self.calls == 2 else "complete"

        event = FakeEvent()
        runner = FakeRunner()
        with patch("app.scheduler.threading.Event", return_value=event):
            run_forever(FakeConfig(), runner)
        self.assertEqual(event.asserted_seconds, 60)
        self.assertEqual(runner.calls, 2)

    def test_unexpected_cycle_error_is_logged_waits_then_retries(self):
        class FakeEvent:
            def __init__(self):
                self.stopped = False
                self.waited = []

            def is_set(self):
                return self.stopped

            def wait(self, seconds):
                self.waited.append(seconds)
                return False

        class FailingThenSuccessfulRunner:
            def __init__(self):
                self.calls = 0

            def run_once(self, owner=None):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("simulated cycle failure")
                return "limit"

        event = FakeEvent()
        runner = FailingThenSuccessfulRunner()
        with patch("app.scheduler.threading.Event", return_value=event):
            with self.assertLogs("app.scheduler", level="ERROR") as captured:
                run_forever(FakeConfig(), runner)

        self.assertEqual(runner.calls, 2)
        self.assertEqual(event.waited, [60])
        self.assertTrue(any("simulated cycle failure" in line for line in captured.output))

    def test_limit_result_stops_without_waiting_for_another_cycle(self):
        class FakeEvent:
            def is_set(self):
                return False

            def wait(self, seconds):
                raise AssertionError("scheduler must not wait after reaching the limit")

        class LimitRunner:
            def __init__(self):
                self.calls = 0

            def run_once(self, owner=None):
                self.calls += 1
                return "limit"

        runner = LimitRunner()
        with patch("app.scheduler.threading.Event", return_value=FakeEvent()):
            run_forever(FakeConfig(), runner)
        self.assertEqual(runner.calls, 1)
