import asyncio, websockets, json, uuid, time

URL = "ws://localhost:8000/api/unified-chat/ws/aa5de8b2-a83d-4a39-8508-a90c970cc182?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhYTVkZThiMi1hODNkLTRhMzktODUwOC1hOTBjOTcwY2MxODIiLCJleHAiOjE3NzUyNDE3OTIsImlhdCI6MTc3NTIzODE5MiwidHlwZSI6ImFjY2VzcyJ9.6VPve503z8rFxiyBwmxD4DV5j-19EkXrFpDZETVbuKY"

async def test_iris(ws, msg, label):
    rid = uuid.uuid4().hex[:8]
    print(f"\n🧪 [LOCAL TEST: {label}]...")
    start = time.time()
    await ws.send(json.dumps({"message": msg, "request_id": rid}))
    text = ""
    try:
        while True:
            resp = json.loads(await asyncio.wait_for(ws.recv(), 60))
            if resp.get("token"): text += resp["token"]
            elif resp.get("type") in ["done", "error"]: break
    except Exception as e: print(f"   ⚠️ Error: {e}")
    print(f"   ✅ {int((time.time()-start)*1000)}ms | {len(text)} tks")
    return len(text) > 10

async def run():
    async with websockets.connect(URL) as ws:
        await test_iris(ws, "Hola Iris. Búsqueda rápida de IA.", "Local Search")
        await test_iris(ws, "Dime una broma de nerds.", "Local Agent")

if __name__ == "__main__":
    asyncio.run(run())
