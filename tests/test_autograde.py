"""
AutoGrade Test Suite
Tests for grading engine, sandbox security, and API endpoints.
"""

import pytest
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from grader.engine import SandboxedRunner, Grader


# ─── SandboxedRunner Tests ────────────────────────────────────────────────────

class TestSandboxedRunner:

    def setup_method(self):
        self.runner = SandboxedRunner(time_limit_ms=3000, memory_limit_mb=64)

    def test_correct_hello_world(self):
        code = 'print("Hello, World!")'
        result = self.runner.run(code)
        assert result.stdout == "Hello, World!"
        assert result.exit_code == 0
        assert not result.timed_out

    def test_stdout_with_stdin(self):
        code = "n = int(input())\nprint(n * 2)"
        result = self.runner.run(code, stdin_data="21")
        assert result.stdout == "42"

    def test_runtime_error(self):
        code = "print(1 / 0)"
        result = self.runner.run(code)
        assert result.exit_code != 0
        assert "ZeroDivisionError" in result.stderr

    def test_syntax_error(self):
        code = "def broken(:"
        result = self.runner.run(code)
        assert result.exit_code != 0

    def test_timeout_enforcement(self):
        code = "while True: pass"
        runner = SandboxedRunner(time_limit_ms=500, memory_limit_mb=64)
        result = runner.run(code)
        assert result.timed_out

    def test_blocked_socket_import(self):
        code = "import socket\nprint('escaped')"
        result = self.runner.run(code)
        assert result.exit_code != 0
        assert "not allowed" in result.stderr or "ImportError" in result.stderr

    def test_blocked_subprocess(self):
        code = "import subprocess\nsubprocess.run(['ls'])"
        result = self.runner.run(code)
        assert result.exit_code != 0

    def test_multiline_output(self):
        code = "for i in range(5):\n    print(i)"
        result = self.runner.run(code)
        assert result.stdout == "0\n1\n2\n3\n4"

    def test_execution_time_tracked(self):
        code = "import time\ntime.sleep(0.1)\nprint('done')"
        result = self.runner.run(code)
        assert result.execution_time_ms >= 100
        assert result.stdout == "done"


# ─── Grader Tests ─────────────────────────────────────────────────────────────

class TestGrader:

    def setup_method(self):
        self.grader = Grader(time_limit_ms=3000, memory_limit_mb=64, max_workers=2)

    def test_all_pass(self):
        code = "n = int(input())\nprint(n * n)"
        test_cases = [
            {"name": "Test 1", "input": "3", "expected_output": "9"},
            {"name": "Test 2", "input": "5", "expected_output": "25"},
            {"name": "Test 3", "input": "0", "expected_output": "0"},
        ]
        results = self.grader.grade(code, test_cases)
        assert len(results) == 3
        assert all(r.passed for r in results)

    def test_partial_pass(self):
        code = "n = int(input())\nprint(n + 1)"  # Wrong logic
        test_cases = [
            {"name": "Test 1", "input": "1", "expected_output": "1"},  # Fail
            {"name": "Test 2", "input": "4", "expected_output": "5"},  # Pass
        ]
        results = self.grader.grade(code, test_cases)
        assert results[0].passed is False
        assert results[1].passed is True

    def test_wrong_answer_error_type(self):
        code = 'print("wrong")'
        test_cases = [{"name": "T1", "input": "", "expected_output": "right"}]
        results = self.grader.grade(code, test_cases)
        assert results[0].error_type == "wrong_answer"

    def test_runtime_error_type(self):
        code = "raise ValueError('oops')"
        test_cases = [{"name": "T1", "input": "", "expected_output": "anything"}]
        results = self.grader.grade(code, test_cases)
        assert results[0].error_type == "runtime_error"

    def test_timeout_error_type(self):
        code = "while True: pass"
        grader = Grader(time_limit_ms=400, memory_limit_mb=64)
        test_cases = [{"name": "T1", "input": "", "expected_output": "done"}]
        results = grader.grade(code, test_cases)
        assert results[0].error_type == "timeout"

    def test_concurrent_execution(self):
        """Multiple tests run concurrently and all complete."""
        code = "n = int(input())\nprint(n ** 2)"
        test_cases = [{"name": f"T{i}", "input": str(i), "expected_output": str(i**2)} for i in range(6)]
        results = self.grader.grade(code, test_cases)
        assert len(results) == 6
        assert all(r.passed for r in results)


# ─── API Tests ────────────────────────────────────────────────────────────────

class TestAPI:

    @pytest.fixture
    def client(self):
        import os
        from app import create_app
        from api.database import init_db
        
        test_db = "test_autograde.db"
        os.environ["DB_PATH"] = test_db
        
        # Ensure fresh database setup
        if os.path.exists(test_db):
            try:
                os.remove(test_db)
            except Exception:
                pass
        
        app = create_app()
        app.config["TESTING"] = True
        
        with app.app_context():
            init_db()
            
        with app.test_client() as client:
            yield client
            
        # Cleanup database file after tests
        if os.path.exists(test_db):
            try:
                os.remove(test_db)
            except Exception:
                pass

    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.get_json()["status"] == "ok"

    def test_submit_with_inline_tests(self, client):
        payload = {
            "code": "print(int(input()) * 2)",
            "test_cases": [
                {"name": "T1", "input": "3", "expected_output": "6"},
                {"name": "T2", "input": "10", "expected_output": "20"},
            ]
        }
        r = client.post("/api/submit", json=payload)
        assert r.status_code == 202
        data = r.get_json()
        assert "submission_id" in data

    def test_submit_missing_code(self, client):
        r = client.post("/api/submit", json={"test_cases": []})
        assert r.status_code == 400

    def test_create_and_get_problem(self, client):
        payload = {
            "id": "two-sum",
            "title": "Two Sum",
            "description": "Return a + b",
            "test_cases": [
                {"name": "T1", "input": "1\n2", "expected_output": "3"}
            ]
        }
        r = client.post("/api/problems", json=payload)
        assert r.status_code == 201

        r2 = client.get("/api/problems/two-sum")
        assert r2.status_code == 200
        assert r2.get_json()["title"] == "Two Sum"

    def test_status_not_found(self, client):
        r = client.get("/api/status/nonexistent-id")
        assert r.status_code == 404

    def test_batch_submit(self, client):
        payload = {
            "submissions": [
                {"code": "print('a')", "test_cases": [{"name": "T1", "input": "", "expected_output": "a"}]},
                {"code": "print('b')", "test_cases": [{"name": "T1", "input": "", "expected_output": "b"}]},
            ]
        }
        r = client.post("/api/batch", json=payload)
        assert r.status_code == 202
        data = r.get_json()
        assert data["submitted"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
