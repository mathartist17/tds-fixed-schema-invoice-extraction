import re
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins = ["*"],
    allow_methods = ["*"],
    allow_headers = ["*"]
)

class InvoiceRequest(BaseModel):
    invoice_text: str

def parse_date(text: str):
    match = re.search(r"Date:\s*(.+)", text)
    if not match:
        return None
    raw = match.group(1).strip()
    formats = ["%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]

    for format in formats:
        try:
            return datetime.strptime(raw, format).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None

def parse_amount(text: str, label_pattern: str):
    match = re.search(r"(?:" + label_pattern + r").*?([\d,]+\.\d{2})", text)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))

@app.post("/extract")
def extract(req: InvoiceRequest):
    text = req.invoice_text

    invoice_number_match = re.search(r"Invoice No:\s*(\S+)", text)
    vendor_match = re.search(r"Vendor:\s*(.+)", text)

    invoice_number = invoice_number_match.group(1).strip() if invoice_number_match else None
    vendor = vendor_match.group(1).strip() if vendor_match else None
    date = parse_date(text)
    amount = parse_amount(text, r"Subtotal:")
    tax = parse_amount(text, r"GST|Tax")

    currency = "INR" if re.search(r"Rs\.|INR|₹", text) else None

    return {
        "invoice_no": invoice_number,
        "date": date,
        "vendor": vendor,
        "amount": amount,
        "tax": tax,
        "currency": currency
    }

@app.get("/")
def health_check():
    return {"status": "ok"}
