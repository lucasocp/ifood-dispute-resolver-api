import logging
from typing import Dict, Any, List
from app.models import (
    DisputeRequest,
    DisputeVerdict,
    DecisionEnum,
    LiabilityEnum,
    OrderTelemetryLog,
    CustomerRiskProfile,
    DisputeReason
)

logger = logging.getLogger("ReActDisputeAgent")

class OrderNotFoundError(LookupError):
    pass

class CustomerOrderMismatchError(PermissionError):
    pass

# Mock telemetry database for demonstration & integration tests
SAMPLE_ORDER_LOGS: Dict[str, OrderTelemetryLog] = {
    "ORD-101": OrderTelemetryLog(
        order_id="ORD-101",
        customer_id="CUST-901",
        restaurant_id="REST-SP-01",
        driver_id="DRV-401",
        order_total=84.50,
        order_time="19:00",
        prep_completed_time="19:25",
        driver_pickup_time="19:30",
        driver_arrived_destination_time="20:45",
        gps_distance_to_delivery_meters=3500.0, # Entregador esteve a 3.5km de distância do cliente
        pin_code_validated=False,
        delay_minutes=65
    ),
    "ORD-102": OrderTelemetryLog(
        order_id="ORD-102",
        customer_id="CUST-902",
        restaurant_id="REST-BA-02",
        driver_id="DRV-402",
        order_total=52.00,
        order_time="12:10",
        prep_completed_time="13:20", # Restaurante demorou 70 minutos para preparar
        driver_pickup_time="13:22",
        driver_arrived_destination_time="13:35",
        gps_distance_to_delivery_meters=15.0, # Entregador esteve na porta
        pin_code_validated=True,
        delay_minutes=55
    ),
    "ORD-103": OrderTelemetryLog(
        order_id="ORD-103",
        customer_id="CUST-SUSPICIOUS",
        restaurant_id="REST-PR-04",
        driver_id="DRV-403",
        order_total=120.00,
        order_time="20:00",
        prep_completed_time="20:18",
        driver_pickup_time="20:20",
        driver_arrived_destination_time="20:38",
        gps_distance_to_delivery_meters=5.0, # Entregador entregou exatamente no endereço
        pin_code_validated=True, # Cliente informou PIN
        delay_minutes=0
    )
}

SAMPLE_CUSTOMER_PROFILES: Dict[str, CustomerRiskProfile] = {
    "CUST-901": CustomerRiskProfile(
        customer_id="CUST-901",
        lifetime_orders=48,
        disputes_last_30_days=0,
        chargeback_history_flag=False,
        trust_score=0.98
    ),
    "CUST-902": CustomerRiskProfile(
        customer_id="CUST-902",
        lifetime_orders=15,
        disputes_last_30_days=1,
        chargeback_history_flag=False,
        trust_score=0.92
    ),
    "CUST-SUSPICIOUS": CustomerRiskProfile(
        customer_id="CUST-SUSPICIOUS",
        lifetime_orders=4,
        disputes_last_30_days=4,
        chargeback_history_flag=True,
        trust_score=0.15
    )
}

class ReActDisputeAgent:
    """
    Agente Autônomo baseado no padrão ReAct (Reasoning + Acting)
    Itera sobre observações de telemetria logística, conformidade de políticas e
    perfis de risco de fraude para emitir decisões auditáveis e automáticas.
    """
    def __init__(self):
        self.order_logs = SAMPLE_ORDER_LOGS
        self.customer_profiles = SAMPLE_CUSTOMER_PROFILES

    # --- TOOLS DISPONÍVEIS PARA O AGENTE ---
    def tool_inspect_order_telemetry(self, order_id: str) -> Dict[str, Any]:
        log = self.order_logs.get(order_id)
        if not log:
            return {"error": f"Ordem {order_id} não encontrada na telemetria"}
        return log.dict() if hasattr(log, "dict") else log.model_dump()

    def tool_inspect_customer_risk(self, customer_id: str) -> Dict[str, Any]:
        profile = self.customer_profiles.get(customer_id)
        if not profile:
            # Perfil padrão neutro
            return {
                "customer_id": customer_id,
                "lifetime_orders": 1,
                "disputes_last_30_days": 0,
                "chargeback_history_flag": False,
                "trust_score": 0.8
            }
        return profile.dict() if hasattr(profile, "dict") else profile.model_dump()

    def tool_evaluate_policy_rules(self, reason: DisputeReason, delay_minutes: int, pin_validated: bool, gps_distance: float) -> str:
        if reason == DisputeReason.ORDER_NOT_DELIVERED:
            if pin_validated and gps_distance <= 50.0:
                return "POLICY_VIOLATION_SUSPECTED: Pedido com PIN confirmado e entregador no raio de 50 metros. Rejeição recomendada."
            elif gps_distance > 500.0 or not pin_validated:
                return "POLICY_ELIGIBLE: Telemetria indica falha logística (entregador distante ou sem validação biométrica/PIN)."
        
        if delay_minutes >= 45:
            return "POLICY_ELIGIBLE: Atraso superior a 45 minutos fere o SLA de entrega do iFood."

        return "POLICY_STANDARD: Caso requer análise de evidências ou voucher de cortesia."

    def evaluate_dispute(self, dispute: DisputeRequest) -> DisputeVerdict:
        trace: List[Dict[str, Any]] = []

        # PASSO 1: Reasoning & Telemetria
        trace.append({
            "step": 1,
            "thought": f"Analisando contestação {dispute.dispute_id} para o pedido {dispute.order_id}. Motivo alegado: {dispute.reason}.",
            "action": f"tool_inspect_order_telemetry({dispute.order_id})",
        })
        telemetry = self.tool_inspect_order_telemetry(dispute.order_id)
        if "error" in telemetry:
            raise OrderNotFoundError("Order not found.")
        if telemetry["customer_id"] != dispute.customer_id:
            raise CustomerOrderMismatchError("The dispute customer does not match the order.")
        trace[-1]["observation"] = telemetry
        refund_limit = min(dispute.requested_amount, telemetry["order_total"])

        # PASSO 2: Risk Profile
        trace.append({
            "step": 2,
            "thought": f"Consultando perfil de confiabilidade e histórico do cliente {dispute.customer_id}.",
            "action": f"tool_inspect_customer_risk({dispute.customer_id})",
        })
        customer_risk = self.tool_inspect_customer_risk(dispute.customer_id)
        trace[-1]["observation"] = customer_risk

        # PASSO 3: Policy Engine
        delay = telemetry.get("delay_minutes", 0)
        pin_valid = telemetry.get("pin_code_validated", False)
        gps_dist = telemetry.get("gps_distance_to_delivery_meters", 0.0)

        trace.append({
            "step": 3,
            "thought": "Cruzando logs de telemetria com as matrizes de regras e responsabilidade financeira do iFood.",
            "action": f"tool_evaluate_policy_rules(delay={delay}, pin={pin_valid}, gps_dist={gps_dist})",
        })
        policy_eval = self.tool_evaluate_policy_rules(dispute.reason, delay, pin_valid, gps_dist)
        trace[-1]["observation"] = policy_eval

        # PASSO 4: Decisão Final Autônoma
        trust_score = customer_risk.get("trust_score", 0.8)
        chargeback_flag = customer_risk.get("chargeback_history_flag", False)

        # Regra 1: Fraude detectada (PIN validado + GPS perfeito + cliente com alto índice de contestações)
        if pin_valid and gps_dist <= 50.0 and (trust_score < 0.4 or chargeback_flag):
            decision = DecisionEnum.DENY_DISPUTE
            liability = LiabilityEnum.CUSTOMER
            refund = 0.0
            confidence = 0.96
            summary = "Contestação rejeitada: Entrega auditada via GPS e PIN biométrico; histórico de contestações anômalas."

        # Regra 2: Falha logística clara (entregador marcou entregue mas estava a mais de 500m)
        elif dispute.reason == DisputeReason.ORDER_NOT_DELIVERED and (gps_dist > 500.0 or not pin_valid):
            decision = DecisionEnum.APPROVE_FULL_REFUND
            liability = LiabilityEnum.LOGISTICS
            refund = refund_limit
            confidence = 0.98
            summary = "Reembolso integral aprovado: Telemetria de GPS aponta desvio da rota de entrega sem confirmação de PIN."

        # Regra 3: Atraso excessivo por gargalo de cozinha
        elif delay >= 45:
            decision = DecisionEnum.APPROVE_FULL_REFUND
            liability = LiabilityEnum.MERCHANT
            refund = refund_limit
            confidence = 0.94
            summary = f"Reembolso aprovado por SLA violado: Pedido atrasou {delay} minutos com preparo excessivo do restaurante."

        # Regra 4: Itens danificados ou faltantes para clientes de alta confiança
        elif trust_score >= 0.85:
            decision = DecisionEnum.APPROVE_PARTIAL_VOUCHER
            liability = LiabilityEnum.IFOOD
            refund = min(refund_limit, 30.0)
            confidence = 0.90
            summary = "Voucher de compensação imediato aprovado para cliente de alta fidelidade sem histórico de fricção."

        else:
            decision = DecisionEnum.REQUEST_PHOTO_EVIDENCE
            liability = LiabilityEnum.CUSTOMER
            refund = 0.0
            confidence = 0.75
            summary = "Solicitada foto comprobatória do estado do pacote para validação da comissão de qualidade."

        verdict = DisputeVerdict(
            dispute_id=dispute.dispute_id,
            order_id=dispute.order_id,
            decision=decision,
            refund_amount=refund,
            financial_liability=liability,
            confidence_score=confidence,
            reasoning_summary=summary,
            audit_trace=trace
        )

        logger.info(f"Veredito ReAct emitido para disputa {dispute.dispute_id}: {decision.value}")
        return verdict
