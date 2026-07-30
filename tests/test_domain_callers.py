import json
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

import pytest

from agents._shared import run_agent as shared_runner
from bench import report, run_bench
from finetune import gen_toolcall_data
from harness.agent import build_harness_system
from harness.domain import load_domain
from harness.storage import agent_runtime_paths
from webui import runner as web_runner
from webui import server as web_server


PROJECT = Path(__file__).resolve().parents[1]


class CounterBenchLLM:
    def __init__(self, model):
        self.model = model
        self.calls = 0
        self.prompt_tokens = 0
        self.output_tokens = 0
        self.wall = 0.0
        self.replies = [
            '{"tool":"increment_counter","args":{"amount":1}}',
            '{"tool":"increment_counter","args":{"amount":1}}',
            '{"tool":"done","args":{"summary":"two"}}',
        ]

    def chat(self, messages, **kwargs):
        self.calls += 1
        return self.replies.pop(0)


def result_row(
    domain,
    version,
    condition,
    *,
    task="task",
    capability="custom_cap",
    tools=None,
):
    return {
        "domain": domain,
        "domain_version": version,
        "model": "model",
        "condition": condition,
        "task": task,
        "caps": [capability],
        "tools": tools or ["done"],
        "score": 1.0,
        "checks": [["expected outcome", True]],
        "finished": True,
        "parse_failures": 0,
        "invalid_calls": 0,
        "tool_errors": 0,
        "llm_calls": 1,
        "prompt_tokens": 1,
        "wall_seconds": 0.1,
        "output_tokens": 1,
        "error": None,
        "max_calls": 4,
    }


def test_all_agent_configs_select_a_domain_and_shims_are_centralized():
    agent_dirs = [
        path.parent
        for path in PROJECT.glob("agents/*/config.json")
        if not path.parent.name.startswith("_")
    ]
    assert agent_dirs
    for folder in agent_dirs:
        config = json.loads(
            (folder / "config.json").read_text(encoding="utf-8-sig")
        )
        domain = load_domain(config["domain"])
        assert domain.version
        shim = (folder / "run_agent.py").read_text(encoding="utf-8")
        assert "agents._shared.run_agent import main" in shim
        launcher = folder / "run.ps1"
        assert launcher.is_file()
        assert "run_agent.py" in launcher.read_text(encoding="utf-8")
    assert not (PROJECT / "agents/_shared/run.ps1").exists()


def test_counter_pack_import_does_not_load_office_compatibility_modules():
    probe = """
import sys
from domains.counter_demo import PACK
assert PACK.name == "counter_demo"
for name in ("domains.office_demo", "harness.world", "harness.office"):
    assert name not in sys.modules, (name, sorted(sys.modules))
"""
    subprocess.run(
        [sys.executable, "-c", probe],
        cwd=PROJECT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_agent_flag_precedence_and_domain_selection():
    options, task = shared_runner.parse_flags(
        [
            "--domain",
            "counter_demo",
            "--max-calls",
            "2",
            "increment",
        ]
    )
    assert options["domain_name"] == "counter_demo"
    assert options["max_calls"] == 2
    assert task == "increment"

    options, task = shared_runner.parse_flags(
        ["increment", "--domain", "counter_demo", "twice"]
    )
    assert options["domain_name"] == "counter_demo"
    assert task == "increment twice"


def test_agent_cli_rejects_bad_flags_and_help_never_starts_a_model():
    for argv in (
        ["--unknown"],
        ["--max-c", "2"],
        ["--domain"],
        ["--root"],
        ["--root", "/tmp", "task"],
        ["--shell", "task"],
        ["--yolo", "task"],
        ["--with-domain", "task"],
        ["--with-office", "task"],
        ["--max-calls", "0"],
        ["--max-calls", "not-an-int"],
    ):
        with pytest.raises(SystemExit):
            shared_runner.parse_flags(argv)

    completed = subprocess.run(
        [sys.executable, "agents/1b/run_agent.py", "--help"],
        cwd=PROJECT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0
    assert "--domain" in completed.stdout
    for removed in shared_runner.REMOVED_CAPABILITY_FLAGS:
        assert removed not in completed.stdout
    assert "127.0.0.1:11434/api/chat" not in completed.stderr


def test_agent_config_allowlist_rejects_capability_escape_fields():
    safe = {
        "name": "safe",
        "model": "local",
        "domain": "office_demo",
        "num_ctx": 8192,
    }
    shared_runner.validate_config(safe)
    for field in ("root", "allow_shell", "shell", "yolo",
                  "with_domain", "with_office", "tools"):
        with pytest.raises(ValueError, match="unsupported"):
            shared_runner.validate_config({**safe, field: False})


def test_every_checked_in_agent_config_satisfies_the_allowlist():
    for path in PROJECT.glob("agents/*/config.json"):
        if path.parent.name.startswith("_"):
            continue
        shared_runner.validate_config(
            json.loads(path.read_text(encoding="utf-8-sig"))
        )


def test_runtime_paths_preserve_legacy_office_and_namespace_other_domains(
    tmp_path,
):
    office = agent_runtime_paths(tmp_path, load_domain("office_demo"))
    counter = agent_runtime_paths(tmp_path, load_domain("counter_demo"))
    assert office.workspace == tmp_path / "workspace"
    assert office.memory == tmp_path / "memory" / "memory.jsonl"
    assert counter.workspace == (
        tmp_path
        / "runtime"
        / "counter_demo"
        / "0.1.0"
        / "workspace"
    )
    assert office.workspace != counter.workspace
    assert office.memory != counter.memory


def test_benchmark_rejects_invalid_options_before_output_mutation(tmp_path):
    for extra in (
        ["--conditions", "bogus"],
        ["--conditions", "raw", "raw"],
        ["--models", "same", "same"],
        ["--models", "Model", "model"],
        ["--max-calls", "0"],
    ):
        outdir = tmp_path / ("case-" + str(len(list(tmp_path.iterdir()))))
        argv = ["--models", "model"]
        if extra[0] == "--models":
            argv = []
        argv += extra + ["--outdir", str(outdir)]
        with pytest.raises(SystemExit):
            run_bench.main(argv)
        assert not outdir.exists()


@pytest.mark.parametrize(
    "value", ["../escape", r"..\\escape", "\nname", ":", "..."]
)
def test_benchmark_slug_cannot_form_a_traversal_component(value):
    if value in (":", "..."):
        with pytest.raises(ValueError):
            run_bench.slug(value)
    else:
        component = run_bench.slug(value)
        assert "/" not in component
        assert "\\" not in component
        assert component not in {".", ".."}


@pytest.mark.parametrize(
    "value", ["CON", "con.txt", "NUL", "COM1", "lpt9.log"]
)
def test_benchmark_slug_rejects_windows_device_names(value):
    with pytest.raises(ValueError, match="reserved Windows device"):
        run_bench.slug(value)


def test_benchmark_rejects_slug_collisions_before_output_mutation(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(run_bench, "slug", lambda value: "same")
    outdir = tmp_path / "results"
    with pytest.raises(SystemExit):
        run_bench.main(
            [
                "--models",
                "first",
                "second",
                "--outdir",
                str(outdir),
            ]
        )
    assert not outdir.exists()


def test_counter_domain_runs_through_generic_benchmark(
    monkeypatch, tmp_path
):
    base = load_domain("counter_demo")
    reordered_task = replace(
        base.tasks[0],
        tool_names=tuple(reversed(base.tasks[0].tool_names)),
    )
    domain = replace(base, tasks=(reordered_task,))
    monkeypatch.setattr(run_bench, "load_domain", lambda _name: domain)
    monkeypatch.setattr(run_bench, "LLM", CounterBenchLLM)
    outdir = tmp_path / "results"
    run_bench.main(
        [
            "--domain",
            "counter_demo",
            "--models",
            "fake/model",
            "--conditions",
            "raw",
            "--outdir",
            str(outdir),
            "--max-calls",
            "3",
        ]
    )
    records = json.loads(
        (outdir / "results.json").read_text(encoding="utf-8")
    )
    assert len(records) == 1
    assert records[0]["domain"] == "counter_demo"
    assert records[0]["domain_version"] == "0.1.0"
    assert records[0]["score"] == 1.0
    assert records[0]["tools"] == list(
        domain.registry_for(reordered_task).names()
    )
    assert records[0]["tools"] != list(reordered_task.tool_names)
    transcripts = list(
        (outdir / "counter_demo" / "0.1.0").rglob("transcript.md")
    )
    assert len(transcripts) == 1
    assert outdir.resolve() in transcripts[0].resolve().parents


def test_report_separates_domains_and_renders_unknown_capabilities():
    records = [
        result_row("office_demo", "0.1.0", "raw"),
        result_row("office_demo", "0.1.0", "harness"),
        result_row(
            "counter_demo",
            "0.1.0",
            "raw",
            capability="counter_write",
        ),
    ]
    markdown, summary = report.build_report(records)
    assert set(summary["datasets"]) == {
        "office_demo@0.1.0",
        "counter_demo@0.1.0",
    }
    assert "custom_cap" in markdown
    assert "counter_write" in markdown
    counter = summary["datasets"]["counter_demo@0.1.0"]
    assert counter["overall"]["model"]["comparison"]["paired"] is False
    assert "unpaired task sets" in markdown


def test_report_rejects_duplicate_identity_and_incompatible_delta():
    row = result_row("counter_demo", "0.1.0", "raw")
    with pytest.raises(ValueError, match="duplicate benchmark identity"):
        report.build_report([row, dict(row)])

    raw = result_row("counter_demo", "0.1.0", "raw")
    harness = result_row("counter_demo", "0.1.0", "harness")
    harness["tools"] = ["read_counter", "done"]
    _, summary = report.build_report([raw, harness])
    comparison = summary["datasets"]["counter_demo@0.1.0"][
        "overall"
    ]["model"]["comparison"]
    assert comparison == {
        "paired": False,
        "reason": "incompatible surfaces",
        "delta": None,
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda row: row.pop("domain"), "missing fields"),
        (lambda row: row.pop("domain_version"), "missing fields"),
        (lambda row: row.pop("invalid_calls"), "missing fields"),
        (lambda row: row.pop("output_tokens"), "missing fields"),
        (lambda row: row.update(condition="typo"), "invalid condition"),
        (lambda row: row.update(score=float("nan")), "invalid score"),
        (lambda row: row.update(max_calls=0), "invalid max_calls"),
        (
            lambda row: row.update(llm_calls=row["max_calls"] + 1),
            "exceeds max_calls",
        ),
        (lambda row: row.update(tools=["done", "done"]), "invalid tools"),
    ],
)
def test_report_rejects_missing_or_malformed_identity_and_metrics(
    mutation, message
):
    row = result_row("counter_demo", "0.1.0", "raw")
    mutation(row)
    with pytest.raises(ValueError, match=message):
        report.build_report([row])


def test_report_escapes_html_in_untrusted_labels():
    row = result_row("counter_demo", "0.1.0", "raw")
    row["model"] = "<img src=x onerror=alert(1)>"
    row["caps"] = ["<b>counter</b>"]
    markdown, _ = report.build_report([row])
    assert "<img" not in markdown
    assert "<b>" not in markdown
    assert "&lt;img src=x onerror=alert(1)&gt;" in markdown
    assert "&lt;b&gt;counter&lt;/b&gt;" in markdown


def test_training_system_prompt_uses_serving_builder():
    domain = load_domain("office_demo")
    expected = build_harness_system(
        domain.registry,
        domain.default_today.strftime("%A, %B %d, %Y"),
        domain.prompt_profile,
        memory_block="",
        extra_rules=domain.prompt_rules,
    )
    assert gen_toolcall_data.DOMAIN is domain
    assert gen_toolcall_data.SYSTEM == expected
    assert (
        PROJECT / "training_scripts/system_prompt.txt"
    ).read_text(encoding="utf-8") == expected


def test_web_workspace_consumes_both_domain_envelopes(
    monkeypatch, tmp_path
):
    agents = tmp_path / "agents"
    folder = agents / "test"
    folder.mkdir(parents=True)
    (folder / "config.json").write_text(
        json.dumps(
            {
                "name": "test",
                "model": "fake",
                "domain": "office_demo",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(web_server, "AGENTS_DIR", str(agents))

    office = web_server.workspace("test", "office_demo")
    counter = web_server.workspace("test", "counter_demo")
    for state, name in (
        (office, "office_demo"),
        (counter, "counter_demo"),
    ):
        assert state["domain"] == name
        assert state["version"] == "0.1.0"
        assert isinstance(state["sections"], list)
        assert isinstance(state["files"], list)
        assert isinstance(state["memory"], list)
    assert office["folder"] != counter["folder"]


def test_web_runner_rejects_agent_traversal():
    for value in ("../8b", r"..\\8b", "/tmp", ""):
        with pytest.raises(ValueError):
            web_runner.resolve_agent_folder(value)


def test_web_ingress_rejects_retired_capabilities_before_start():
    for field in web_server.REMOVED_RUN_FIELDS:
        with pytest.raises(ValueError, match="unsupported"):
            web_server.reject_removed_run_fields({field: False})
    web_server.reject_removed_run_fields(
        {
            "agent": "1b",
            "domain": "office_demo",
            "task": "safe synthetic task",
        }
    )

    base = ["--agent", "1b", "--task", "safe"]
    for extra in (
        ["--root", "/tmp"],
        ["--shell"],
        ["--yolo"],
        ["--with-domain"],
        ["--with-office"],
    ):
        with pytest.raises(SystemExit):
            web_runner.main(base + extra)


def test_web_path_resolution_rejects_prefix_and_symlink_escape(tmp_path):
    root = tmp_path / "static"
    sibling = tmp_path / "static-private"
    root.mkdir()
    sibling.mkdir()
    (root / "ok.txt").write_text("ok", encoding="utf-8")
    (sibling / "secret.txt").write_text("secret", encoding="utf-8")

    assert Path(web_server._resolve_under(root, "ok.txt")) == (
        root / "ok.txt"
    ).resolve()
    with pytest.raises(ValueError, match="outside"):
        web_server._resolve_under(root, "..", "static-private", "secret.txt")

    link = root / "linked"
    try:
        link.symlink_to(sibling, target_is_directory=True)
    except (NotImplementedError, OSError):
        return
    with pytest.raises(ValueError, match="outside"):
        web_server._resolve_under(root, "linked", "secret.txt")


def test_frontend_passes_and_locks_selected_domain():
    source = (PROJECT / "webui/static/app.js").read_text(
        encoding="utf-8"
    )
    html = (PROJECT / "webui/static/index.html").read_text(
        encoding="utf-8"
    )
    assert 'id="opt-domain"' in html
    assert "domain: S.domain" in source
    assert "/api/workspace?agent=" in source
    assert "&domain=" in source
    assert "S.locked = true" in source
    assert "if (!S.agent || S.locked) return" in source
    assert "$('opt-domain').disabled = true" in source
    assert "$('run').disabled = false" in source
    retired_tokens = (
        "opt-root",
        "opt-shell",
        "opt-yolo",
        "opt-office",
        "with_domain",
        "with_office",
        "/api/confirm",
    )
    for token in retired_tokens:
        assert token not in source
        assert token not in html
    runner_source = (PROJECT / "webui/runner.py").read_text(
        encoding="utf-8"
    )
    assert '"retained_hints": router.retained_model_hints()' in runner_source
    assert "resident_models" not in runner_source
