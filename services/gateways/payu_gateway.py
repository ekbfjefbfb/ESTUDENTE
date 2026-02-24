import httpx
import os
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger("payu_gateway")
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

PAYU_API_KEY = os.getenv("PAYU_API_KEY")
PAYU_API_URL = "https://api.payu.com/v2.1"

class PayUGateway:
    def __init__(self):
        self.client = httpx.AsyncClient(base_url=PAYU_API_URL, timeout=30)
        self.headers = {"Authorization": f"Bearer {PAYU_API_KEY}"}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5), reraise=True)
    async def create_payment(self, user_id: str, amount: float, currency: str, metadata: dict):
        if amount <= 0:
            raise ValueError("Amount must be positive")
        payload = {"amount": amount, "currency": currency, "buyer": {"id": user_id}, "metadata": metadata}
        try:
            resp = await self.client.post("/orders", json=payload, headers=self.headers)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"PayU create payment failed: {e.response.status_code} - {e.response.text}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5), reraise=True)
    async def verify_payment(self, payment_id: str):
        if not payment_id:
            raise ValueError("payment_id is required")
        try:
            resp = await self.client.get(f"/orders/{payment_id}", headers=self.headers)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"PayU verify payment failed: {e.response.status_code} - {e.response.text}")
            raise

    async def get_payment_status(self, payment_id: str):
        info = await self.verify_payment(payment_id)
        return info.get("status")
