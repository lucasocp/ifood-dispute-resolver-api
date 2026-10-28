from enum import Enum
from typing import List, Optional, Dict, Any
from app.compat import BaseModel, Field

class DisputeReason(str, Enum):
    ITEM_MISSING = "item_faltando"
    ORDER_NOT_DELIVERED = "pedido_nao_entregue"
    EXTREME_DELAY = "atraso_extremo"
    FOOD_DAMAGED = "comida_danificada_ou_fria"
    WRONG_ORDER = "pedido_trocado"

class DecisionEnum(str, Enum):
    APPROVE_FULL_REFUND = "reembolso_integral_aprovado"
    APPROVE_PARTIAL_VOUCHER = "voucher_compensacao_aprovado"
    REQUEST_PHOTO_EVIDENCE = "solicitar_evidencia_fotografica"
    DENY_DISPUTE = "disputa_rejeitada"

class LiabilityEnum(str, Enum):
    MERCHANT = "restaurante_parceiro"
    LOGISTICS = "operador_logistico_ou_entregador"
    IFOOD = "plataforma_ifood"
    CUSTOMER = "cliente_sem_indenizacao"

class OrderTelemetryLog(BaseModel):
    order_id: str
    customer_id: str
    restaurant_id: str
    driver_id: Optional[str] = None
    order_total: float
    order_time: str
    prep_completed_time: str
    driver_pickup_time: Optional[str] = None
    driver_arrived_destination_time: Optional[str] = None
    gps_distance_to_delivery_meters: float = 0.0
    pin_code_validated: bool = False
    delay_minutes: int = 0

class CustomerRiskProfile(BaseModel):
    customer_id: str
    lifetime_orders: int
    disputes_last_30_days: int
    chargeback_history_flag: bool = False
    trust_score: float = Field(default=0.9, ge=0.0, le=1.0)

class DisputeRequest(BaseModel):
    dispute_id: str
    order_id: str
    customer_id: str
    reason: DisputeReason
    customer_notes: str
    requested_amount: float = Field(gt=0, allow_inf_nan=False)

class ReActStep(BaseModel):
    step_number: int
    thought: str
    action: str
    observation: str

class DisputeVerdict(BaseModel):
    dispute_id: str
    order_id: str
    decision: DecisionEnum
    refund_amount: float
    financial_liability: LiabilityEnum
    confidence_score: float
    reasoning_summary: str
    audit_trace: List[Dict[str, Any]] = Field(default_factory=list)
