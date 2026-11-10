import ast
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from . import config
from .models import Deliverable, EvaluationResult, TaskContract

FORBIDDEN_IMPORTS = {
    "os", "sys", "subprocess", "socket", "shutil", "ctypes", "importlib",
    "multiprocessing", "threading", "signal", "http", "urllib", "requests",
    "webbrowser", "pickle",
}
DYNAMIC_EXEC_CALLS = {"eval", "exec", "compile", "__import__"}
SVG_UNSAFE_TAGS = {"script", "foreignObject", "iframe", "image"}

RUNNER_SOURCE = r'''
import contextlib, io, json, sys

spec_path, out_path = sys.argv[1], sys.argv[2]
results = {"passed": 0, "total": 0, "logs": [], "error": None}
try:
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    code, tests = spec["code"], spec["tests"]
    ns = {}
    try:
        exec(compile(code, "deliverable.py", "exec"), ns)
    except Exception as exc:
        results["error"] = "deliverable import failed: %s: %s" % (type(exc).__name__, exc)
        results["logs"].append("[IMPORT-ERROR] " + results["error"])
    if results["error"] is None:
        tns = dict(ns)
        try:
            exec(compile(tests, "contract_tests.py", "exec"), tns)
        except Exception as exc:
            results["error"] = "test module failed to load: %s: %s" % (type(exc).__name__, exc)
            results["logs"].append("[TESTLOAD-ERROR] " + results["error"])
        else:
            fns = [(n, f) for n, f in sorted(tns.items()) if n.startswith("test_") and callable(f)]
            results["total"] = len(fns)
            for name, fn in fns:
                buf = io.StringIO()
                try:
                    with contextlib.redirect_stdout(buf):
                        fn()
                    results["passed"] += 1
                    extra = buf.getvalue().strip()
                    results["logs"].append("[PASS] %s%s" % (name, (" :: " + extra) if extra else ""))
                except Exception as exc:
                    results["logs"].append("[FAIL] %s :: %s: %s" % (name, type(exc).__name__, exc))
except Exception as exc:
    results["error"] = "runner failure: %s: %s" % (type(exc).__name__, exc)
finally:
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh)
'''


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_windows_job():
    """Windows Job Object: memory cap, active-process cap, kill-on-close.

    Everything the sandbox spawns dies with the job handle, even on timeout,
    and a runaway process cannot exceed the configured memory budget.
    """
    if os.name != "nt":
        return None, None
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class BASIC_LIMITS(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class EXTENDED_LIMITS(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BASIC_LIMITS),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
    JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000200
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JobObjectExtendedLimitInformation = 9

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None, None
    limits = EXTENDED_LIMITS()
    limits.BasicLimitInformation.LimitFlags = (
        JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_ACTIVE_PROCESS | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    )
    limits.ProcessMemoryLimit = config.SANDBOX_MEMORY_MB * 1024 * 1024
    limits.BasicLimitInformation.ActiveProcessLimit = 8
    if not kernel32.SetInformationJobObject(
        job, JobObjectExtendedLimitInformation, ctypes.byref(limits), ctypes.sizeof(limits)
    ):
        kernel32.CloseHandle(job)
        return None, None
    return job, kernel32


def run_code_sandbox(code_str: str, test_code_str: str, timeout_seconds: float | None = None) -> dict:
    """Execute worker code against contract tests in a hardened subprocess.

    Layers: isolated interpreter (-I), utf8 mode, no window, below-normal
    priority, memory cap + process cap + kill-on-close via Job Object, wall
    clock timeout, disposable temp dir, results-file handshake.
    """
    timeout_s = float(timeout_seconds or config.SANDBOX_TIMEOUT_SECONDS)
    declared = len(re.findall(r"def\s+test_\w+", test_code_str or ""))
    result: dict = {
        "passed": 0, "total": max(declared, 0), "pass_rate": 0.0,
        "logs": [], "error": None, "duration_ms": 0,
    }
    tmp_dir = None
    job, kernel32 = _make_windows_job()
    started = time.perf_counter()
    proc = None
    try:
        tmp_dir = tempfile.mkdtemp(prefix="synapse_sandbox_")
        spec_path = os.path.join(tmp_dir, "spec.json")
        out_path = os.path.join(tmp_dir, "results.json")
        runner_path = os.path.join(tmp_dir, "runner.py")
        with open(spec_path, "w", encoding="utf-8") as fh:
            json.dump({"code": code_str, "tests": test_code_str}, fh)
        with open(runner_path, "w", encoding="utf-8") as fh:
            fh.write(RUNNER_SOURCE)

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW | 0x00004000  # BELOW_NORMAL_PRIORITY_CLASS
        proc = subprocess.Popen(
            [sys.executable, "-I", "-B", "-X", "utf8", runner_path, spec_path, out_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", cwd=tmp_dir, creationflags=creationflags,
        )
        if job is not None and kernel32 is not None:
            kernel32.AssignProcessToJobObject(job, int(proc._handle))

        timed_out = False
        try:
            _stdout, stderr = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
            try:
                proc.communicate(timeout=2)
            except Exception:
                pass

        if timed_out:
            result["error"] = f"sandbox timeout after {timeout_s}s"
            result["logs"].append(f"[TIMEOUT] execution exceeded {timeout_s}s - process tree killed")
        elif os.path.exists(out_path):
            with open(out_path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            for key in ("passed", "total", "logs", "error"):
                if key in loaded:
                    result[key] = loaded[key]
        else:
            result["error"] = f"sandbox exited rc={proc.returncode} without results"
            if stderr:
                result["logs"].append(stderr.strip()[-800:])
    except Exception as exc:
        result["error"] = f"sandbox failure: {type(exc).__name__}: {exc}"
        result["logs"].append(result["error"])
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
        if job is not None and kernel32 is not None:
            kernel32.CloseHandle(job)
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    result["duration_ms"] = int((time.perf_counter() - started) * 1000)
    if result["total"] > 0:
        result["pass_rate"] = round(result["passed"] / result["total"], 4)
    else:
        result["total"] = declared
        result["pass_rate"] = 0.0
    return result


def analyze_code_ast(code_str: str, schema: dict) -> tuple[float, list[str]]:
    """Static schema + import policy + dynamic-execution ban via Python AST."""
    details: list[str] = []
    try:
        tree = ast.parse(code_str or "")
    except SyntaxError as exc:
        return 0.0, [f"[SCHEMA] FAIL syntax error: {exc}"]
    defined = {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    required = schema.get("required_functions", [])
    if required:
        present = [fn for fn in required if fn in defined]
        score = len(present) / len(required)
        for fn in required:
            state = "PASS present" if fn in defined else "FAIL MISSING"
            details.append(f"[SCHEMA] {state} required function: {fn}()")
    else:
        score = 1.0
        details.append("[SCHEMA] PASS no required functions declared")

    imports: set[str] = set()
    dynamic: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in DYNAMIC_EXEC_CALLS:
            dynamic.append(node.func.id)

    banned = sorted(imports & FORBIDDEN_IMPORTS)
    if banned:
        details.append(f"[SCHEMA] FAIL forbidden imports detected: {', '.join(banned)} - contract violation")
        score = 0.0
    else:
        details.append("[SCHEMA] PASS import policy clean")

    if dynamic:
        details.append(f"[SCHEMA] FAIL dynamic execution forbidden: {', '.join(sorted(set(dynamic)))}()")
        score = 0.0
    return round(score, 4), details


def check_json_payload(payload: dict, schema: dict) -> tuple[float, float, list[str]]:
    logs: list[str] = []
    required = schema.get("required_fields", [])
    field_types = schema.get("field_types", {})
    payload = payload if isinstance(payload, dict) else {}

    if required:
        hits = sum(1 for f in required if payload.get(f) is not None)
        test_score = round(hits / len(required), 4)
        for f in required:
            ok = payload.get(f) is not None
            logs.append(f"[{'PASS' if ok else 'FAIL'}] json::required_field::{f}")
    else:
        test_score = 1.0
        logs.append("[PASS] json::no_required_fields_declared")

    checkers = {
        "str": lambda v: isinstance(v, str),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "array": lambda v: isinstance(v, list),
        "object": lambda v: isinstance(v, dict),
    }
    if field_types:
        hits = 0
        for field, expected in field_types.items():
            value = payload.get(field)
            ok = value is not None and checkers.get(expected, lambda v: True)(value)
            hits += ok
            logs.append(f"[{'PASS' if ok else 'FAIL'}] json::type::{field}:{expected}")
        schema_score = round(hits / len(field_types), 4)
    else:
        schema_score = 1.0
        logs.append("[PASS] json::no_type_constraints_declared")
    return test_score, schema_score, logs


def evaluate_svg_constraints(svg_str: str, schema: dict) -> tuple[float, int, list[str], float]:
    logs: list[str] = []
    counters = {"passed": 0, "total": 0}

    def check(name: str, ok: bool, note: str = "") -> None:
        counters["total"] += 1
        counters["passed"] += ok
        logs.append(f"[{'PASS' if ok else 'FAIL'}] svg::{name}" + (f" :: {note}" if note else ""))

    root = None
    parse_error = None
    try:
        root = ET.fromstring((svg_str or "").strip())
    except ET.ParseError as exc:
        parse_error = exc
    check("well_formed_xml", parse_error is None, str(parse_error) if parse_error else "parses cleanly")
    if root is None:
        return 0.0, 1, logs, 0.0
    check("root_is_svg", root.tag.rsplit("}", 1)[-1] == "svg")
    check("has_viewbox", root.get("viewBox") is not None, root.get("viewBox") or "missing")
    element_count = max(len(list(root.iter())) - 1, 0)
    min_elements = int(schema.get("min_elements", 3))
    check("min_elements", element_count >= min_elements, f"{element_count} elements (minimum {min_elements})")
    shapes = {el.tag.rsplit("}", 1)[-1] for el in root.iter()}
    for shape in schema.get("required_shapes", []):
        check(f"required_shape_{shape}", shape in shapes)
    unsafe = [el.tag.rsplit("}", 1)[-1] for el in root.iter() if el.tag.rsplit("}", 1)[-1] in SVG_UNSAFE_TAGS]
    check("no_dynamic_content", not unsafe, f"unsafe nodes: {', '.join(unsafe)}" if unsafe else "no script/foreignObject/image")

    palette = {c.lower() for c in schema.get("palette", [])}
    colors = {c.lower() for c in re.findall(r"#[0-9a-fA-F]{3,8}", svg_str or "")}
    if palette:
        violations = sorted(colors - palette)
        check("brand_palette_compliance", not violations,
              f"off-palette: {', '.join(violations)}" if violations else f"{len(colors)} colors all inside brand palette")
        schema_score = 1.0 if not violations else round(max(0.0, 1.0 - len(violations) / max(len(colors), 1)), 4)
    else:
        check("brand_palette_compliance", True, "no palette declared")
        schema_score = 1.0
    test_score = round(counters["passed"] / counters["total"], 4) if counters["total"] else 0.0
    return test_score, counters["total"], logs, schema_score


def heuristic_rubric(contract: TaskContract, deliverable: Deliverable) -> tuple[float, str, str]:
    reasons: list[str] = []
    score = 0.5
    schema = contract.deliverable_schema or {}

    if deliverable.artifact_type == "code":
        src = deliverable.code or ""
        if re.search(r'"""[\s\S]+?"""', src) or re.search(r"'''[\s\S]+?'''", src):
            score += 0.15
            reasons.append("documented with docstrings (+0.15)")
        if re.search(r"\b(raise|try|except)\b", src):
            score += 0.15
            reasons.append("explicit error handling (+0.15)")
        if re.search(r"def\s+\w+\s*\([^)]*:\s*\w", src):
            score += 0.10
            reasons.append("type-annotated signatures (+0.10)")
        if 200 <= len(src) <= 8000:
            score += 0.05
            reasons.append("reasonable implementation size (+0.05)")
        reasons.append("heuristic rubric capped at 0.95 - set GEMINI_API_KEY for full LLM evaluation")
    elif deliverable.artifact_type == "json":
        payload = deliverable.payload or {}
        required = schema.get("required_fields", [])
        score = 0.6
        reasons.append("structural baseline (+0.60)")
        if required and all(payload.get(f) is not None for f in required):
            score += 0.15
            reasons.append("all required fields populated (+0.15)")
        if len(payload) >= max(len(required), 1) + 1:
            score += 0.20
            reasons.append("payload richer than bare minimum (+0.20)")
    else:
        svg = deliverable.code or ""
        palette = {c.lower() for c in schema.get("palette", [])}
        score = 0.5
        reasons.append("geometric baseline (+0.50)")
        colors = {c.lower() for c in re.findall(r"#[0-9a-fA-F]{3,8}", svg)}
        in_palette = len(colors & palette) if palette else len(colors)
        if in_palette >= 2:
            score += 0.15
            reasons.append(f"uses {in_palette} brand-palette colors (+0.15)")
        if re.search(r"<title>|<desc>", svg, re.IGNORECASE):
            score += 0.15
            reasons.append("accessible title/desc metadata (+0.15)")
        if re.search(r"\b(width|height)\s*=", svg):
            score += 0.10
            reasons.append("explicit render dimensions (+0.10)")
        vb = re.search(r'viewBox\s*=\s*"([^"]+)"', svg)
        if vb and len(vb.group(1).split()) == 4:
            score += 0.05
            reasons.append("valid 4-component viewBox (+0.05)")

    score = max(0.30, min(0.95, round(score, 4)))
    return score, " | ".join(reasons), "heuristic_fallback"


def gemini_rubric(contract: TaskContract, deliverable: Deliverable) -> tuple[float, str, str] | None:
    """LLM rubric via Google Gemini. Returns None on any failure.

    Safety invariant: Gemini contributes at most W_LLM of the composite and
    can never trigger a settlement by itself - the threshold rule over the
    full composite (deterministic channels included) is the only authority.
    """
    if not config.GEMINI_API_KEY:
        return None

    def _call() -> str:
        from google import genai

        client = genai.Client(api_key=config.GEMINI_API_KEY)
        contract_view = {
            "title": contract.title,
            "description": contract.description,
            "acceptance_criteria": contract.acceptance_criteria,
            "deliverable_schema": contract.deliverable_schema,
        }
        if deliverable.artifact_type == "json":
            artifact = json.dumps(deliverable.payload or {}, indent=2)
        else:
            artifact = deliverable.code or ""
        prompt = (
            "You are the Neural Arbiter for SynapsePay, an autonomous escrow protocol. "
            "Score the worker agent's deliverable against the contract criteria.\n\n"
            f"CONTRACT:\n{json.dumps(contract_view, indent=2)}\n\n"
            f"DELIVERABLE ({deliverable.artifact_type}):\n{artifact[:6000]}\n\n"
            "Rubric: adherence to acceptance criteria, edge-case resilience, code/asset quality.\n"
            'Respond with ONLY a JSON object: {"score": <0.0-1.0>, "rationale": "<=60 words"}'
        )
        response = client.models.generate_content(model=config.GEMINI_MODEL, contents=prompt)
        return response.text or ""

    return _gemini_with_timeout(_call)


def _gemini_with_timeout(call) -> tuple[float, str, str] | None:
    import concurrent.futures

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(call)
            text = future.result(timeout=25)
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        data = json.loads(match.group(0))
        score = max(0.0, min(1.0, float(data.get("score", 0.0))))
        rationale = str(data.get("rationale", ""))[:500]
        return round(score, 4), rationale, f"gemini:{config.GEMINI_MODEL}"
    except Exception:
        return None


def payout_fraction_for_score(score: float) -> float:
    """Partial-payout schedule: fraction of the bounty captured when
    PARTIAL_THRESHOLD <= S < ARBITER_THRESHOLD. Documented, deterministic,
    clamped to [0.25, 0.80]."""
    tau = config.ARBITER_THRESHOLD
    tau_p = config.PARTIAL_THRESHOLD
    if score >= tau:
        return 1.0
    if score < tau_p:
        return 0.0
    raw = 0.25 + 0.55 * (score - tau_p) / max(tau - tau_p, 1e-9)
    return round(min(0.80, max(0.25, raw)), 4)


async def evaluate_deliverable(contract: TaskContract, deliverable: Deliverable) -> EvaluationResult:
    """Neural Arbiter core: sandbox -> schema/policy -> LLM rubric -> composite.

    Decisions: CAPTURE (S >= 0.85), PARTIAL (0.80 <= S < 0.85, fractional
    capture), VOID (S < 0.80). Gemini can never settle alone: its maximum
    contribution is W_LLM (0.25), far below the threshold.
    """
    started = time.perf_counter()
    schema = contract.deliverable_schema or {}
    weights = contract.arbiter_weights or {
        "tests": config.W_TESTS, "schema": config.W_SCHEMA, "llm": config.W_LLM,
    }

    sandbox = {"passed": 0, "total": 0, "pass_rate": 0.0, "logs": [], "error": None, "duration_ms": 0}
    test_logs: list[str] = []
    schema_details: list[str] = []

    if deliverable.artifact_type == "code":
        sandbox = await asyncio.to_thread(
            run_code_sandbox, deliverable.code, contract.test_code, contract.timeout_seconds
        )
        test_logs = list(sandbox["logs"])
        a_tests = sandbox["pass_rate"]
        a_schema, schema_details = analyze_code_ast(deliverable.code, schema)
    elif deliverable.artifact_type == "json":
        a_tests, a_schema, logs = check_json_payload(deliverable.payload or {}, schema)
        test_logs = logs
        sandbox = {
            "passed": round(a_tests * max(len(schema.get("required_fields", [])), 1)),
            "total": max(len(schema.get("required_fields", [])), 1),
            "pass_rate": a_tests, "logs": logs, "error": None, "duration_ms": 0,
        }
    else:
        a_tests, total, test_logs, a_schema = evaluate_svg_constraints(deliverable.code, schema)
        sandbox = {
            "passed": round(a_tests * total), "total": total, "pass_rate": a_tests,
            "logs": test_logs, "error": None, "duration_ms": 0,
        }
        schema_details = [line for line in test_logs if "palette" in line or "SCHEMA" in line]

    rubric = gemini_rubric(contract, deliverable)
    if rubric is not None:
        a_llm, rationale, provider = rubric
    else:
        a_llm, rationale, provider = heuristic_rubric(contract, deliverable)

    composite = round(
        weights.get("tests", 0.0) * a_tests
        + weights.get("schema", 0.0) * a_schema
        + weights.get("llm", 0.0) * a_llm,
        4,
    )
    threshold = float(config.ARBITER_THRESHOLD)
    if composite >= threshold:
        decision = "CAPTURE"
        payout_fraction = 1.0
    elif composite >= config.PARTIAL_THRESHOLD:
        decision = "PARTIAL"
        payout_fraction = payout_fraction_for_score(composite)
    else:
        decision = "VOID"
        payout_fraction = 0.0

    failed_cases = [line for line in test_logs if line.startswith("[FAIL]")]
    failed_cases += [line for line in schema_details if "FAIL" in line]
    remediation_plan = []
    for line in failed_cases[:8]:
        remediation_plan.append(f"Failed check: {line.split('] ', 1)[-1]}")
    if remediation_plan:
        remediation_plan.append("Fix the failing cases and resubmit - the deliverable is re-scored from scratch on the next arbitration.")

    return EvaluationResult(
        contract_id=contract.id,
        scores={"tests": a_tests, "schema": a_schema, "llm": a_llm},
        weights=weights,
        composite=composite,
        threshold=threshold,
        decision=decision,
        payout_fraction=payout_fraction,
        remediation_plan=remediation_plan,
        test_logs=test_logs,
        schema_details=schema_details,
        llm_provider=provider,
        llm_rationale=rationale,
        sandbox=sandbox,
        arbiter_latency_ms=int((time.perf_counter() - started) * 1000),
        evaluated_at=_now(),
    )
