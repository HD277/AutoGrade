"""REST API endpoints for the AutoGrade platform."""
import json, uuid, logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, request, jsonify
from api.database import get_db, get_submission, list_submissions, get_problem, list_problems
from grader.engine import Grader

api_bp = Blueprint("api", __name__)
logger = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=4)

# Helpers

def _run_grading_job(submission_id, code, test_cases, time_limit_ms, memory_limit_mb):
    db = get_db()
    db.execute("UPDATE submissions SET status='running' WHERE id=?", (submission_id,))
    db.commit()
    try:
        grader = Grader(time_limit_ms=time_limit_ms, memory_limit_mb=memory_limit_mb)
        results = grader.grade(code, test_cases)
        for r in results:
            db.execute("""INSERT INTO test_results
                (submission_id, test_name, passed, expected_output, actual_output, stderr, execution_time_ms, error_type)
                VALUES (?,?,?,?,?,?,?,?)""",
                (submission_id, r.test_name, int(r.passed), r.expected_output,
                 r.actual_output, r.stderr, r.execution_time_ms, r.error_type))
        db.execute("UPDATE submissions SET status='completed', completed_at=? WHERE id=?",
                   (datetime.utcnow().isoformat(), submission_id))
        db.commit()
        logger.info(f"[{submission_id}] Completed — {len(results)} tests.")
    except Exception as e:
        logger.exception(f"[{submission_id}] Grading failed: {e}")
        db.execute("UPDATE submissions SET status='failed', completed_at=? WHERE id=?",
                   (datetime.utcnow().isoformat(), submission_id))
        db.commit()
    finally:
        db.close()


@api_bp.route("/submit", methods=["POST"])
def submit():
    data = request.get_json(silent=True) or {}
    code = data.get("code", "").strip()
    if not code:
        return jsonify({"error": "code is required"}), 400

    problem_id = data.get("problem_id")
    custom_tests = data.get("test_cases")

    if custom_tests:
        test_cases = custom_tests
        time_limit_ms = data.get("time_limit_ms", 5000)
        memory_limit_mb = data.get("memory_limit_mb", 128)
    elif problem_id:
        prob = get_problem(problem_id)
        if not prob:
            return jsonify({"error": f"Problem '{problem_id}' not found"}), 404
        test_cases = prob["test_cases"]
        time_limit_ms = prob["time_limit_ms"]
        memory_limit_mb = prob["memory_limit_mb"]
    else:
        return jsonify({"error": "Provide problem_id or test_cases"}), 400

    sub_id = str(uuid.uuid4())
    db = get_db()
    db.execute("INSERT INTO submissions (id, code, problem_id) VALUES (?,?,?)", (sub_id, code, problem_id))
    db.commit(); db.close()

    _pool.submit(_run_grading_job, sub_id, code, test_cases, time_limit_ms, memory_limit_mb)
    return jsonify({"submission_id": sub_id, "status": "pending",
                    "message": "Poll /api/status/<submission_id> for results."}), 202


@api_bp.route("/status/<submission_id>")
def get_status(submission_id):
    sub = get_submission(submission_id)
    if not sub:
        return jsonify({"error": "Submission not found"}), 404
    return jsonify(sub)


@api_bp.route("/problems", methods=["POST"])
def create_problem():
    data = request.get_json(silent=True) or {}
    for f in ["id", "title", "test_cases"]:
        if not data.get(f):
            return jsonify({"error": f"Missing: {f}"}), 400
    if get_problem(data["id"]):
        return jsonify({"error": "Problem already exists"}), 409
    db = get_db()
    db.execute("INSERT INTO problems (id, title, description, test_cases, time_limit_ms, memory_limit_mb) VALUES (?,?,?,?,?,?)",
               (data["id"], data["title"], data.get("description",""),
                json.dumps(data["test_cases"]), data.get("time_limit_ms",5000), data.get("memory_limit_mb",128)))
    db.commit(); db.close()
    return jsonify(get_problem(data["id"])), 201

@api_bp.route("/problems")
def get_problems():
    return jsonify(list_problems())

@api_bp.route("/problems/<problem_id>")
def get_problem_route(problem_id):
    prob = get_problem(problem_id)
    if not prob: return jsonify({"error": "Not found"}), 404
    return jsonify(prob)


@api_bp.route("/batch", methods=["POST"])
def batch_submit():
    data = request.get_json(silent=True) or {}
    items = data.get("submissions", [])
    if not items: return jsonify({"error": "submissions required"}), 400
    if len(items) > 20: return jsonify({"error": "Max 20 per batch"}), 400
    ids = []
    db = get_db()
    for item in items:
        code = item.get("code","").strip()
        if not code: continue
        prob_id = item.get("problem_id")
        tests = item.get("test_cases")
        if tests:
            tl, ml = 5000, 128
        elif prob_id:
            prob = get_problem(prob_id)
            if not prob: continue
            tests, tl, ml = prob["test_cases"], prob["time_limit_ms"], prob["memory_limit_mb"]
        else:
            continue
        sub_id = str(uuid.uuid4())
        db.execute("INSERT INTO submissions (id, code, problem_id) VALUES (?,?,?)", (sub_id, code, prob_id))
        _pool.submit(_run_grading_job, sub_id, code, tests, tl, ml)
        ids.append(sub_id)
    db.commit(); db.close()
    return jsonify({"submitted": len(ids), "submission_ids": ids}), 202


@api_bp.route("/submissions")
def get_submissions():
    limit = min(int(request.args.get("limit", 20)), 100)
    prob_id = request.args.get("problem_id")
    return jsonify(list_submissions(limit=limit, problem_id=prob_id))


@api_bp.route("/health")
def health():
    return jsonify({"status": "ok", "service": "AutoGrade"})
