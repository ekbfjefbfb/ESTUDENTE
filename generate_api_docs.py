#!/usr/bin/env python3
"""
API Documentation Generator
Genera documentación automática de todos los endpoints con ejemplos
Versión: 1.0 - Noviembre 2025
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List

def get_app():
    """Importa y retorna la app de FastAPI"""
    sys.path.insert(0, str(Path(__file__).parent))
    from main import app
    return app

def generate_api_docs() -> Dict[str, Any]:
    """
    Genera documentación completa de la API
    
    Returns:
        Dict con toda la información de endpoints
    """
    app = get_app()
    
    docs = {
        "info": {
            "title": app.title,
            "version": app.version,
            "description": app.description,
        },
        "endpoints": [],
        "total_endpoints": 0,
        "categories": {}
    }
    
    # Iterar sobre todas las rutas
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            methods = [m for m in route.methods if m != "HEAD"]
            
            if not methods:
                continue
            
            endpoint_info = {
                "path": route.path,
                "methods": methods,
                "name": route.name,
                "tags": getattr(route, "tags", []),
                "summary": None,
                "description": None,
                "parameters": [],
                "request_body": None,
                "responses": {},
            }
            
            # Obtener docstring si existe
            if hasattr(route, "endpoint") and route.endpoint:
                if route.endpoint.__doc__:
                    docstring = route.endpoint.__doc__.strip()
                    lines = docstring.split("\n")
                    endpoint_info["summary"] = lines[0] if lines else None
                    endpoint_info["description"] = "\n".join(lines[1:]).strip() if len(lines) > 1 else None
            
            docs["endpoints"].append(endpoint_info)
            
            # Categorizar por tags
            for tag in endpoint_info["tags"]:
                if tag not in docs["categories"]:
                    docs["categories"][tag] = []
                docs["categories"][tag].append(endpoint_info)
    
    docs["total_endpoints"] = len(docs["endpoints"])
    
    return docs

def generate_markdown_docs(docs: Dict[str, Any]) -> str:
    """
    Genera documentación en formato Markdown
    
    Args:
        docs: Documentación generada
        
    Returns:
        String con Markdown
    """
    md = f"""# {docs['info']['title']} - API Documentation

**Version:** {docs['info']['version']}

{docs['info']['description']}

---

## 📊 Summary

- **Total Endpoints:** {docs['total_endpoints']}
- **Categories:** {len(docs['categories'])}

---

## 📋 Categories

"""
    
    # Listar categorías
    for category, endpoints in sorted(docs['categories'].items()):
        md += f"### {category} ({len(endpoints)} endpoints)\n\n"
        
        for endpoint in endpoints:
            methods_str = ", ".join(endpoint['methods'])
            md += f"#### `{methods_str}` {endpoint['path']}\n\n"
            
            if endpoint['summary']:
                md += f"{endpoint['summary']}\n\n"
            
            if endpoint['description']:
                md += f"**Description:**\n\n{endpoint['description']}\n\n"
            
            md += "---\n\n"
    
    return md

def generate_postman_collection(docs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Genera colección de Postman
    
    Args:
        docs: Documentación generada
        
    Returns:
        Dict con formato Postman Collection v2.1
    """
    collection = {
        "info": {
            "name": docs['info']['title'],
            "description": docs['info']['description'],
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
        },
        "item": []
    }
    
    # Agrupar por categorías
    for category, endpoints in sorted(docs['categories'].items()):
        folder = {
            "name": category,
            "item": []
        }
        
        for endpoint in endpoints:
            for method in endpoint['methods']:
                request_item = {
                    "name": endpoint['name'] or endpoint['path'],
                    "request": {
                        "method": method,
                        "header": [
                            {
                                "key": "Content-Type",
                                "value": "application/json"
                            },
                            {
                                "key": "Authorization",
                                "value": "Bearer {{access_token}}"
                            }
                        ],
                        "url": {
                            "raw": "{{base_url}}" + endpoint['path'],
                            "host": ["{{base_url}}"],
                            "path": endpoint['path'].strip("/").split("/")
                        }
                    },
                    "response": []
                }
                
                folder["item"].append(request_item)
        
        collection["item"].append(folder)
    
    return collection

def main():
    """Función principal"""
    print("🚀 Generating API documentation...")
    
    try:
        # Generar docs
        docs = generate_api_docs()
        
        print(f"✅ Found {docs['total_endpoints']} endpoints in {len(docs['categories'])} categories")
        
        # Guardar JSON
        output_dir = Path("docs/api")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        with open(output_dir / "endpoints.json", "w", encoding="utf-8") as f:
            json.dump(docs, f, indent=2, ensure_ascii=False)
        print(f"✅ JSON docs saved: docs/api/endpoints.json")
        
        # Guardar Markdown
        markdown = generate_markdown_docs(docs)
        with open(output_dir / "API_REFERENCE.md", "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"✅ Markdown docs saved: docs/api/API_REFERENCE.md")
        
        # Guardar Postman Collection
        postman = generate_postman_collection(docs)
        with open(output_dir / "postman_collection.json", "w", encoding="utf-8") as f:
            json.dump(postman, f, indent=2, ensure_ascii=False)
        print(f"✅ Postman collection saved: docs/api/postman_collection.json")
        
        print("\n✨ Documentation generation complete!")
        
    except Exception as e:
        print(f"❌ Error generating docs: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
