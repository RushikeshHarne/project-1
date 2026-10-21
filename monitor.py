
from docx import Document
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

BASELINE = Path("baseline.json")
HISTORY = Path("change_history.json")
CONTRACT = Path("contract.docx")

BASEROW_URL = os.getenv("BASEROW_URL", "").rstrip("/")
BASEROW_TOKEN = os.getenv("BASEROW_TOKEN")
TABLE_ID = os.getenv("BASEROW_TABLE_ID")

def read_paragraphs():
    doc = Document(CONTRACT)
    return [p.text.strip() for p in doc.paragraphs if p.text.strip()]

def get_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def save_to_baserow(event):
    if not BASEROW_URL or not BASEROW_TOKEN or not TABLE_ID:
        raise RuntimeError("Baserow settings are missing from .env")

    url = f"{BASEROW_URL}/api/database/rows/table/{TABLE_ID}/?user_field_names=true"
    headers = {
        "Authorization": f"Token {BASEROW_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "Contract Name": CONTRACT.name,
        "Paragraph Number": event["paragraph"],
        "Old Text": event["old_text"] or "[New paragraph]",
        "New Text": event["new_text"] or "[Paragraph removed]",
        "Timestamp": event["timestamp"][:10],
        "Old Hash": event["old_hash"] or "",
        "New Hash": event["new_hash"] or "",
    }

    response = requests.post(
        url, headers=headers, json=payload, timeout=20
    )
    if not response.ok:
        raise RuntimeError(
            f"Baserow API error {response.status_code}: {response.text}"
        )
    print("Change saved to Baserow.")

current = read_paragraphs()

if not BASELINE.exists():
    baseline = []
else:
    baseline = json.loads(BASELINE.read_text())

if not baseline:
    baseline = [
        {"text": text, "hash": get_hash(text)}
        for text in current
    ]
    BASELINE.write_text(json.dumps(baseline, indent=2))
    if not HISTORY.exists():
        HISTORY.write_text("[]")
    print("Baseline saved.")
else:
    history = json.loads(HISTORY.read_text()) if HISTORY.exists() else []
    updated_history = []

    for i in range(max(len(baseline), len(current))):
        old = baseline[i] if i < len(baseline) else None
        new_text = current[i] if i < len(current) else None
        new_hash = get_hash(new_text) if new_text is not None else None

        if old is None or old["hash"] != new_hash:
            event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "paragraph": i + 1,
                "old_text": old["text"] if old else None,
                "new_text": new_text,
                "old_hash": old["hash"] if old else None,
                "new_hash": new_hash,
            }

            print(f"Change detected in paragraph {i + 1}")
            print(f"Old text: {event['old_text'] or '[New paragraph]'}")
            print(f"New text: {new_text or '[Paragraph removed]'}")

            # Save to Baserow first. Only record the event locally
            # after Baserow accepts it.
            save_to_baserow(event)
            updated_history.append(event)

    if updated_history:
        history.extend(updated_history)
        HISTORY.write_text(json.dumps(history, indent=2))

    BASELINE.write_text(json.dumps(
        [{"text": text, "hash": get_hash(text)} for text in current],
        indent=2,
    ))
    print("Baseline updated.")

