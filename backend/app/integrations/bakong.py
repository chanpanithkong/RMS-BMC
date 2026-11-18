"""Bakong KHQR (National Bank of Cambodia) for online payment, per the NBC documents:

* "Bakong as a payment switch – Merchant" (KHQR guideline v1.4, Nov 2020): EMVCo tags; tag 29 for an individual/solo
  merchant (sub-tag 00 = Bakong account ID), tag 30 for a corporate merchant (00 = account ID, 01 = merchant ID,
  02 = acquiring bank); 52 MCC, 53 currency (116 KHR, 840 USD), 54 amount, 58 KH, 59 name, 60 city, 62 additional
  data (01 bill number, 02 mobile, 03 store label, 07 terminal label, 08 purpose), 99/00 creation timestamp in ms,
  63 CRC over everything before it including "6304".
* "Bakong QR Pay Integration" v1.0.3: dynamic KHQR (point of initiation 12); the merchant back end polls
  check_transaction_by_md5 with the MD5 of the QR string; QR time-out not more than 10 minutes.
* "Bakong Open API" v1.0.1: POST {base}/v1/check_transaction_by_md5, header "Authorization: Bearer <token>",
  body {"md5": ...}; responseCode 0 = success with data {hash, fromAccountId, toAccountId, currency, amount,
  description}; responseCode 1 with errorCode 1 = not found, 3 = failed. Tokens expire after 90 days.

Card or wallet credentials never pass through RMS: the customer pays in their own banking app.
"""
import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx

CURRENCY = {"KHR": "116", "USD": "840"}
TRANSPORT: httpx.BaseTransport | None = None  # tests inject httpx.MockTransport here


class KhqrError(ValueError):
    pass


class BakongUnavailable(Exception):
    """Token rejected, access blocked (Bakong refuses requests from outside Cambodia), or the service is down."""


def crc16(data: str) -> str:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF), upper-case hex — matches NBC's sample (…630498B8)."""
    crc = 0xFFFF
    for b in data.encode("utf-8"):
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def tlv(tag: str, value: str) -> str:
    if len(value) > 99:
        raise KhqrError(f"Tag {tag} is longer than 99 characters.")
    return f"{tag}{len(value):02d}{value}"


def _check(name: str, value: str | None, max_len: int, required: bool = True) -> str | None:
    if not value:
        if required:
            raise KhqrError(f"{name} is required for KHQR.")
        return None
    if len(value) > max_len:
        raise KhqrError(f"{name} can be at most {max_len} characters.")
    return value


def amount_text(amount: Decimal, currency: str) -> str:
    if amount <= 0:
        raise KhqrError("A dynamic KHQR needs an amount above zero.")
    return str(int(amount)) if currency == "KHR" else f"{amount.quantize(Decimal('0.01'))}"


def build_khqr(*, account_id: str, merchant_name: str, merchant_city: str, amount: Decimal, currency: str, bill_number: str,
               merchant_type: str = "individual", merchant_id: str | None = None, acquiring_bank: str | None = None, mcc: str = "5999",
               store_label: str | None = None, terminal_label: str | None = None, created_ms: int | None = None) -> str:
    """Dynamic KHQR string (point of initiation 12) with a unique bill number and creation timestamp."""
    if currency not in CURRENCY:
        raise KhqrError("KHQR supports KHR and USD only.")
    _check("Bakong account ID", account_id, 32)
    if merchant_type == "individual":
        account = tlv("29", tlv("00", account_id))
    elif merchant_type == "merchant":
        account = tlv("30", tlv("00", account_id) + tlv("01", _check("Merchant ID", merchant_id, 32)) + tlv("02", _check("Acquiring bank", acquiring_bank, 32)))
    else:
        raise KhqrError("merchant_type must be 'individual' (tag 29) or 'merchant' (tag 30).")
    extra = tlv("01", _check("Bill number", bill_number, 25))
    if store_label:
        extra += tlv("03", _check("Store label", store_label, 25))
    if terminal_label:
        extra += tlv("07", _check("Terminal label", terminal_label, 25))
    body = (tlv("00", "01") + tlv("01", "12") + account + tlv("52", mcc) + tlv("53", CURRENCY[currency]) + tlv("54", amount_text(amount, currency))
            + tlv("58", "KH") + tlv("59", _check("Merchant name", merchant_name, 25)) + tlv("60", _check("Merchant city", merchant_city, 15))
            + tlv("62", extra) + tlv("99", tlv("00", str(created_ms or int(time.time() * 1000)))) + "6304")
    return body + crc16(body)


def parse(qr: str) -> dict:
    """Top-level TLV fields, after checking the CRC. Used by tests and to double-check what we display."""
    if len(qr) < 8 or crc16(qr[:-4]) != qr[-4:]:
        raise KhqrError("KHQR checksum doesn't match.")
    out, i = {}, 0
    while i < len(qr):
        tag, n = qr[i:i + 2], int(qr[i + 2:i + 4])
        out[tag] = qr[i + 4:i + 4 + n]
        i += 4 + n
    return out


def md5(qr: str) -> str:
    return hashlib.md5(qr.encode("utf-8")).hexdigest()


@dataclass
class CheckResult:
    status: str  # paid | failed | not_found
    hash: str | None = None
    from_account: str | None = None
    to_account: str | None = None
    currency: str | None = None
    amount: Decimal | None = None


class BakongClient:
    def __init__(self, base_url: str, token: str, timeout: float = 8.0):
        self.base_url, self.token, self.timeout = base_url.rstrip("/"), token, timeout

    def check_by_md5(self, digest: str) -> CheckResult:
        try:
            with httpx.Client(timeout=self.timeout, transport=TRANSPORT) as c:
                r = c.post(f"{self.base_url}/v1/check_transaction_by_md5", json={"md5": digest},
                           headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        except httpx.HTTPError as e:
            raise BakongUnavailable(f"Bakong didn't answer: {type(e).__name__}") from e
        if r.status_code in (401, 403, 429) or r.status_code >= 500:
            raise BakongUnavailable(f"Bakong returned HTTP {r.status_code}")
        body = r.json()
        if body.get("responseCode") == 0 and body.get("data"):
            d = body["data"]
            return CheckResult("paid", d.get("hash"), d.get("fromAccountId"), d.get("toAccountId"), d.get("currency"), Decimal(str(d.get("amount"))))
        return CheckResult("failed" if body.get("errorCode") == 3 else "not_found")


class BakongGateway:
    """Online payment by dynamic KHQR. The customer scans with any KHQR banking app; RMS confirms by polling Bakong."""

    name = "bakong"
    kind = "qr"

    def __init__(self, s):
        self.s = s
        self.client = BakongClient(s.BAKONG_API_URL, s.BAKONG_API_TOKEN)

    def create_qr(self, bill_number: str, amount: Decimal, currency: str, store_label: str | None = None) -> dict:
        minutes = min(int(self.s.BAKONG_QR_MINUTES), 10)  # NBC: QR time-out shall not exceed 10 minutes
        qr = build_khqr(account_id=self.s.BAKONG_ACCOUNT_ID, merchant_type=self.s.BAKONG_MERCHANT_TYPE, merchant_id=self.s.BAKONG_MERCHANT_ID or None,
                        acquiring_bank=self.s.BAKONG_ACQUIRING_BANK or None, merchant_name=self.s.BAKONG_MERCHANT_NAME, merchant_city=self.s.BAKONG_MERCHANT_CITY,
                        mcc=self.s.BAKONG_MCC, amount=amount, currency=currency, bill_number=bill_number, store_label=store_label)
        return {"qr": qr, "md5": md5(qr), "expires_at": datetime.now(timezone.utc) + timedelta(minutes=minutes)}

    def check(self, digest: str) -> CheckResult:
        return self.client.check_by_md5(digest)

    def receiver_ok(self, result: CheckResult) -> bool:
        return (result.to_account or "").lower() == self.s.BAKONG_ACCOUNT_ID.lower()
