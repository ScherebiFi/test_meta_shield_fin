import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


class PaymentWebhookTests(unittest.TestCase):
    def test_webhook_validates_and_processes_transactions_through_the_queue(self):
        state = {
            "fail_safe_active": True,
            "reason": "Test local",
        }
        with patch.object(main, "llama_agent", None), patch.dict(main.system_state, state):
            with TestClient(main.app) as client:
                fail_safe_off = client.post("/api/toggle-failsafe").json()
                fail_safe_on = client.post("/api/toggle-failsafe").json()
                self.assertFalse(fail_safe_off["fail_safe_active"])
                self.assertTrue(fail_safe_on["fail_safe_active"])

                invalid_response = client.post(
                    "/api/webhook/payment-notification",
                    json={"amount": -1, "velocity": 1, "country_risk": 0},
                )
                self.assertEqual(invalid_response.status_code, 422)

                response = client.post(
                    "/api/webhook/payment-notification",
                    json={
                        "transaction_id": "tx_api_test",
                        "amount": 42.0,
                        "velocity": 1,
                        "country_risk": 0,
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertIn(
            response.json()["analysis"]["status"],
            {"SAFE_FAILSAFE", "BLOCKED_FAILSAFE"},
        )
        self.assertEqual(len(response.json()["analysis"]["integrity_hash"]), 64)


if __name__ == "__main__":
    unittest.main()
