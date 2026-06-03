"""Sandboxed Python grading engine that executes user submissions under resource limits."""

import sys
import subprocess
import tempfile
import os
import time
try:
    import resource
except ImportError:
    resource = None
import json
import logging
import threading
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: float
    timed_out: bool
    memory_exceeded: bool


def _set_resource_limits(memory_limit_mb: int):
    """Applies RLIMIT configurations inside the spawned process."""
    if resource is None:
        return
    memory_bytes = memory_limit_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))

class SandboxedRunner:
    """Runs Python submissions in a sandboxed subprocess."""

    BLOCKED_IMPORTS = [
        "socket", "requests", "urllib", "http.client",
        "subprocess", "os.system", "shutil", "ctypes",
        "multiprocessing", "threading", "asyncio",
    ]

    def __init__(self, time_limit_ms: int = 5000, memory_limit_mb: int = 128):
        self.time_limit_ms = time_limit_ms
        self.memory_limit_mb = memory_limit_mb

    def _inject_safety_wrapper(self, code: str) -> str:
        """Adds standard import blocks for safety before running."""
        blocked = json.dumps(self.BLOCKED_IMPORTS)
        wrapper = f"""
import sys
import builtins

_blocked = {blocked}
_real_import = builtins.__import__

def _safe_import(name, *args, **kwargs):
    if any(name == b or name.startswith(b + '.') for b in _blocked):
        raise ImportError(f"Import '{{name}}' is not allowed in the sandbox.")
    return _real_import(name, *args, **kwargs)

builtins.__import__ = _safe_import

# User Code
{code}
"""
        return wrapper

    def run(self, code: str, stdin_data: str = "") -> ExecutionResult:
        import shutil
        safe_code = self._inject_safety_wrapper(code)

        tmpdir = tempfile.mkdtemp(prefix="autograde_")
        code_file = os.path.join(tmpdir, "solution.py")

        start = time.perf_counter()
        try:
            with open(code_file, "w", encoding="utf-8") as f:
                f.write(safe_code)

            timed_out = False
            memory_exceeded = False

            is_windows = sys.platform == "win32"
            python_exe = sys.executable if sys.executable else "python"
            
            popen_kwargs = {
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "cwd": tmpdir,
            }
            if not is_windows:
                popen_kwargs["preexec_fn"] = lambda: _set_resource_limits(self.memory_limit_mb)
                popen_kwargs["env"] = {"PATH": "/usr/bin:/bin"}
            
            proc = subprocess.Popen(
                [python_exe, "-u", code_file],
                **popen_kwargs
            )

            timeout_s = self.time_limit_ms / 1000.0
            try:
                stdout, stderr = proc.communicate(
                    input=stdin_data.encode(),
                    timeout=timeout_s
                )
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
                timed_out = True

            elapsed_ms = (time.perf_counter() - start) * 1000

            stderr_text = stderr.decode(errors="replace")
            if "MemoryError" in stderr_text or "Cannot allocate memory" in stderr_text:
                memory_exceeded = True

            return ExecutionResult(
                stdout=stdout.decode(errors="replace").strip(),
                stderr=stderr_text.strip(),
                exit_code=proc.returncode,
                execution_time_ms=round(elapsed_ms, 2),
                timed_out=timed_out,
                memory_exceeded=memory_exceeded,
            )

        except Exception as e:
            logger.exception("Runner error")
            elapsed_ms = (time.perf_counter() - start) * 1000
            return ExecutionResult(
                stdout="",
                stderr=str(e),
                exit_code=-1,
                execution_time_ms=round(elapsed_ms, 2),
                timed_out=False,
                memory_exceeded=False,
            )
        finally:
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass


@dataclass
class TestCaseResult:
    test_name: str
    passed: bool
    expected_output: str
    actual_output: str
    stderr: str
    execution_time_ms: float
    error_type: Optional[str]


class Grader:
    """Grades user submissions concurrently against test cases."""

    def __init__(self, time_limit_ms: int = 5000, memory_limit_mb: int = 128, max_workers: int = 4):
        self.time_limit_ms = time_limit_ms
        self.memory_limit_mb = memory_limit_mb
        self.max_workers = max_workers

    def grade(self, code: str, test_cases: list[dict]) -> list[TestCaseResult]:
        """
        Grade code against all test cases using concurrent threads.
        test_cases: list of {name, input, expected_output}
        """
        results = [None] * len(test_cases)
        threads = []

        semaphore = threading.Semaphore(self.max_workers)

        def run_test(idx: int, tc: dict):
            with semaphore:
                runner = SandboxedRunner(self.time_limit_ms, self.memory_limit_mb)
                result = runner.run(code, stdin_data=tc.get("input", ""))
                results[idx] = self._evaluate(tc, result)

        for i, tc in enumerate(test_cases):
            t = threading.Thread(target=run_test, args=(i, tc))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        return results

    def _evaluate(self, test_case: dict, result: ExecutionResult) -> TestCaseResult:
        expected = str(test_case.get("expected_output", "")).strip()
        actual = result.stdout.strip()
        name = test_case.get("name", "Test")

        if result.timed_out:
            return TestCaseResult(
                test_name=name, passed=False,
                expected_output=expected, actual_output="",
                stderr=result.stderr,
                execution_time_ms=result.execution_time_ms,
                error_type="timeout"
            )

        if result.memory_exceeded:
            return TestCaseResult(
                test_name=name, passed=False,
                expected_output=expected, actual_output="",
                stderr=result.stderr,
                execution_time_ms=result.execution_time_ms,
                error_type="memory_limit_exceeded"
            )

        if result.exit_code != 0:
            return TestCaseResult(
                test_name=name, passed=False,
                expected_output=expected, actual_output=actual,
                stderr=result.stderr,
                execution_time_ms=result.execution_time_ms,
                error_type="runtime_error"
            )

        passed = actual == expected
        return TestCaseResult(
            test_name=name, passed=passed,
            expected_output=expected, actual_output=actual,
            stderr=result.stderr,
            execution_time_ms=result.execution_time_ms,
            error_type=None if passed else "wrong_answer"
        )
