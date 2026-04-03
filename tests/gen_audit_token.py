import asyncio, sys, os
from datetime import timedelta
sys.path.append("/home/alberto/mi-backend-super")
from utils.auth import create_access_token

async def main():
    # Usamos un ID único de auditoría para evitar locks
    user_id = "iris-audit-v27-999-expert"
    token = await create_access_token(
        data={"sub": user_id},
        expires_delta=timedelta(hours=1)
    )
    print(f"USER_ID:{user_id}")
    print(f"TOKEN_GENERADO:{token}")

if __name__ == "__main__":
    asyncio.run(main())
