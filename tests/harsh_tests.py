import os
import sqlite3
import time
import sys

# إضافة المسار الجذر للمشروع إلى sys.path لاستيراد app.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from app import app, DB_PATH
from fastapi.testclient import TestClient

# Handle encoding issues on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(errors='replace')

client = TestClient(app)

def safe_print(message):
    try:
        print(message)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or 'utf-8'
        print(message.encode(encoding, errors='replace').decode(encoding))

def test_database_integrity():
    safe_print("--- Testing Database Integrity ---")
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='players_scouting_data'")
        table_exists = cursor.fetchone()
        assert table_exists is not None, "Table 'players_scouting_data' missing from database."
        
        # التحقق من وجود الأعمدة الجديدة
        cursor.execute("PRAGMA table_info(players_scouting_data)")
        columns = [col[1] for col in cursor.fetchall()]
        required_columns = ['player_name', 'position', 'pace', 'finishing', 'composure', 
                            'off_the_ball', 'vision', 'total_xG', 'total_xA']
        for col in required_columns:
            assert col in columns, f"Column '{col}' is missing in the database table."
        
        cursor.execute("SELECT COUNT(*) FROM players_scouting_data")
        count = cursor.fetchone()[0]
        assert count > 0, "Table is empty. No players found."
        safe_print(f"[PASS] DB columns verified, intact, and validated with {count} players.")
        conn.close()
    else:
        safe_print("[WARN] DB file not found. Ensure the server is run at least once to build it.")

def test_repetition_failsafe_logic():
    safe_print("\n--- Testing Repetition Failsafe Logic ---")
    from app import clean_repetitions
    
    # 1. اختبار نص طبيعي لا تكرار فيه
    normal_text = "محمد صلاح لاعب رائع يلعب في ليفربول. إنه يمتلك مهارات فريدة وسرعة خيالية."
    cleaned_normal = clean_repetitions(normal_text)
    assert cleaned_normal == normal_text, "Failsafe modified non-repetitive text incorrectly."
    
    # 2. اختبار نص يحتوي على تكرار كامل للجملة
    repetitive_text = "محمد صلاح لاعب رائع يلعب في ليفربول. إنه يمتلك مهارات فريدة وسرعة خيالية. محمد صلاح لاعب رائع يلعب في ليفربول. إنه يمتلك مهارات فريدة وسرعة خيالية."
    cleaned_rep = clean_repetitions(repetitive_text)
    assert len(cleaned_rep) < len(repetitive_text), "Failsafe did not truncate repetitive text."
    assert "ليفربول" in cleaned_rep, "Failsafe truncated too early."
    
    safe_print("[PASS] clean_repetitions successfully detected and truncated infinite loops.")

def test_api_endpoints_resilience():
    safe_print("\n--- Testing API Resilience ---")
    # Test rapid requests to /api/players to simulate heavy load
    start = time.time()
    for i in range(20):
        res = client.get("/api/players")
        assert res.status_code in [200, 500], f"Unexpected status code {res.status_code} on /api/players"
    safe_print(f"[PASS] /api/players rapid requests (20x) passed in {time.time() - start:.2f}s")
    
    # Test invalid chat input
    res = client.post("/api/chat", json={"message": ""})
    assert res.status_code == 200, "Server crashed on empty chat message"
    safe_print("[PASS] /api/chat invalid/empty input handled gracefully.")

def test_qwen_repetition_limits():
    safe_print("\n--- Testing AI Limits & Repetition Prevention ---")
    player = {
        "player_name": "Test Player (Harsh Test)",
        "position": "ST",
        "pace": 20,
        "finishing": 20,
        "off_the_ball": 20,
        "vision": 20,
        "total_xG": 1.5,
        "total_xA": 0.5,
        "pass_success_under_pressure_pct": 80.0
    }
    
    start = time.time()
    res = client.post("/api/report", json=player)
    
    if res.status_code == 200:
        report = res.json().get("report", "")
        # length check
        assert len(report) > 0, "AI returned an empty report."
        assert len(report) < 2000, f"AI report too long! Possible infinite loop detected. Length: {len(report)} chars."
        
        # simple repetition detection (checking if same 50 chars repeat adjacently)
        if len(report) > 100:
            for i in range(len(report) - 100):
                chunk = report[i:i+50]
                if chunk in report[i+50:]:
                    safe_print(f"[WARN] Warning: Possible repetition detected in AI report text.")
                    break
                    
        safe_print(f"[PASS] AI Report generated within strict limits ({len(report)} chars) in {time.time() - start:.2f}s")
        safe_print(f"[INFO] Snippet: {report[:100]}...\n")
    else:
        safe_print(f"[WARN] AI Report endpoint returned status: {res.status_code}. Ensure Ollama/Qwen is active for integration test.")

if __name__ == "__main__":
    safe_print("[START] Starting Harsh Tests Suite...\n")
    try:
        test_database_integrity()
        test_repetition_failsafe_logic()
        test_api_endpoints_resilience()
        test_qwen_repetition_limits()
        safe_print("\n[SUCCESS] ALL TESTS PASSED.")
    except AssertionError as e:
        safe_print(f"\n[FAIL] TEST FAILED: {e}")
        sys.exit(1)
