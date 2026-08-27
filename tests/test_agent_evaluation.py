import unittest

from scripts.evaluate_agent_routes import DEFAULT_CASES, evaluate, load_cases


class AgentEvaluationTests(unittest.TestCase):
    def test_committed_routing_regression_set_passes(self) -> None:
        report = evaluate(load_cases(DEFAULT_CASES))
        self.assertGreaterEqual(report["case_count"], 20)
        self.assertEqual(report["route_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
