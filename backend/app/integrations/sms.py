"""SMS through PlasGate (Cambodia). From PlasGate's API overview (support.plasgate.com/article/api-overview):

    POST {PLASGATE_API_URL}/rest/send?private_key=<private key>
    Header: X-Secret: <secret>, Content-Type: application/json
    Body:   {"sender": "<sender id>", "to": "855XXXXXXXX", "content": "<text>"}

PlasGate doesn't publish the response body, error codes, delivery reports or Unicode rules, so: any 2xx is treated
as accepted (an id is kept if the body has one), anything else is an error that the worker retries. Messages are
English text until Khmer support is confirmed with PlasGate.
"""
import httpx

TRANSPORT: httpx.BaseTransport | None = None  # tests inject httpx.MockTransport


class SmsError(Exception):
    pass


def msisdn(e164: str) -> str:
    """'+85512345678' -> '85512345678' (PlasGate's examples have no '+')."""
    return e164.lstrip("+")


class PlasGateSender:
    name = "plasgate"

    def __init__(self, base_url: str, private_key: str, secret: str, sender: str, timeout: float = 10.0):
        self.base_url, self.private_key, self.secret, self.sender, self.timeout = base_url.rstrip("/"), private_key, secret, sender, timeout

    def send(self, to: str, content: str) -> str | None:
        try:
            with httpx.Client(timeout=self.timeout, transport=TRANSPORT) as c:
                r = c.post(f"{self.base_url}/rest/send", params={"private_key": self.private_key},
                           headers={"X-Secret": self.secret, "Content-Type": "application/json"},
                           json={"sender": self.sender, "to": to, "content": content})
        except httpx.HTTPError as e:
            raise SmsError(f"PlasGate didn't answer: {type(e).__name__}") from e
        if not 200 <= r.status_code < 300:
            raise SmsError(f"PlasGate returned HTTP {r.status_code}: {r.text[:200]}")
        try:
            body = r.json()
        except ValueError:
            return None
        if isinstance(body, dict):
            for key in ("message_id", "messageId", "id", "queue_id", "data"):
                v = body.get(key)
                if isinstance(v, (str, int)):
                    return str(v)
        return None


def get_sender():
    from app.core.config import get_settings

    s = get_settings()
    if (s.SMS_PROVIDER or "").lower() == "plasgate" and s.PLASGATE_PRIVATE_KEY and s.PLASGATE_SECRET and s.PLASGATE_SENDER:
        return PlasGateSender(s.PLASGATE_API_URL, s.PLASGATE_PRIVATE_KEY, s.PLASGATE_SECRET, s.PLASGATE_SENDER)
    return None
