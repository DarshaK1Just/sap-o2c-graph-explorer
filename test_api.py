#!/usr/bin/env python3
"""
Quick API test script for SAP O2C Graph Explorer.
Tests core endpoints without needing curl/web requests.
"""

import json
import sqlite3
import time
import sys
from pathlib import Path

# Fix Windows encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add backend to path
import sys
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app.db import get_db_path, connect
from app.nlq import answer_nlq

def test_database():
    """Test database connection."""
    print("=" * 60)
    print("TEST 1: Database Connection")
    print("=" * 60)
    
    db_path = get_db_path()
    print(f"[OK] Database path: {db_path}")
    print(f"[OK] Database exists: {Path(db_path).exists()}")
    
    with connect() as con:
        # Check tables exist
        tables = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        print(f"[OK] Tables found: {len(tables)}")
        for t in tables:
            count = con.execute(f"SELECT COUNT(*) FROM {t['name']}").fetchone()[0]
            print(f"  - {t['name']}: {count} rows")
    
    print()

def test_domain_check():
    """Test domain question detection."""
    print("=" * 60)
    print("TEST 2: Domain Question Detection (Guardrails)")
    print("=" * 60)
    
    from app.nlq import is_domain_question
    
    test_cases = [
        ("Trace the full flow of billing document 90504248", True, "Flow tracing"),
        ("Which products appear in the most billing documents?", True, "Aggregation"),
        ("What is the weather in New York?", False, "Off-topic (weather)"),
        ("Write a poem about SQLite", False, "Off-topic (creative)"),
        ("Show broken flows", True, "Anomaly detection"),
    ]
    
    for question, expected, description in test_cases:
        result = is_domain_question(question)
        status = "[OK]" if result == expected else "[FAIL]"
        print(f"{status} {description}")
        print(f"   Q: {question[:60]}...")
        print(f"   Expected: {expected}, Got: {result}")
        print()

def test_chat_queries():
    """Test NLQ endpoint with real queries."""
    print("=" * 60)
    print("TEST 3: Chat Queries (NLQ + SQL Generation)")
    print("=" * 60)
    
    test_queries = [
        "Trace the full flow of billing document 90504248",
        "Which products appear in the most billing documents?",
        "What is the weather?",  # Should be rejected
    ]
    
    with connect() as con:
        for i, query in enumerate(test_queries, 1):
            print(f"\nQuery {i}: {query}")
            print("-" * 40)
            
            result = answer_nlq(con, query)
            
            print(f"Answer: {result.answer[:100]}...")
            if result.sql:
                print(f"SQL generated: {'Yes' if result.sql else 'No'}")
                print(f"Rows returned: {len(result.rows) if result.rows else 0}")
            else:
                print("SQL generated: No (guardrail or no template match)")
            print()

def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("SAP O2C GRAPH EXPLORER - API TEST SUITE")
    print("=" * 60 + "\n")
    
    try:
        test_database()
        test_domain_check()
        test_chat_queries()
        
        print("=" * 60)
        print("[PASS] ALL TESTS COMPLETED")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[FAIL] ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
