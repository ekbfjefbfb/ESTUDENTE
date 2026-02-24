import httpx
import os
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger("visa_gateway")
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

VISA_API_KEY = os.getenv("VISA_API_KEY")
VISA_API_URL = os.getenv("VISA_API_URL", "https://api.visa.com/v1")
VISA_CLIENT_ID = os.getenv("VISA_CLIENT_ID")
VISA_CLIENT_SECRET = os.getenv("VISA_CLIENT_SECRET")

class VisaGateway:
    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=VISA_API_URL, 
            timeout=30,
            headers={
                "Authorization": f"Bearer {VISA_API_KEY}",
                "Content-Type": "application/json"
            }
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5), reraise=True)
    async def create_payment(self, user_id: str, amount: float, currency: str, metadata: dict):
        if amount <= 0:
            raise ValueError("Amount must be positive")
            
        payload = {
            "amount": amount,
            "currency": currency,
            "customer_id": user_id,
            "metadata": metadata,
            "payment_method": "visa"
        }
        
        try:
            resp = await self.client.post("/payments", json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Visa create payment failed: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Visa create payment exception: {e}")
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
            logger.error(f"Visa verify payment failed: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Visa verify payment exception: {e}")
            raise

    async def get_payment_status(self, payment_id: str):
        info = await self.verify_payment(payment_id)
        return info.get("status")