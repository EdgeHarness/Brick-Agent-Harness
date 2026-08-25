"""Adversarial gates for the S5W local Agent Lab control plane."""
import http.client
import ctypes
from email.message import Message
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from webui import control
from webui import runner as lab_runner
from webui import server as lab
from harness import agent as agent_loop
from harness.runtime import ActionPolicy, RunHooks


CAPABILITY = "c" * 43


@pytest.fixture
def lab_server():
    instance = lab.Server(
        ("127.0.0.1", 0), lab.Handler, capability=CAPABILITY
    )
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance
    finally:
        if instance.runs.current and instance.runs.current.proc.poll() is None:
            instance.runs.current.stop()
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=5)


def request(instance, method, path, *, body=None, headers=None, host=None):
    payload = None if body is None else (
        body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    )
    connection = http.client.HTTPConnection(*instance.server_address, timeout=5)
    connection.putrequest(method, path, skip_host=True)
    connection.putheader("Host", host or instance.expected_host)
    for key, value in (headers or {}).items():
        connection.putheader(key, value)
    if payload is not None and "Content-Length" not in (headers or {}):
        connection.putheader("Content-Length", str(len(payload)))
    connection.endheaders(payload)
    response = connection.getresponse()
    raw = response.read()
    result = (response.status, dict(response.getheaders()), raw)
    connection.close()
    return result


def authorized(instance, *, origin=False, content_type=False):
    headers = {"Authorization": "Bearer " + CAPABILITY}
    if origin:
        headers.update({
            "Origin": instance.origin,
            "Sec-Fetch-Site": "same-origin",
        })
    if content_type:
        headers["Content-Type"] = "application/json; charset=utf-8"
    return headers


def test_startup_capability_has_256_bits_of_entropy_material():
    first = control.new_capability()
    second = control.new_capability()
    assert first != second
    assert len(first) >= 43
    assert len(second) >= 43


def test_api_rejects_missing_and_wrong_capabilities(lab_server):
    for header in (None, "Bearer wrong"):
        headers = {} if header is None else {"Authorization": header}
        status, response_headers, _ = request(
            lab_server, "GET", "/api/status", headers=headers
        )
        assert status == 401
        assert response_headers["WWW-Authenticate"] == 'Bearer realm="Agent Lab"'

    status, _, body = request(
        lab_server, "GET", "/api/status", headers=authorized(lab_server)
    )
    assert status == 200
    assert json.loads(body)["status"] == "idle"


def test_host_and_cross_origin_requests_are_refused(lab_server):
    status, _, _ = request(
        lab_server,
        "GET",
        "/api/status",
        headers=authorized(lab_server),
        host="attacker.example",
    )
    assert status == 421

    headers = authorized(lab_server, content_type=True)
    headers.update({"Origin": "https://attacker.example", "Sec-Fetch-Site": "cross-site"})
    status, _, _ = request(
        lab_server, "POST", "/api/stop", body={"run_id": "stale"}, headers=headers
    )
    assert status == 403


@pytest.mark.parametrize(
    ("headers", "body", "expected"),
    [
        ({}, {"run_id": "stale"}, 403),
        ({"Origin": "ORIGIN"}, {"run_id": "stale"}, 415),
        ({"Origin": "ORIGIN", "Content-Type": "text/plain"}, b"{}", 415),
    ],
)
def test_mutations_require_origin_and_json(lab_server, headers, body, expected):
    actual = authorized(lab_server)
    actual.update(headers)
    if actual.get("Origin") == "ORIGIN":
        actual["Origin"] = lab_server.origin
    status, _, _ = request(
        lab_server, "POST", "/api/stop", body=body, headers=actual
    )
    assert status == expected


def test_oversized_and_non_object_json_are_rejected_before_dispatch(lab_server):
    headers = authorized(lab_server, origin=True, content_type=True)
    message = Message()
    message["Content-Type"] = "application/json"
    message["Content-Length"] = str(control.MAX_BODY_BYTES + 1)
    fake = SimpleNamespace(
        headers=message, rfile=io.BytesIO(b""), close_connection=False
    )
    with pytest.raises(control.RequestError) as caught:
        control.read_json_object(fake)
    assert caught.value.status == 413
    assert fake.close_connection is True

    status, _, _ = request(
        lab_server, "POST", "/api/stop", body=b"[]", headers=headers
    )
    assert status == 400


def test_stop_is_bound_to_the_current_run(lab_server):
    stopped = []
    fake = SimpleNamespace(
        id="run-current", agent="1b", status="running",
        proc=SimpleNamespace(poll=lambda: None), stop=lambda: stopped.append(True),
    )
    lab_server.runs.current = fake
    headers = authorized(lab_server, origin=True, content_type=True)

    status, _, _ = request(
        lab_server, "POST", "/api/stop", body={"run_id": "run-old"}, headers=headers
    )
    assert status == 409
    assert stopped == []

    status, _, _ = request(
        lab_server, "POST", "/api/stop", body={"run_id": "run-current"}, headers=headers
    )
    assert status == 200
    assert stopped == [True]
    lab_server.runs.current = None


def test_reset_is_serialized_with_run_start():
    runs = lab.Runs()
    runs.current = SimpleNamespace(
        proc=SimpleNamespace(poll=lambda: None), agent="1b"
    )
    called = []
    with pytest.raises(RuntimeError, match="active"):
        runs.with_idle(lambda: called.append(True))
    assert called == []


def test_confirmation_is_run_id_nonce_and_replay_bound():
    ledger = control.ConfirmationLedger("run-a")
    ledger.register("confirmation-a", "n" * 43)
    with pytest.raises(control.RequestError, match="another run"):
        ledger.decide("run-b", "confirmation-a", "n" * 43, True)
    with pytest.raises(control.RequestError, match="does not match"):
        ledger.decide("run-a", "confirmation-a", "x" * 43, True)
    message = ledger.decide("run-a", "confirmation-a", "n" * 43, False)
    assert message["decision"] is False
    with pytest.raises(control.RequestError, match="stale"):
        ledger.decide("run-a", "confirmation-a", "n" * 43, True)


def test_runner_confirmation_channel_accepts_only_its_exact_run_and_nonce(monkeypatch):
    values = iter(("confirmation-a", "n" * 43))
    monkeypatch.setattr(control.secrets, "token_urlsafe", lambda _size: next(values))
    response = json.dumps({
        "run_id": "run-a", "confirmation_id": "confirmation-a",
        "nonce": "n" * 43, "decision": True,
    }) + "\n"
    emitted = []
    channel = control.ConfirmationChannel(
        io.StringIO(response),
        lambda event, **fields: emitted.append((event, fields)),
        "run-a",
        timeout=0.2,
    )
    assert channel.confirm("send", "synthetic effect") is True
    assert emitted[0][1]["run_id"] == "run-a"
    assert emitted[0][1]["nonce"] == "n" * 43


def test_external_effect_policy_denies_before_executor_and_records_attempt():
    calls = []
    observed = []

    class Tools:
        def execute(self, name, args, attempt):
            calls.append((name, args, attempt))
            return True, "executed"

    attempt = SimpleNamespace(
        policy=ActionPolicy(
            {"danger": "external_write"},
            confirmer=lambda _action, _detail: False,
        ),
        tools=Tools(),
        hooks=RunHooks(
            on_tool=lambda name, args, ok, result: observed.append(
                (name, args, ok, result)
            )
        ),
        actions=[],
    )
    attempt.record_action = lambda name, args, ok, result: attempt.actions.append(
        {"tool": name, "args": args, "ok": ok, "result": result}
    )
    ok, message = agent_loop._execute_with_policy(
        attempt, "danger", {"recipient": "reserved@example.test"}
    )
    assert ok is False
    assert "denied" in message
    assert calls == []
    assert attempt.actions[0]["tool"] == "danger"
    assert observed[0][2] is False


def test_event_replay_and_subscriber_memory_are_bounded():
    journal = control.EventJournal()
    for number in range(control.MAX_EVENTS + 25):
        journal.add({"t": "number", "value": number})
    snapshot = journal.snapshot()
    assert len(snapshot) == control.MAX_EVENTS
    assert snapshot[0][0] == 25
    assert snapshot[-1][1]["value"] == control.MAX_EVENTS + 24

    subscribers = []
    for _ in range(control.MAX_SUBSCRIBERS):
        subscribers.append(journal.subscribe(snapshot[-1][0])[0])
    with pytest.raises(control.RequestError) as caught:
        journal.subscribe(snapshot[-1][0])
    assert caught.value.status == 429
    for subscriber in subscribers:
        journal.unsubscribe(subscriber)


def test_redaction_is_recursive_and_does_not_mutate_input():
    source = {
        "Authorization": "Bearer abcdef",
        "nested": {
            "api_key": "value",
            "text": 'Bearer secret-token and {"password":"hidden"}',
            "output_tokens": 17,
        },
    }
    clean = control.redact(source)
    assert clean == {
        "Authorization": "[redacted]",
        "nested": {
            "api_key": "[redacted]",
            "text": 'Bearer [redacted] and {"password":"[redacted]"}',
            "output_tokens": 17,
        },
    }
    assert source["nested"]["api_key"] == "value"


def test_regular_path_refuses_traversal_and_links(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside.txt"
    root.mkdir()
    outside.write_text("secret", encoding="utf-8")
    (root / "ok.txt").write_text("ok", encoding="utf-8")
    assert Path(control.regular_path_under(root, "ok.txt")) == root / "ok.txt"
    for name in ("../outside.txt", r"..\outside.txt", "."):
        with pytest.raises(control.RequestError):
            control.regular_path_under(root, name)
    link = root / "link.txt"
    try:
        link.symlink_to(outside)
    except (NotImplementedError, OSError):
        return
    with pytest.raises(control.RequestError, match="linked"):
        control.regular_path_under(root, "link.txt")

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    linked_dir = root / "linked-dir"
    try:
        linked_dir.symlink_to(outside_dir, target_is_directory=True)
    except (NotImplementedError, OSError):
        return
    with pytest.raises(control.RequestError, match="linked"):
        control.trusted_directory_under(root, linked_dir)


def test_workspace_tree_refuses_linked_members_and_is_bounded(tmp_path):
    root = tmp_path / "root"
    workspace = root / "workspace"
    outside = tmp_path / "outside.txt"
    workspace.mkdir(parents=True)
    outside.write_text("private", encoding="utf-8")
    (workspace / "state.json").write_text("{}", encoding="utf-8")
    assert control.validate_regular_tree_under(root, workspace) == str(workspace)

    link = workspace / "linked.json"
    try:
        link.symlink_to(outside)
    except (NotImplementedError, OSError):
        pytest.skip("this host cannot create the symlink needed for the gate")
    with pytest.raises(control.RequestError, match="linked"):
        control.validate_regular_tree_under(root, workspace)
    link.unlink()

    with pytest.raises(control.RequestError, match="too many"):
        control.validate_regular_tree_under(root, workspace, maximum_members=0)


def test_trusted_root_itself_cannot_be_a_link(tmp_path):
    real = tmp_path / "real"
    linked = tmp_path / "linked"
    real.mkdir()
    try:
        linked.symlink_to(real, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("this host cannot create the symlink needed for the gate")
    with pytest.raises(control.RequestError, match="roots"):
        control.trusted_directory_under(linked, linked)


def test_server_cleanup_stops_live_run_on_unexpected_serve_failure():
    stopped = []
    closed = []
    failure = RuntimeError("serve failed")
    fake = SimpleNamespace(
        runs=SimpleNamespace(
            current=SimpleNamespace(
                proc=SimpleNamespace(poll=lambda: None),
                stop=lambda: stopped.append(True),
            )
        ),
        serve_forever=lambda: (_ for _ in ()).throw(failure),
        server_close=lambda: closed.append(True),
    )
    with pytest.raises(RuntimeError, match="serve failed"):
        lab.serve_until_stopped(fake)
    assert stopped == [True]
    assert closed == [True]


def test_server_cleanup_failure_is_not_silently_reported_as_success(capsys):
    closed = []
    fake = SimpleNamespace(
        runs=SimpleNamespace(
            current=SimpleNamespace(
                proc=SimpleNamespace(poll=lambda: None),
                stop=lambda: (_ for _ in ()).throw(RuntimeError("Bearer secret")),
            )
        ),
        serve_forever=lambda: None,
        server_close=lambda: closed.append(True),
    )
    with pytest.raises(RuntimeError, match="cleanup did not complete"):
        lab.serve_until_stopped(fake)
    assert closed == [True]
    assert "secret" not in capsys.readouterr().err


def test_runner_stderr_is_not_relayed_to_browser(capsys):
    class FakeProcess:
        stderr = io.StringIO("Authorization: Bearer very-secret\nprivate traceback\n")
        stdout = io.StringIO("")

        @staticmethod
        def wait():
            return 7

    events = []
    run = SimpleNamespace(
        id="run-a",
        proc=FakeProcess(),
        process_tree=SimpleNamespace(close=lambda: None),
        confirmations=SimpleNamespace(clear=lambda: None),
        status="running",
        # A run outside any conversation, which is what a CLI-shaped run is.
        # _pump reads options to decide whether to record a chat turn.
        options={},
        add=lambda event: events.append(event),
    )
    lab.Runs()._pump(run)
    assert events == [
        {"t": "error", "message": "the run exited with code 7"},
        {"t": "closed", "status": "failed", "code": 7},
    ]
    local = capsys.readouterr().err
    assert "private traceback" in local
    assert "very-secret" not in local


def test_runner_exception_event_is_generic_and_local_trace_is_redacted(
    monkeypatch, capsys
):
    events = []
    monkeypatch.setattr(
        lab_runner,
        "emit",
        lambda event, **fields: events.append({"t": event, **fields}),
    )
    try:
        raise RuntimeError("Bearer browser-must-not-see")
    except RuntimeError:
        lab_runner.emit_run_failure()
    assert events == [{"t": "error", "message": "the agent run failed"}]
    local = capsys.readouterr().err
    assert "RuntimeError" in local
    assert "browser-must-not-see" not in local


def _pid_exists(pid):
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == 0x00000102
        finally:
            kernel32.CloseHandle(handle)
    proc_stat = Path(f"/proc/{pid}/stat")
    if proc_stat.exists():
        try:
            if proc_stat.read_text(encoding="ascii").split()[2] == "Z":
                return False
        except (OSError, IndexError):
            pass
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def test_process_tree_stop_leaves_no_child_process(tmp_path):
    pid_file = tmp_path / "pids.json"
    child_code = "import time; time.sleep(60)"
    parent_code = (
        "import json,os,subprocess,sys,time; "
        f"p=subprocess.Popen([sys.executable,'-c',{child_code!r}]); "
        "open(sys.argv[1],'w').write(json.dumps([os.getpid(),p.pid])); "
        "time.sleep(60)"
    )
    tree = control.ProcessTree.start(
        [sys.executable, "-c", parent_code, str(pid_file)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 10
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert pid_file.exists()
    parent_pid, child_pid = json.loads(pid_file.read_text(encoding="utf-8"))
    assert _pid_exists(parent_pid) and _pid_exists(child_pid)
    tree.terminate(grace_seconds=0.2)
    deadline = time.monotonic() + 5
    while (_pid_exists(parent_pid) or _pid_exists(child_pid)) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _pid_exists(parent_pid)
    assert not _pid_exists(child_pid)


def test_security_headers_are_on_static_and_api_responses(lab_server):
    status, headers, _ = request(lab_server, "GET", "/")
    assert status == 200
    assert headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["Referrer-Policy"] == "no-referrer"


def _pumped_run(events_out, *, thread, journal, code=0, status="running"):
    """A Run shaped the way _pump reads one, without a subprocess."""
    class FakeProcess:
        stderr = io.StringIO("")
        stdout = io.StringIO("")

        @staticmethod
        def wait():
            return code

    return SimpleNamespace(
        id="run-t",
        agent="1b",
        proc=FakeProcess(),
        process_tree=SimpleNamespace(close=lambda: None),
        confirmations=SimpleNamespace(clear=lambda: None),
        status=status,
        options={"thread": thread},
        events=SimpleNamespace(snapshot=lambda: list(enumerate(journal))),
        add=lambda event: events_out.append(event),
    )


def test_a_conversation_records_the_agents_summary_as_its_reply(tmp_path, monkeypatch):
    from harness import chat

    monkeypatch.setattr(lab, "agent_dir", lambda agent: str(tmp_path))
    tid = chat.create(str(tmp_path), "do the thing")
    journal = [{"t": "end", "summary": "Drafted the reply."}]
    lab.Runs()._pump(_pumped_run([], thread=tid, journal=journal))
    said = [m["text"] for m in chat.messages(str(tmp_path), tid)
            if m["role"] == "assistant"]
    assert said == ["Drafted the reply."]


def test_a_run_that_never_summarized_reports_what_it_did(tmp_path, monkeypatch):
    """A small model often never calls done(). Saying only "no summary" makes a
    conversation where real work happened read as a row of shrugs, so the reply
    names the steps that actually completed."""
    from harness import chat

    monkeypatch.setattr(lab, "agent_dir", lambda agent: str(tmp_path))
    tid = chat.create(str(tmp_path), "do the thing")
    journal = [{"t": "end", "summary": "", "actions": [
        {"tool": "mail_list_mail", "ok": True},
        {"tool": "mail_list_mail", "ok": True},
        {"tool": "mail_draft_mail", "ok": True},
        {"tool": "mail_draft_mail", "ok": False},
    ]}]
    lab.Runs()._pump(_pumped_run([], thread=tid, journal=journal, code=7))
    said = [m["text"] for m in chat.messages(str(tmp_path), tid)
            if m["role"] == "assistant"]
    assert said == ["(no summary) Steps completed: mail_list_mail x2, "
                    "mail_draft_mail."]


def test_a_run_that_did_nothing_says_so(tmp_path, monkeypatch):
    from harness import chat

    monkeypatch.setattr(lab, "agent_dir", lambda agent: str(tmp_path))
    tid = chat.create(str(tmp_path), "do the thing")
    lab.Runs()._pump(_pumped_run([], thread=tid, journal=[], code=7))
    said = [m["text"] for m in chat.messages(str(tmp_path), tid)
            if m["role"] == "assistant"]
    assert said == ["(no summary, and no step completed)"]


def test_a_failed_call_is_not_reported_as_a_completed_step():
    assert lab.thread_reply(
        {"actions": [{"tool": "mail_send_mail", "ok": False}]}, "failed"
    ) == "(no summary, and no step completed)"


def test_a_run_outside_a_conversation_writes_no_turn(tmp_path, monkeypatch):
    from harness import chat

    monkeypatch.setattr(lab, "agent_dir", lambda agent: str(tmp_path))
    tid = chat.create(str(tmp_path), "do the thing")
    lab.Runs()._pump(_pumped_run([], thread=None, journal=[]))
    assert chat.messages(str(tmp_path), tid) == []


def test_the_interactive_budget_is_fifty_and_the_benchmark_is_not():
    """The two are deliberately different numbers. An interactive run wants
    headroom; the benchmark ceiling is part of a recorded experiment and moving
    it would make new runs incomparable to the ones already on disk."""
    from agents._shared import run_agent
    from bench import run_bench

    assert run_agent.DEFAULT_MAX_CALLS == 50
    assert lab_runner.DEFAULT_MAX_CALLS == 50
    assert run_bench.DEFAULT_MAX_CALLS == 14


def test_the_call_field_cannot_offer_more_than_the_server_accepts():
    """The number input is a hint to a browser; the API is the trust boundary.
    Offering 200 in a field the server rejects above 80 is a guaranteed 400."""
    root = Path(__file__).resolve().parents[1]
    html = (root / "webui/static/index.html").read_text(encoding="utf-8")
    source = (root / "webui/static/app.js").read_text(encoding="utf-8")
    assert 'id="opt-calls" min="2" max="80"' in html
    assert "Math.min(80, Math.max(2, n))" in source
    assert 'max_calls", minimum=2, maximum=80' in (
        root / "webui/server.py").read_text(encoding="utf-8")


# ------------------------------------------------ connector inspection ----
#
# The console can start one connector, read back what it would expose, and
# stop it, without spending a model call. These cover the trust boundary and
# the failure shapes; the happy path against a real server is exercised by
# tests/test_mcp_bridge.py and by running the selftest connector.

def test_connector_inspection_requires_the_capability(lab_server):
    status, _, _ = request(
        lab_server, "POST", "/api/mcp/inspect",
        body={"name": "selftest"},
        headers={"Content-Type": "application/json"},
    )
    assert status == 401


def test_connector_inspection_rejects_an_unknown_field(lab_server):
    status, _, _ = request(
        lab_server, "POST", "/api/mcp/inspect",
        body={"name": "selftest", "command": "rm -rf /"},
        headers=authorized(lab_server, origin=True, content_type=True),
    )
    assert status == 400


def test_connector_inspection_rejects_an_unknown_mode(lab_server):
    status, _, _ = request(
        lab_server, "POST", "/api/mcp/inspect",
        body={"name": "selftest", "mode": "yolo"},
        headers=authorized(lab_server, origin=True, content_type=True),
    )
    assert status == 400


def test_connector_inspection_reports_an_unknown_server_without_raising(lab_server):
    # A name that is not in the registry is the operator's typo, and the
    # message names the known servers, so it belongs in the response body
    # rather than in a 500.
    status, _, body = request(
        lab_server, "POST", "/api/mcp/inspect",
        body={"name": "not-a-real-connector"},
        headers=authorized(lab_server, origin=True, content_type=True),
    )
    assert status == 200
    payload = json.loads(body)
    assert payload["tools"] == []
    assert "unknown MCP server" in payload["error"]


def test_connector_inspection_lists_tools_with_their_effect_and_reason(lab_server):
    # selftest is a stdlib MCP server in this repo: no credentials, no network.
    status, _, body = request(
        lab_server, "POST", "/api/mcp/inspect",
        body={"name": "selftest", "mode": "draft"},
        headers=authorized(lab_server, origin=True, content_type=True),
    )
    assert status == 200
    payload = json.loads(body)
    by_name = {t["name"]: t for t in payload["tools"]}
    assert by_name["mail_list_mail"]["effect"] == "read"
    assert by_name["mail_list_mail"]["why"] == "policy"
    # The self-test opts into exact reviewed policies for every exposed tool.
    assert by_name["mail_modify_mail"]["effect"] == "external_write"
    assert by_name["mail_modify_mail"]["why"] == "policy"
    # draft mode never exposes a tool that transmits to a person
    assert not [n for n in by_name if "send" in n]


def test_business_connector_inspection_requires_the_capability(lab_server):
    status, _, _ = request(
        lab_server,
        "POST",
        "/api/connectors/inspect",
        body={"name": "hubspot", "mode": "read_only"},
        headers={"Content-Type": "application/json"},
    )
    assert status == 401


def test_business_connector_inspection_rejects_unknown_fields_and_modes(lab_server):
    headers = authorized(lab_server, origin=True, content_type=True)
    status, _, _ = request(
        lab_server,
        "POST",
        "/api/connectors/inspect",
        body={"name": "hubspot", "command": "arbitrary"},
        headers=headers,
    )
    assert status == 400
    status, _, _ = request(
        lab_server,
        "POST",
        "/api/connectors/inspect",
        body={"name": "hubspot", "mode": "unsafe"},
        headers=headers,
    )
    assert status == 400


def test_business_connector_inspection_lists_exact_reviewed_reads(
    lab_server, monkeypatch,
):
    tools = (
        "hs_find_contact",
        "hs_get_contact",
        "hs_recent_activity",
        "hs_my_open_followups",
    )
    monkeypatch.setattr(
        lab.connector_config,
        "available",
        lambda: [("hubspot", "HubSpot", "ready")],
    )
    monkeypatch.setattr(
        lab.connector_runtime,
        "enable",
        lambda names, mode: (
            {name: {} for name in tools},
            {name: "read" for name in tools},
            [{
                "id": "hubspot",
                "account": "sandbox",
                "mode": mode,
                "tools": list(tools),
                "writes": [],
                "effects": {
                    name: {
                        "effect": "read",
                        "transmits": False,
                        "invites": False,
                        "classified_by": "reviewed declaration",
                    }
                    for name in tools
                },
            }],
        ),
    )
    closed = []
    monkeypatch.setattr(lab.connector_runtime, "shutdown", lambda: closed.append(True))
    status, _, body = request(
        lab_server,
        "POST",
        "/api/connectors/inspect",
        body={"name": "hubspot", "mode": "read_only"},
        headers=authorized(lab_server, origin=True, content_type=True),
    )
    assert status == 200
    payload = json.loads(body)
    assert payload["account"] == "sandbox"
    assert payload["mode"] == "read_only"
    assert payload["writes"] == []
    assert [item["name"] for item in payload["tools"]] == list(tools)
    assert all(item["effect"] == "read" for item in payload["tools"])
    assert all(item["why"] == "reviewed declaration" for item in payload["tools"])
    assert closed == [True]
