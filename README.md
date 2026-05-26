# AutoGrade — Automated Code Grading Platform

A modern, automated code grading platform built in Python. It executes user-submitted code in an isolated sandbox with resource constraints, runs test cases concurrently in a background thread pool, and features a sleek, dark-themed Single Page Application (SPA) web frontend.

---

## Features

- 🖥️ **Sleek Web Frontend**: A premium, dark-mode browser interface to view problems, write Python code with line numbers, run tests, see live status updates, and create custom coding problems.
- ⚙️ **Concurrently Graded Submissions**: Submissions are queued using a thread-pool executor so the Flask API remains responsive.
- 🔒 **Sandboxed Execution**: Subprocesses are spawned in isolated temporary directories with blocklists for dangerous imports (such as `subprocess`, `socket`, `requests`, `os.system`, and `ctypes`).
- 📁 **Unified SQLite Database**: Flat-file database layout storing problems, submissions, and test results with automatic seeding of sample problems.
- 🐳 **Docker Support**: Exposes the application instantly through a lightweight container configuration.

---

## Architecture

```text
autograde/
├── app.py                  # Flask app factory + entry point
├── api/
│   ├── database.py         # Unified SQLite setup, seeding, & query models
│   └── routes.py           # REST API endpoints (submit, status, problems)
├── grader/
│   └── engine.py           # Sandboxed code runner & concurrent grader
├── static/
│   ├── index.html          # Frontend SPA structure
│   ├── index.css           # Premium dark-theme stylesheet
│   └── app.js              # Frontend API integration & reactive state
├── tests/
│   └── test_autograde.py   # Full test suite (pytest)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .gitignore
```

---

## Setup & Run

### 1. Local Development
Make sure you have Flask installed:
```bash
pip install -r requirements.txt
```
Start the server:
```bash
python app.py
```
Open **`http://127.0.0.1:5000/`** in your web browser to access the frontend workspace!

### 2. Docker Container
Build and spin up the container:
```bash
docker-compose up --build
```
The application will be accessible at **`http://127.0.0.1:5000/`**.

---

## API Reference

### Create Problem
`POST /api/problems`
```json
{
  "id": "two-sum",
  "title": "Sum of Two Numbers",
  "description": "Read two numbers and print their sum.",
  "test_cases": [
    { "name": "Basic Case", "input": "3\n4", "expected_output": "7" },
    { "name": "Zeros Case", "input": "0\n0", "expected_output": "0" }
  ],
  "time_limit_ms": 3000,
  "memory_limit_mb": 64
}
```

### Submit Solution
`POST /api/submit`
```json
{
  "problem_id": "two-sum",
  "code": "a = int(input())\nb = int(input())\nprint(a + b)"
}
```
Response (`202 Accepted`):
```json
{
  "submission_id": "528574c8-32a4-4cc9-b7b5-27a372cc6d23",
  "status": "pending"
}
```

### Poll Submission Status
`GET /api/status/<submission_id>`
```json
{
  "id": "528574c8-32a4-4cc9-b7b5-27a372cc6d23",
  "status": "completed",
  "summary": { "total": 2, "passed": 2, "failed": 0, "score": 100.0 },
  "results": [
    {
      "test_name": "Basic Case",
      "passed": true,
      "expected_output": "7",
      "actual_output": "7",
      "execution_time_ms": 32.5,
      "stderr": "",
      "error_type": null
    }
  ]
}
```

### Other Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/problems` | List all coding problems |
| GET | `/api/problems/<id>` | Fetch a specific problem |
| GET | `/api/submissions` | Retrieve recent submissions |
| POST | `/api/batch` | Batch submit (up to 20 solutions) |
| GET | `/api/health` | Service health status |

---

## Sandbox Security Limits
Each submission runs in a separate process with:
- **Time Limits**: Configurable timeout (default 5s) enforced using subprocess communications.
- **Resource Constraints**: Skip limits on Windows, and virtual memory/CPU constraints (`resource.setrlimit`) on POSIX/Linux platforms.
- **Imports Restrictions**: Restricts dangerous modules like `socket`, `subprocess`, `requests`, `urllib`, `os.system`, and `ctypes` inside the sandbox environment.

---

## Running Tests
Run the pytest suite to verify grader reliability and sandboxing rules:
```bash
pytest tests/ -v
```
