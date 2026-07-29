import json
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
        "parse_failures": 0,
        "invalid_calls": 0,
        "tool_errors": 0,
        "llm_calls": 1,
        "wall_seconds": 0.1,
        "output_tokens": 1,
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


def test_agent_flag_precedence_and_domain_overlay_surface(tmp_path):
    options, task = shared_runner.parse_flags(
        [
            "--domain",
            "counter_demo",
            "--with-domain",
            "--max-calls",
            "0",
            "increment",
        ]
    )
    assert options["domain_name"] == "counter_demo"
    assert options["include_domain"] is True
    assert options["max_calls"] == 0
    assert task == "increment"

    root = tmp_path / "root"
    root.mkdir()
    counter = load_domain("counter_demo")
    tools, policy, profile, rules, resolved = shared_runner._surface(
        counter, root, True, False, None
    )
    assert "increment_counter" in tools
    assert "write_file" in tools
    assert policy.effect("increment_counter") == "state_write"
    assert policy.effect("write_file") == "external_write"
    assert profile is counter.prompt_profile
    assert str(root) in rules
    assert resolved == str(root)


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


def test_frontend_passes_and_locks_selected_domain():
    source = (PROJECT / "webui/static/app.js").read_text(
        encoding="utf-8"
    )
    html = (PROJECT / "webui/static/index.html").read_text(
        encoding="utf-8"
    )
    assert 'id="opt-domain"' in html
    assert "domain: S.domain" in source
    assert "with_domain:" in source
    assert "/api/workspace?agent=" in source
    assert "&domain=" in source
    assert "S.locked = true" in source
    assert "if (!S.agent || S.locked) return" in source
    assert "$('opt-domain').disabled = true" in source
    assert "$('run').disabled = false" in source
    runner_source = (PROJECT / "webui/runner.py").read_text(
        encoding="utf-8"
    )
    assert '"retained_hints": router.retained_model_hints()' in runner_source
    assert "resident_models" not in runner_source
