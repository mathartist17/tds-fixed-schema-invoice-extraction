import json
import os
import re
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
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


AI_PIPE_MODEL = "openai/gpt-4.1-nano"


def build_invoice_prompt(text: str):
    return (
        "Extract invoice details from the text below and return only valid JSON "
        "with these keys: invoice_no, date, vendor, amount, tax, currency. "
        "Use null when a value is missing. Normalize date to YYYY-MM-DD and "
        "return amount and tax as numbers.\n\n"
        f"Invoice text:\n{text}"
    )


def extract_text_from_ai_response(data):
    if isinstance(data, dict):
        if isinstance(data.get("output_text"), str):
            return data["output_text"]

        output = data.get("output")
        if isinstance(output, list):
            chunks = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                if isinstance(item.get("text"), str):
                    chunks.append(item["text"])
                    continue
                content = item.get("content")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            chunks.append(part["text"])
            if chunks:
                return "".join(chunks)

        if isinstance(data.get("content"), str):
            return data["content"]

    raise ValueError("AI Pipe response did not contain text output")


def parse_json_response(text: str):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("AI output was not valid JSON")

    return json.loads(cleaned[start : end + 1])

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
    match = re.search(
        r"(?:" + label_pattern + r").*?([\d,]+(?:\.\d{1,2})?)",
        text
    )
    if not match:
        return None
    return float(match.group(1).replace(",", ""))

@app.post("/extract")
def extract(req: InvoiceRequest):
    text = req.invoice_text

    invoice_number_match = re.search(
        r"(?:Invoice\s*(?:No\.?|Number|#)|Inv\.?\s*No\.?|Bill\s*No\.?)\s*[:#]?\s*(\S+)",
        text,
        re.IGNORECASE,
    )
    vendor_match = re.search(r"Vendor:\s*(.+)", text)

    invoice_number = invoice_number_match.group(1).strip() if invoice_number_match else None
    vendor = vendor_match.group(1).strip() if vendor_match else None
    date = parse_date(text)
    amount = parse_amount(text, r"Subtotal:")
    tax = parse_amount(text, r"GST|Tax")

    currency = "INR" if re.search(r"Rs\.|INR|₹", text) else None

    regex_result = {
        "invoice_no": invoice_number,
        "date": date,
        "vendor": vendor,
        "amount": amount,
        "tax": tax,
        "currency": currency,
    }

    if any(value is not None for value in regex_result.values()):
        return regex_result

    token = os.getenv("AIPIPE_TOKEN")

    if token:
        payload = {
            "model": AI_PIPE_MODEL,
            "input": build_invoice_prompt(req.invoice_text),
            "temperature": 0,
        }

        try:
            response = httpx.post(
                "https://aipipe.org/openrouter/v1/responses",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            ai_text = extract_text_from_ai_response(data)
            return parse_json_response(ai_text)
        except Exception:
            pass

    return regex_result

@app.get("/")
def health_check():
    return {"status": "ok"}
