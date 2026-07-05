import json
import os
import re
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins = ["*"],
    allow_methods = ["*"],
    allow_headers = ["*"]
)

AI_PIPE_MODEL = "openai/gpt-4.1"


def build_invoice_prompt(text: str):
    return (
        "Extract these fields from the invoice text and return JSON with EXACTLY "
        "these keys: invoice_no, date, vendor, amount, tax, currency.\n"
        "- date: ISO YYYY-MM-DD\n"
        "- amount: the SUBTOTAL before tax, as a plain number (no separators)\n"
        "- tax: the tax amount only, as a plain number\n"
        "- currency: ISO code (INR, USD, EUR...)\n"
        "- use null if a field is not present.\n\n"
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


async def extract_from_ai(text: str):
    token = os.getenv("AIPIPE_TOKEN")
    if not token:
        return {}

    prompt = build_invoice_prompt(text)
    payload = {
        "model": AI_PIPE_MODEL,
        "input": prompt,
        "temperature": 0,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://aipipe.org/openrouter/v1/responses",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            ai_text = extract_text_from_ai_response(data)
            return parse_json_response(ai_text)
    except Exception:
        return {}


@app.post("/extract")
async def extract(request: Request):
    body = await request.json()
    text = body.get("invoice_text", "")
    out = await extract_from_ai(text)
    keys = ["invoice_no", "date", "vendor", "amount", "tax", "currency"]
    return {key: out.get(key) for key in keys}

@app.get("/")
def health_check():
    return {"status": "ok"}
