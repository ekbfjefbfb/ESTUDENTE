#!/usr/bin/env python3
"""
Test rápido de imports del backend
"""
import sys
import traceback

def test_imports():
    """Test de imports críticos"""
    try:
        print("1. Testing config...")
        import config
        print("   ✓ Config OK")
        
        print("2. Testing models...")
        from models import models
        print("   ✓ Models OK")
        
        print("3. Testing database...")
        from database import db_enterprise
        print("   ✓ Database OK")
        
        print("4. Testing utils.safe_metrics...")
        from utils import safe_metrics
        print("   ✓ Safe metrics OK")
        
        print("5. Testing utils.auth...")
        from utils import auth
        print("   ✓ Auth OK")
        
        print("6. Testing main app...")
        from main import app
        print("   ✓ Main app OK")
        
        print("\n✅ ALL IMPORTS SUCCESSFUL!")
        return 0
        
    except Exception as e:
        print(f"\n❌ IMPORT FAILED: {e}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(test_imports())
