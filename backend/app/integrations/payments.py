"""Payment gateway adapters (FR-ONL-007).

Card data never reaches RMS: the customer pays on the provider's hosted page, and RMS only trusts a signed
server-to-server callback. No real provider is integrated yet (SRS V-06, RK-10). ``SandboxGateway`` lets the
flow be built and tested end to end; it is refused when APP_ENV is production.
"""
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from decimal import Decimal

from app.core.config import get_settings


@dataclass
class Checkout:
    session_ref: str
    redirect_url: str


class SandboxGateway:
    name = "sandbox"
    kind = "redirect"

    def __init__(self, secret: str):
        self._secret = secret.encode()

    def create_checkout(self, order_no: str, amount: Decimal, currency: str) -> Checkout:
        ref = f"SBX-{secrets.token_urlsafe(18)}"
        return Checkout(ref, f"{get_settings().FRONTEND_URL.split(',')[0].rstrip('/')}/pay/sandbox?session={ref}&amount={amount}&currency={currency}")

    def sign(self, body: bytes) -> str:
        return hmac.new(self._secret, body, hashlib.sha256).hexdigest()

    def verify(self, body: bytes, signature: str | None) -> dict | None:
        """Returns the parsed callback only when the HMAC-SHA256 signature matches (constant-time compare)."""
        if not signature or not hmac.compare_digest(self.sign(body), signature):
            return None
        return json.loads(body)


def get_gateway(name: str | None = None):
    """The configured gateway, or None when online payment isn't available. Bakong needs its account, name and API token."""
    s = get_settings()
    configured = (s.PAYMENT_GATEWAY or "").lower()
    if name and name.lower() != configured:
        return None
    if configured == "sandbox" and s.PAYMENT_SANDBOX_SECRET and s.APP_ENV != "production":
        return SandboxGateway(s.PAYMENT_SANDBOX_SECRET)
    if configured == "bakong" and s.BAKONG_ACCOUNT_ID and s.BAKONG_MERCHANT_NAME and s.BAKONG_API_TOKEN:
        from app.integrations.bakong import BakongGateway

        return BakongGateway(s)
    return None
