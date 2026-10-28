import unittest
import os
import sys
from pathlib import Path
from unittest.mock import patch

root = str(Path(__file__).resolve().parent.parent)
if root not in sys.path:
    sys.path.insert(0, root)

from app.models import DisputeRequest, DisputeReason, DecisionEnum, LiabilityEnum
from app.agents.react_agent import ReActDisputeAgent
from app.main import evaluate_dispute_endpoint, require_api_key
from fastapi import HTTPException

class TestReActDisputeResolver(unittest.TestCase):
    def setUp(self):
        self.agent = ReActDisputeAgent()

    def test_logistics_failure_triggers_full_refund(self):
        # ORD-101: motorista marcou entregue mas estava a 3.5km e sem PIN
        dispute = DisputeRequest(
            dispute_id="DSP-001",
            order_id="ORD-101",
            customer_id="CUST-901",
            reason=DisputeReason.ORDER_NOT_DELIVERED,
            customer_notes="Nunca recebi meu pedido.",
            requested_amount=84.50
        )
        verdict = self.agent.evaluate_dispute(dispute)
        self.assertEqual(verdict.decision, DecisionEnum.APPROVE_FULL_REFUND)
        self.assertEqual(verdict.financial_liability, LiabilityEnum.LOGISTICS)
        self.assertEqual(verdict.refund_amount, 84.50)
        self.assertGreaterEqual(verdict.confidence_score, 0.95)
        self.assertEqual(len(verdict.audit_trace), 3)

    def test_merchant_kitchen_delay_triggers_merchant_liability(self):
        # ORD-102: restaurante atrasou 70 minutos para preparar
        dispute = DisputeRequest(
            dispute_id="DSP-002",
            order_id="ORD-102",
            customer_id="CUST-902",
            reason=DisputeReason.EXTREME_DELAY,
            customer_notes="O pedido demorou quase 2 horas para chegar.",
            requested_amount=52.00
        )
        verdict = self.agent.evaluate_dispute(dispute)
        self.assertEqual(verdict.decision, DecisionEnum.APPROVE_FULL_REFUND)
        self.assertEqual(verdict.financial_liability, LiabilityEnum.MERCHANT)
        self.assertEqual(verdict.refund_amount, 52.00)

    def test_fraudulent_claim_triggers_denial(self):
        # ORD-103: PIN confirmado, GPS a 5 metros da porta, cliente suspeito com 4 disputas recentes
        dispute = DisputeRequest(
            dispute_id="DSP-003",
            order_id="ORD-103",
            customer_id="CUST-SUSPICIOUS",
            reason=DisputeReason.ORDER_NOT_DELIVERED,
            customer_notes="Diz que foi entregue mas eu não vi ninguém.",
            requested_amount=120.00
        )
        verdict = self.agent.evaluate_dispute(dispute)
        self.assertEqual(verdict.decision, DecisionEnum.DENY_DISPUTE)
        self.assertEqual(verdict.financial_liability, LiabilityEnum.CUSTOMER)
        self.assertEqual(verdict.refund_amount, 0.0)

    def test_react_audit_trace_integrity(self):
        dispute = DisputeRequest(
            dispute_id="DSP-TRACE-TEST",
            order_id="ORD-101",
            customer_id="CUST-901",
            reason=DisputeReason.ORDER_NOT_DELIVERED,
            customer_notes="Teste de rastreabilidade.",
            requested_amount=84.50
        )
        verdict = self.agent.evaluate_dispute(dispute)
        for step in verdict.audit_trace:
            self.assertIn("thought", step)
            self.assertIn("action", step)
            self.assertIn("observation", step)

    def test_unknown_order_cannot_receive_approval(self):
        dispute = DisputeRequest(
            dispute_id="DSP-UNKNOWN",
            order_id="ORD-UNKNOWN",
            customer_id="CUST-901",
            reason=DisputeReason.ORDER_NOT_DELIVERED,
            customer_notes="Pedido não reconhecido.",
            requested_amount=84.50
        )
        with self.assertRaisesRegex(LookupError, "Order not found"):
            self.agent.evaluate_dispute(dispute)

    def test_api_returns_not_found_for_unknown_order(self):
        dispute = DisputeRequest(
            dispute_id="DSP-UNKNOWN",
            order_id="ORD-UNKNOWN",
            customer_id="CUST-901",
            reason=DisputeReason.ORDER_NOT_DELIVERED,
            customer_notes="Pedido não reconhecido.",
            requested_amount=84.50
        )
        with self.assertRaises(HTTPException) as result:
            evaluate_dispute_endpoint(dispute, _auth=None)
        self.assertEqual(result.exception.status_code, 404)

    def test_dispute_customer_must_match_order(self):
        dispute = DisputeRequest(
            dispute_id="DSP-MISMATCH",
            order_id="ORD-101",
            customer_id="CUST-902",
            reason=DisputeReason.ORDER_NOT_DELIVERED,
            customer_notes="Pedido não recebido.",
            requested_amount=84.50
        )
        with self.assertRaisesRegex(PermissionError, "does not match"):
            self.agent.evaluate_dispute(dispute)

    def test_refund_is_capped_at_order_total(self):
        dispute = DisputeRequest(
            dispute_id="DSP-OVER-TOTAL",
            order_id="ORD-101",
            customer_id="CUST-901",
            reason=DisputeReason.ORDER_NOT_DELIVERED,
            customer_notes="Pedido não recebido.",
            requested_amount=1000.00
        )
        verdict = self.agent.evaluate_dispute(dispute)
        self.assertEqual(verdict.refund_amount, 84.50)

    def test_api_key_authentication_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as missing_key:
                require_api_key("a" * 32)
        self.assertEqual(missing_key.exception.status_code, 503)

        with patch.dict(os.environ, {"DISPUTE_API_KEY": "a" * 32}):
            with self.assertRaises(HTTPException) as invalid_key:
                require_api_key("b" * 32)
            self.assertEqual(invalid_key.exception.status_code, 401)
            self.assertIsNone(require_api_key("a" * 32))

if __name__ == "__main__":
    unittest.main()
