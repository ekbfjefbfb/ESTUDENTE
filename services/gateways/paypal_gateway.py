import httpx
import os
import logging
from datetime import datetime, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger("paypal_gateway")
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_SECRET = os.getenv("PAYPAL_SECRET")
PAYPAL_API_URL = "https://api-m.sandbox.paypal.com"  # sandbox o live

class PayPalGateway:
    def __init__(self):
        self.client = httpx.AsyncClient(base_url=PAYPAL_API_URL, timeout=30)
        self._token = None
        self._token_expiry = datetime.utcnow()

    async def _get_token(self):
        if self._token and datetime.utcnow() < self._token_expiry:
            return self._token

        try:
            resp = await self.client.post(
                "/v1/oauth2/token",
                auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
                data={"grant_type": "client_credentials"}
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
            self._token_expiry = datetime.utcnow() + timedelta(seconds=int(data.get("expires_in", 300)) - 30)
            return self._token
        except httpx.HTTPStatusError as e:
            logger.error(f"PayPal token error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"PayPal token exception: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5), reraise=True)
    async def create_payment(self, user_id: str, amount: float, currency: str, metadata: dict):
        if amount <= 0:
            raise ValueError("Amount must be positive")
        token = await self._get_token()
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {"amount": {"currency_code": currency, "value": str(amount)}, "custom_id": user_id}
            ]
        }
        try:
            resp = await self.client.post("/v2/checkout/orders", json=payload, headers={"Authorization": f"Bearer {token}"})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Create payment failed: {e.response.status_code} - {e.response.text}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5), reraise=True)
    async def verify_payment(self, payment_id: str):
        if not payment_id:
            raise ValueError("payment_id is required")
        token = await self._get_token()
        try:
            resp = await self.client.get(f"/v2/checkout/orders/{payment_id}", headers={"Authorization": f"Bearer {token}"})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Verify payment failed: {e.response.status_code} - {e.response.text}")
            raise

    async def get_payment_status(self, payment_id: str):
        info = await self.verify_payment(payment_id)
        return info.get("status")
