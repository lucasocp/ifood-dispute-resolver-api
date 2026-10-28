"""
FastAPI Server: iFood Async Dispute Resolver API
"""
import os
import secrets
import sys
from pathlib import Path

root = str(Path(__file__).resolve().parent.parent)
if root not in sys.path:
    sys.path.insert(0, root)

try:
    from fastapi import Depends, FastAPI, Header, HTTPException
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

from app.agents.react_agent import (
    CustomerOrderMismatchError,
    OrderNotFoundError,
    ReActDisputeAgent,
)
from app.models import DisputeRequest, DisputeVerdict, DisputeReason

agent = ReActDisputeAgent()

if HAS_FASTAPI:
    app = FastAPI(
        title="iFood Dispute Resolver API (ReAct Pattern)",
        description="Serviço assíncrono para resolução autônoma e auditável de contestações e estornos com Agentes ReAct.",
        version="1.0.0"
    )

    @app.get("/health")
    def health():
        return {"status": "healthy", "service": "ifood-dispute-resolver"}

    def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
        expected_key = os.getenv("DISPUTE_API_KEY")
        if not expected_key or len(expected_key) < 32:
            raise HTTPException(
                status_code=503,
                detail="API authentication is not configured with a sufficiently strong key.",
            )
        if x_api_key is None or not secrets.compare_digest(x_api_key, expected_key):
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing API key.",
                headers={"WWW-Authenticate": "ApiKey"},
            )

    @app.post("/api/v1/disputes/evaluate", response_model=None)
    def evaluate_dispute_endpoint(
        dispute: DisputeRequest,
        _auth: None = Depends(require_api_key),
    ):
        try:
            verdict = agent.evaluate_dispute(dispute)
        except OrderNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except CustomerOrderMismatchError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        return verdict.dict() if hasattr(verdict, "dict") else verdict.model_dump()

if __name__ == "__main__":
    print("[Standalone Execution Demo]")
    test_dispute = DisputeRequest(
        dispute_id="DSP-LIVE-99",
        order_id="ORD-101",
        customer_id="CUST-901",
        reason=DisputeReason.ORDER_NOT_DELIVERED,
        customer_notes="O entregador marcou como entregue mas nunca tocou o interfone.",
        requested_amount=84.50
    )
    verdict = agent.evaluate_dispute(test_dispute)
    print(f"Decisão: {verdict.decision.value}")
    print(f"Responsabilidade Financeira: {verdict.financial_liability.value}")
    print(f"Valor Reembolsado: R$ {verdict.refund_amount}")
    print(f"Justificativa: {verdict.reasoning_summary}")
    print(f"Passos de Auditoria ReAct: {len(verdict.audit_trace)} etapas registradas.")
