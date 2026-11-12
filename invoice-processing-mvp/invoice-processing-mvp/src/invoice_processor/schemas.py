from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict

class InvoiceLine(BaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    tax_rate: Optional[float] = None
    line_total: Optional[float] = None

class InvoiceData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    po_number: Optional[str] = None
    currency: Optional[str] = None
    subtotal: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    line_items: List[InvoiceLine] = Field(default_factory=list)
    extraction_method: str = "local"
    extraction_confidence: str = "medium"
