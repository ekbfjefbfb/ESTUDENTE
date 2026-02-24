import httpx
import os
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger("yappy_gateway")
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

YAPPY_API_KEY = os.getenv("YAPPY_API_KEY")
YAPPY_API_URL = "https://api.yappy.com.hn/v1"

class YappyGateway:
    def __init__(self):
        self.client = httpx.AsyncClient(base_url=YAPPY_API_URL, timeout=30)
        self.headers = {"Authorization": f"Bearer {YAPPY_API_KEY}"}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5), reraise=True)
    async def create_payment(self, user_id: str, amount: float, currency: str, metadata: dict):
        if amount <= 0:
            raise ValueError("Amount must be positive")
        payload = {"amount": amount, "currency": currency, "user_id": user_id, "metadata": metadata}
        try:
            resp = await self.client.post("/payments", json=payload, headers=self.headers)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Yappy create payment failed: {e.response.status_code} - {e.response.text}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5), reraise=True)
    async def verify_payment(self, payment_id: str):
        if not payment_id:
            raise ValueError("payment_id is required")
        try:
            resp = await self.client.get(f"/payments/{payment_id}", headers=self.headers)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Yappy verify payment failed: {e.response.status_code} - {e.response.text}")
            raise

    async def get_payment_status(self, payment_id: str):
        info = await self.verify_payment(payment_id)
        return info.get("status")
