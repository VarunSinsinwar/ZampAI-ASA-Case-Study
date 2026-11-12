import hashlib
from pathlib import Path

def file_fingerprint(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def check_duplicate(store, invoice: dict, fingerprint: str):
    return store.find_duplicate(
        vendor_name=invoice.get("vendor_name"),
        invoice_number=invoice.get("invoice_number"),
        fingerprint=fingerprint
    )
