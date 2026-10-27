import unittest

from ml_engine import MLFraudDetector


class FraudDetectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = MLFraudDetector()

    def test_hash_is_stable_for_same_transaction(self):
        transaction = {
            "transaction_id": "tx_test",
            "amount": 42.0,
            "velocity": 1,
            "country_risk": 0,
            "timestamp": "2026-01-01T00:00:00+00:00",
        }

        first_hash = self.detector.compute_integrity_hash(transaction)
        second_hash = self.detector.compute_integrity_hash(transaction)

        self.assertEqual(first_hash, second_hash)
        self.assertEqual(len(first_hash), 64)

    def test_failsafe_returns_a_local_decision_for_every_risk_band(self):
        low_risk = {
            "transaction_id": "tx_low",
            "amount": 42.0,
            "velocity": 1,
            "country_risk": 0,
            "timestamp": "2026-01-01T00:00:00+00:00",
        }
        elevated_risk = {**low_risk, "amount": 200.0}
        critical_risk = {**low_risk, "amount": 600.0}

        low_result = self.detector.predict(low_risk, force_local_failsafe=True)
        elevated_result = self.detector.predict(elevated_risk, force_local_failsafe=True)
        critical_result = self.detector.predict(critical_risk, force_local_failsafe=True)

        self.assertEqual(low_result["action"], "ALLOW")
        self.assertIn(elevated_result["action"], {"ALLOW", "BLOCK"})
        self.assertEqual(critical_result["action"], "BLOCK")
        self.assertNotEqual(low_result["status"], "GREY_ZONE")
        self.assertNotEqual(elevated_result["status"], "GREY_ZONE")
        self.assertIn("latency_ms", low_result)

    def test_warm_local_scoring_median_stays_below_five_milliseconds(self):
        transaction = {
            "transaction_id": "tx_latency",
            "amount": 42.0,
            "velocity": 1,
            "country_risk": 0,
            "timestamp": "2026-01-01T00:00:00+00:00",
        }
        self.detector.predict(transaction)
        measurements = [
            self.detector.predict(transaction)["latency_ms"]
            for _ in range(51)
        ]
        median_latency = sorted(measurements)[len(measurements) // 2]

        self.assertLess(median_latency, 5.0, f"Median was {median_latency} ms")


if __name__ == "__main__":
    unittest.main()
