import asyncio
import time
import logging

from notes_grpc.extractor import extract_note_segmented
from notes_grpc.groq_client import GroqClient
from services.groq_ai_service import GROQ_LLM_REASONING_MODEL

logging.basicConfig(level=logging.INFO)

async def main():
    print(f"Model used for Reasoning: {GROQ_LLM_REASONING_MODEL}")
    
    # Generate 150,000 chars of fake transcript (approx 3 hours of speech)
    sentence = "El profesor explicó que la fotosíntesis es fundamental para las plantas. Luego nos asignó un proyecto para el lunes sobre el ciclo de Krebs. "
    fake_transcript = sentence * 1100  # ~159,500 chars

    print(f"Transcript size: {len(fake_transcript)} characters.")
    
    client = GroqClient()
    start_time = time.time()
    
    try:
        extracted = await extract_note_segmented(
            client=client,
            transcript=fake_transcript,
            title_hint="Clase de Biología Intensiva (3 Horas de Prueba Real Backend)",
            max_chunk_chars=15000
        )
        print("====== SUCCESS ======")
        print(f"Title: {extracted.title}")
        print(f"Summary generated: {len(extracted.summary)} chars")
        print(f"Key Points: {len(extracted.key_points)}")
        print(f"Tasks extracted: {len(extracted.tasks)}")
    except Exception as e:
        print(f"FAILED with exception: {e}")
    finally:
        print(f"Total processing time: {time.time() - start_time:.2f} seconds.")

if __name__ == "__main__":
    asyncio.run(main())
