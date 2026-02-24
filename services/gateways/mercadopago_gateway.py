import httpx
import os
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger("mercadopago_gateway")
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
MP_API_URL = "https://api.mercadopago.com/v1"

class MercadoPagoGateway:
    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=MP_API_URL,
            timeout=30,
            headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5), reraise=True)
    async def create_payment(self, user_id: str, amount: float, currency: str, metadata: dict):
        if amount <= 0:
            raise ValueError("Amount must be positive")
        payload = {
            "transaction_amount": amount,
            "currency_id": currency,
            "payer": {"email": f"{user_id}@example.com"},
            "metadata": metadata
        }
        try:
            resp = await self.client.post("/payments", json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Create payment failed: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Create payment exception: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5), reraise=True)
    async def verify_payment(self, payment_id: str):
        if not payment_id:
            raise ValueError("payment_id is required")
        try:
            resp = await self.client.get(f"/payments/{payment_id}")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Verify payment failed: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Verify payment exception: {e}")
            raise

    async def get_payment_status(self, payment_id: str):
        info = await self.verify_payment(payment_id)
        return info.get("status")
