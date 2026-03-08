#!/usr/bin/env python3
"""
Script de diagnóstico para verificar el esquema de la base de datos.
Verifica qué tablas y columnas existen realmente.
"""

import asyncio
import os
from sqlalchemy import text
from database.db_enterprise import get_primary_session

async def check_database_schema():
    """Verifica el esquema actual de la base de datos"""
    
    # Tablas a verificar
    tables_to_check = [
        "users",
        "chat_messages", 
        "local_chat_metadata",
        "chat_sync_status",
        "user_permissions",
        "storage_strategy",
        "cost_savings",
        "encryption_keys",
        "whatsapp_chat_messages",
        "chats",
        "calls",
        "contacts",
        "whatsapp_stories",
        "story_views"
    ]
    
    print("🔍 Verificando esquema de base de datos...\n")
    
    session = await get_primary_session()
    async with session:
        for table in tables_to_check:
            try:
                # Verificar si la tabla existe
                result = await session.execute(
                    text("""
                        SELECT column_name, data_type 
                        FROM information_schema.columns 
                        WHERE table_name = :table
                        ORDER BY ordinal_position
                    """),
                    {"table": table}
                )
                columns = result.fetchall()
                
                if columns:
                    print(f"✅ Tabla '{table}' existe con columnas:")
                    for col_name, data_type in columns:
                        print(f"   - {col_name} ({data_type})")
                    print()
                else:
                    print(f"❌ Tabla '{table}' NO existe\n")
                    
            except Exception as e:
                print(f"❌ Error verificando tabla '{table}': {e}\n")

if __name__ == "__main__":
    asyncio.run(check_database_schema())
