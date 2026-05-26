import sqlite3
import os
import json

DB_PATH = os.getenv("DB_PATH", "autograde.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS submissions (
            id TEXT PRIMARY KEY,
            language TEXT DEFAULT 'python',
            code TEXT NOT NULL,
            problem_id TEXT,
            status TEXT DEFAULT 'pending',
            submitted_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id TEXT NOT NULL,
            test_name TEXT NOT NULL,
            passed INTEGER NOT NULL,
            expected_output TEXT,
            actual_output TEXT,
            stderr TEXT,
            execution_time_ms REAL,
            error_type TEXT,
            FOREIGN KEY(submission_id) REFERENCES submissions(id)
        );
        CREATE TABLE IF NOT EXISTS problems (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            test_cases TEXT NOT NULL,
            time_limit_ms INTEGER DEFAULT 5000,
            memory_limit_mb INTEGER DEFAULT 128,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()

    # Seed default problems if table is empty
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM problems")
    if cursor.fetchone()[0] == 0:
        default_problems = [
            {
                "id": "hello-world",
                "title": "Hello World",
                "description": "Write a python program that prints 'Hello, World!' to the console.",
                "test_cases": [
                    {
                        "name": "Correct Output Check",
                        "input": "",
                        "expected_output": "Hello, World!"
                    }
                ],
                "time_limit_ms": 2000,
                "memory_limit_mb": 64
            },
            {
                "id": "double-number",
                "title": "Double the Input",
                "description": "Read a single integer from standard input, and print its value multiplied by 2.",
                "test_cases": [
                    {
                        "name": "Positive Case",
                        "input": "4",
                        "expected_output": "8"
                    },
                    {
                        "name": "Negative Case",
                        "input": "-6",
                        "expected_output": "-12"
                    },
                    {
                        "name": "Zero Case",
                        "input": "0",
                        "expected_output": "0"
                    }
                ],
                "time_limit_ms": 3000,
                "memory_limit_mb": 64
            },
            {
                "id": "square-number",
                "title": "Square the Input",
                "description": "Read a single integer from standard input, and print its square (number multiplied by itself).",
                "test_cases": [
                    {
                        "name": "Basic Square",
                        "input": "5",
                        "expected_output": "25"
                    },
                    {
                        "name": "Negative Square",
                        "input": "-3",
                        "expected_output": "9"
                    }
                ],
                "time_limit_ms": 3000,
                "memory_limit_mb": 64
            }
        ]
        for prob in default_problems:
            cursor.execute(
                "INSERT INTO problems (id, title, description, test_cases, time_limit_ms, memory_limit_mb) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    prob["id"],
                    prob["title"],
                    prob["description"],
                    json.dumps(prob["test_cases"]),
                    prob["time_limit_ms"],
                    prob["memory_limit_mb"]
                )
            )
        conn.commit()
    conn.close()

# ─── Query Helpers ────────────────────────────────────────────────────────────

def get_submission(sub_id):
    db = get_db()
    row = db.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)).fetchone()
    if not row:
        db.close(); return None
    results = db.execute("SELECT * FROM test_results WHERE submission_id=?", (sub_id,)).fetchall()
    db.close()
    return _submission_dict(row, results)

def list_submissions(limit=20, problem_id=None):
    db = get_db()
    if problem_id:
        rows = db.execute("SELECT * FROM submissions WHERE problem_id=? ORDER BY submitted_at DESC LIMIT ?", (problem_id, limit)).fetchall()
    else:
        rows = db.execute("SELECT * FROM submissions ORDER BY submitted_at DESC LIMIT ?", (limit,)).fetchall()
    result = []
    for row in rows:
        results = db.execute("SELECT * FROM test_results WHERE submission_id=?", (row["id"],)).fetchall()
        result.append(_submission_dict(row, results))
    db.close()
    return result

def _submission_dict(row, results):
    res_list = [dict(r) for r in results]
    for r in res_list:
        r["passed"] = bool(r["passed"])
    total = len(res_list)
    passed = sum(1 for r in res_list if r["passed"])
    return {
        "id": row["id"],
        "language": row["language"],
        "problem_id": row["problem_id"],
        "status": row["status"],
        "submitted_at": row["submitted_at"],
        "completed_at": row["completed_at"],
        "results": res_list,
        "summary": {"total": total, "passed": passed, "failed": total - passed,
                    "score": round((passed / total * 100), 1) if total else 0} if total else None,
    }

def get_problem(problem_id):
    db = get_db()
    row = db.execute("SELECT * FROM problems WHERE id=?", (problem_id,)).fetchone()
    db.close()
    if not row: return None
    return _problem_dict(row)

def list_problems():
    db = get_db()
    rows = db.execute("SELECT * FROM problems ORDER BY created_at DESC").fetchall()
    db.close()
    return [_problem_dict(r) for r in rows]

def _problem_dict(row):
    return {
        "id": row["id"], "title": row["title"],
        "description": row["description"],
        "test_cases": json.loads(row["test_cases"]),
        "time_limit_ms": row["time_limit_ms"],
        "memory_limit_mb": row["memory_limit_mb"],
    }
