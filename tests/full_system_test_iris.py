import asyncio, websockets, json, uuid, time

# --- CONFIGURACIÓN DE AUDITORÍA REAL ---
USER_ID = "aa5de8b2-a83d-4a39-8508-a90c970cc182"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhYTVkZThiMi1hODNkLTRhMzktODUwOC1hOTBjOTcwY2MxODIiLCJleHAiOjE3NzUyNDE3OTIsImlhdCI6MTc3NTIzODE5MiwidHlwZSI6ImFjY2VzcyJ9.6VPve503z8rFxiyBwmxD4DV5j-19EkXrFpDZETVbuKY"
WS_URL = f"wss://estudente-msba.onrender.com/api/unified-chat/ws/{USER_ID}?token={TOKEN}"

async def test_iris(ws, msg, label):
    rid = uuid.uuid4().hex[:8]
    print(f"\n🧪 [TEST: {label}]...")
    start = time.time()
    await ws.send(json.dumps({"message": msg, "request_id": rid}))
    text, agents, search = "", False, False
    try:
        while True:
            # 180s para tareas pesadas en Render
            resp = json.loads(await asyncio.wait_for(ws.recv(), 180))
            if resp.get("type") == "status":
                c = resp["content"].lower()
                if any(x in c for x in ["equipo", "experto", "investigación"]): agents = True
                if any(x in c for x in ["buscando", "🔍", "fuentes"]): search = True
                print(f"   ⚙️ {resp['content']}")
            elif resp.get("type") == "token": 
                text += resp.get("token", "")
            elif resp.get("type") in ["done", "error"]: 
                break
    except Exception as e: print(f"   ⚠️ Timeout/Error en {label}: {e}")
    print(f"   ✅ {int((time.time()-start)*1000)}ms | {len(text)} tks | Agents: {agents} | Search: {search}")
    return len(text) > 30

async def run_audit():
    print("🏛️ AUDIT TOTAL IRIS v28.5 - TOKEN REAL RENDER\n" + "="*50)
    async with websockets.connect(WS_URL, open_timeout=90, ping_interval=None) as ws:
        # 1. Búsqueda
        await test_iris(ws, "Hola Iris. Búsqueda: ¿Noticias de IA hoy 3 de Abril 2026?", "Búsqueda Web")
        # 2. YouTube
        await test_iris(ws, "Resumen breve: https://www.youtube.com/watch?v=0fKBhvDjuy0", "YouTube Analysis")
        # 3. Agentes
        await test_iris(ws, "Resuelve la integral de x*log(x) paso a paso.", "Expert Team (AutoGen)")
        # 4. Memoria Progresiva
        await test_iris(ws, "Recuerda mi clave: K_IRIS = 3.1416.", "Memoria (Def)")
        await test_iris(ws, "¿Cuál era mi clave K_IRIS?", "Memoria (Rec)")

if __name__ == "__main__":
    asyncio.run(run_audit())
