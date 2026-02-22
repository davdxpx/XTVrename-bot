import sys
import os
import asyncio

# Mocking config and db for import tests
sys.modules['config'] = type('config', (), {'Config': type('Config', (), {'BOT_TOKEN': '123:ABC', 'API_ID': 123, 'API_HASH': 'abc', 'MAIN_URI': 'mongodb://localhost', 'DB_NAME': 'test', 'SETTINGS_COLLECTION': 'settings', 'CEO_ID': 1, 'FRANCHISEE_IDS': [], 'TMDB_API_KEY': 'abc'})})
sys.modules['database'] = type('database', (), {'db': type('db', (), {'get_settings': None})})

def test_imports():
    try:
        from plugins import start, admin, process, rename_flow
        print("Imports successful")
    except ImportError as e:
        print(f"Import failed: {e}")
        exit(1)

if __name__ == "__main__":
    test_imports()
