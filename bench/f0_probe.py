"""Reproducible Lenovo feasibility gate for Brick.

F0 is an infrastructure probe, not a benchmark. It verifies the exact local
model artifacts, Ollama-native tool transport, warm throughput, process-tree
memory and the disposable marker-last storage spike before research code is
allowed to depend on them.
"""

import argparse
import copy
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import time
import urllib.parse
import uuid

import requests

from bench import f0_storage, f0_windows


PROTOCOL_PATH = Path(__file__).with_name("f0_protocol.json")
OLLAMA_URL = "http://127.0.0.1:11434"
SUMMARY_SCHEMA = "brick.f0.summary/2"
# The v1 protocol gated on unknown-option rejection, which Ollama never
# promised. That candidate's failed bundle stays immutable and must remain
# verifiable, so its schema is still accepted for integrity verification only.
LEGACY_SUMMARY_SCHEMA = "brick.f0.summary/1"
PREPARED_SCHEMA = "brick.f0.report-prepared/1"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_REPORT_RETRY_DELAYS = (0.0, 0.05, 0.1, 0.2, 0.4, 0.8, 1.6)
_EXPECTED_SAMPLING = {
    "think": False,
    "temperature": 1.0,
    "top_p": 1.0,
    "top_k": 20,
    "min_p": 0.0,
    "presence_penalty": 2.0,
    "repeat_penalty": 1.0,
    "num_ctx": 8192,
}
_EXPECTED_MODELS = [
    {
        "tag": "qwen3.5:4b-q4_K_M",
        "role": "primary",
        "min_eval_tps": 5.0,
    },
    {
        "tag": "qwen3.5:2b-q4_K_M",
        "role": "descriptive",
        "min_eval_tps": None,
    },
    {
        "tag": "qwen3.5:9b-q4_K_M",
        "role": "descriptive",
        "min_eval_tps": 3.0,
    },
]
_EXPECTED_OPTION_CONTRACT = {
    "temperature": "float",
    "top_p": "float",
    "min_p": "float",
    "presence_penalty": "float",
    "repeat_penalty": "float",
    "top_k": "integer",
    "num_ctx": "integer",
    "seed": "integer",
    "num_predict": "integer",
}
_PROTOCOL_KEYS = frozenset(
    {
        "schema_version",
        "primary_model",
        "models",
        "sampling",
        "option_contract",
        "recognition_suite",
        "unknown_option_sentinel",
        "recognition_invalid_value",
        "request_timeout_seconds",
        "max_tree_private_commit_bytes",
        "minimum_free_disk_bytes_after_pulls",
        "minimum_physical_memory_bytes",
        "runtime_warmups",
        "runtime_samples",
        "runtime_num_predict",
        "minimum_valid_runtime_samples",
        "storage_cycles",
        "storage_process_exits",
        "storage_held_handle_cycles",
        "conformance_suite",
    }
)


class F0Error(RuntimeError):
    """The live F0 probe could not satisfy a required invariant."""


TOOLS_RECORD_VALUES = [
    {
        "type": "function",
        "function": {
            "name": "record_values",
            "description": "Record the three supplied values exactly.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "count", "enabled"],
                "properties": {
                    "label": {"type": "string"},
                    "count": {"type": "integer"},
                    "enabled": {"type": "boolean"},
                },
            },
        },
    }
]
TOOLS_SELECTION = [
    {
        "type": "function",
        "function": {
            "name": "lookup_shape",
            "description": "Look up only an item's shape.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["item_id"],
                "properties": {"item_id": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_color",
            "description": "Look up only an item's color.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["item_id"],
                "properties": {"item_id": {"type": "string"}},
            },
        },
    },
]
TOOLS_ROUNDTRIP = [
    {
        "type": "function",
        "function": {
            "name": "read_nonce",
            "description": "Read the nonce for one key.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["key"],
                "properties": {"key": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_nonce",
            "description": "Submit the exact nonce returned by read_nonce.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["nonce"],
                "properties": {"nonce": {"type": "string"}},
            },
        },
    },
]


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _canonical_bytes(value):
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _write_bytes(path, value, exclusive=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb" if exclusive else "wb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def _write_json(path, value, exclusive=True):
    _write_bytes(path, _canonical_bytes(value), exclusive=exclusive)


def _sha256(path):
    return f0_windows.sha256_file(path)


def _protocol_hash(protocol):
    return hashlib.sha256(_canonical_bytes(protocol)).hexdigest()


def load_protocol(path=PROTOCOL_PATH):
    with Path(path).open("r", encoding="utf-8") as handle:
        protocol = json.load(handle)
    validate_protocol(protocol)
    return protocol


def validate_protocol(protocol):
    if not isinstance(protocol, dict):
        raise F0Error("F0 protocol must be an object")
    if protocol.get("schema_version") != "brick.f0.protocol/2":
        raise F0Error("unsupported F0 protocol schema")
    if set(protocol) != _PROTOCOL_KEYS:
        raise F0Error("F0 protocol fields do not match schema version 2")
    models = protocol.get("models")
    if not isinstance(models, list) or len(models) != 3:
        raise F0Error("F0 protocol requires exactly three model entries")
    if models != _EXPECTED_MODELS:
        raise F0Error(
            "F0 model matrix differs from the version-1 research contract"
        )
    tags = []
    primary = []
    for model in models:
        if not isinstance(model, dict):
            raise F0Error("F0 model entries must be objects")
        tag = model.get("tag")
        if not isinstance(tag, str) or not tag:
            raise F0Error("F0 model tag must be nonempty")
        tags.append(tag)
        if model.get("role") == "primary":
            primary.append(tag)
        elif model.get("role") != "descriptive":
            raise F0Error("F0 model role must be primary or descriptive")
        minimum = model.get("min_eval_tps")
        if minimum is not None and (
            isinstance(minimum, bool)
            or not isinstance(minimum, (int, float))
            or minimum <= 0
        ):
            raise F0Error("minimum eval throughput must be positive")
    if len(set(tags)) != len(tags):
        raise F0Error("F0 model tags must be unique")
    if primary != [protocol.get("primary_model")]:
        raise F0Error("F0 protocol must identify exactly one primary model")
    sampling = protocol.get("sampling")
    if sampling != _EXPECTED_SAMPLING:
        raise F0Error(
            "F0 sampling differs from the version-2 research contract"
        )
    if protocol.get("option_contract") != _EXPECTED_OPTION_CONTRACT:
        raise F0Error(
            "F0 option contract differs from the version-2 research contract"
        )
    if protocol.get("recognition_suite") != "option-recognition-v2":
        raise F0Error("unsupported option-recognition suite")
    for field in ("unknown_option_sentinel", "recognition_invalid_value"):
        value = protocol.get(field)
        if not isinstance(value, str) or not value.strip():
            raise F0Error(f"{field} must be a nonempty string")
    if (
        protocol["unknown_option_sentinel"]
        in _EXPECTED_OPTION_CONTRACT
    ):
        raise F0Error("the unknown-option sentinel collides with a real option")
    # Every option the probe actually sends must be covered by the contract so
    # that recognition is proven for the exact production option map.
    sent_options = set(_EXPECTED_OPTION_CONTRACT)
    declared = set(sampling) - {"think"}
    if not declared <= sent_options:
        raise F0Error("sampling declares options outside the option contract")
    integer_fields = (
        "request_timeout_seconds",
        "max_tree_private_commit_bytes",
        "minimum_free_disk_bytes_after_pulls",
        "minimum_physical_memory_bytes",
        "runtime_warmups",
        "runtime_samples",
        "runtime_num_predict",
        "minimum_valid_runtime_samples",
        "storage_cycles",
        "storage_process_exits",
        "storage_held_handle_cycles",
    )
    for field in integer_fields:
        if type(protocol.get(field)) is not int or protocol[field] < 0:
            raise F0Error(f"{field} must be a nonnegative integer")
    if protocol["request_timeout_seconds"] < 1:
        raise F0Error("request timeout must be positive")
    if protocol["request_timeout_seconds"] > 600:
        raise F0Error("request timeout exceeds the ten-minute gate")
    if not (
        0
        < protocol["max_tree_private_commit_bytes"]
        <= 28 * 1024 ** 3
    ):
        raise F0Error("process-memory ceiling is weaker than 28 GiB")
    if protocol["minimum_free_disk_bytes_after_pulls"] < 30 * 1024 ** 3:
        raise F0Error("post-pull free-disk floor is below 30 GiB")
    if protocol["minimum_physical_memory_bytes"] < 30 * 1024 ** 3:
        raise F0Error("physical-memory floor is below 30 GiB")
    if protocol["runtime_warmups"] < 1:
        raise F0Error("at least one runtime warm-up is required")
    if protocol["runtime_samples"] < 5:
        raise F0Error("at least five runtime samples are required")
    if protocol["runtime_num_predict"] < 128:
        raise F0Error("runtime generation budget is too short")
    if protocol["minimum_valid_runtime_samples"] < 3:
        raise F0Error("at least three valid runtime samples are required")
    if not (
        1
        <= protocol["minimum_valid_runtime_samples"]
        <= protocol["runtime_samples"]
    ):
        raise F0Error("valid runtime sample count is inconsistent")
    if (
        protocol["storage_process_exits"]
        + protocol["storage_held_handle_cycles"]
        > protocol["storage_cycles"]
    ):
        raise F0Error("storage subcases exceed total cycles")
    if protocol["storage_cycles"] < 200:
        raise F0Error("fewer than 200 storage cycles are not eligible")
    if protocol["storage_process_exits"] < 50:
        raise F0Error("fewer than 50 process exits are not eligible")
    if protocol["storage_held_handle_cycles"] < 1:
        raise F0Error("held-handle storage coverage is required")
    if protocol.get("conformance_suite") != "native-tools-v1":
        raise F0Error("unsupported native-tool conformance suite")


def _validate_endpoint(endpoint):
    parsed = urllib.parse.urlsplit(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.port != 11434
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise F0Error("Ollama F0 endpoint must be loopback port 11434")
    return endpoint.rstrip("/")


class OllamaProbeClient:
    """Small raw-JSON Ollama client used only by the feasibility probe."""

    def __init__(self, endpoint=OLLAMA_URL, timeout=600, session=None):
        self.endpoint = _validate_endpoint(endpoint)
        self.timeout = int(timeout)
        if session is None:
            session = requests.Session()
            # The loopback control connection must not be redirected through
            # ambient HTTP proxy configuration.
            session.trust_env = False
        self.session = session

    def get(self, path):
        response = self.session.get(
            self.endpoint + path, timeout=(5, self.timeout)
        )
        response.raise_for_status()
        return response.json()

    def post(self, path, payload):
        response = self.session.post(
            self.endpoint + path,
            json=payload,
            timeout=(5, self.timeout),
        )
        response.raise_for_status()
        return response.json()

    def pull(self, model, log_path):
        started = time.monotonic()
        response = self.session.post(
            self.endpoint + "/api/pull",
            json={"model": model, "stream": True},
            stream=True,
            timeout=(5, self.timeout),
        )
        response.raise_for_status()
        final = None
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            for line in response.iter_lines(decode_unicode=True):
                if time.monotonic() - started > self.timeout:
                    raise F0Error(
                        f"Ollama pull exceeded the deadline for {model}"
                    )
                if not line:
                    continue
                value = json.loads(line)
                handle.write(
                    json.dumps(
                        value, ensure_ascii=False, sort_keys=True
                    )
                    + "\n"
                )
                handle.flush()
                final = value
            os.fsync(handle.fileno())
        if not isinstance(final, dict) or final.get("status") != "success":
            raise F0Error(f"Ollama pull did not complete for {model}")
        return final

    def chat(self, payload):
        return self.post("/api/chat", payload)

    def rejected_post(self, path, payload):
        """Return a structured 4xx response without treating it as success."""
        response = self.session.post(
            self.endpoint + path,
            json=payload,
            timeout=(5, self.timeout),
        )
        try:
            body = response.json()
        except ValueError:
            body = {"text": response.text[-2000:]}
        return {"status_code": response.status_code, "body": body}

    def unload(self, model):
        return self.post(
            "/api/generate",
            {
                "model": model,
                "prompt": "",
                "stream": False,
                "keep_alive": 0,
            },
        )


def _seed(protocol_sha256, model_digest, case_id):
    material = "\0".join(
        (protocol_sha256, model_digest, case_id)
    ).encode("utf-8")
    return int.from_bytes(
        hashlib.sha256(material).digest()[:4], "big"
    ) & 0x7FFFFFFF


_REQUEST_TOP_LEVEL_KEYS = frozenset(
    {"model", "messages", "tools", "stream", "think", "keep_alive", "options"}
)


def validate_chat_request(payload, protocol):
    """Fail closed on any request Brick itself has not fully specified.

    F0 v1 relied on the server to reject a malformed option map. Ollama does
    not promise that, so Brick owns the contract: every request is checked
    against the frozen protocol *before* it reaches the network, and an
    unexpected key, type, value, or non-finite number raises rather than
    silently reaching the model.
    """
    sampling = protocol["sampling"]
    contract = protocol["option_contract"]
    if not isinstance(payload, dict):
        raise F0Error("chat request must be an object")
    if set(payload) != _REQUEST_TOP_LEVEL_KEYS:
        raise F0Error(
            "chat request keys do not match the frozen request contract"
        )
    if not isinstance(payload["model"], str) or not payload["model"].strip():
        raise F0Error("chat request model must be a nonempty string")
    if not isinstance(payload["messages"], list) or not payload["messages"]:
        raise F0Error("chat request requires at least one message")
    for message in payload["messages"]:
        if not isinstance(message, dict) or not isinstance(
            message.get("role"), str
        ):
            raise F0Error("chat request message is malformed")
    if not isinstance(payload["tools"], list):
        raise F0Error("chat request tools must be a list")
    if payload["stream"] is not False:
        raise F0Error("chat request must set stream to false")
    if payload["think"] is not sampling["think"]:
        raise F0Error("chat request think flag differs from the protocol")
    if not isinstance(payload["keep_alive"], str) or not payload["keep_alive"]:
        raise F0Error("chat request keep_alive must be a nonempty string")
    options = payload["options"]
    if not isinstance(options, dict):
        raise F0Error("chat request options must be an object")
    if set(options) != set(contract):
        missing = sorted(set(contract) - set(options))
        extra = sorted(set(options) - set(contract))
        raise F0Error(
            "chat request option keys do not match the option contract"
            + (f"; missing={missing}" if missing else "")
            + (f"; unexpected={extra}" if extra else "")
        )
    for key, expected in sorted(contract.items()):
        value = options[key]
        if expected == "integer":
            # type() rather than isinstance() so bool cannot pass as int.
            if type(value) is not int:
                raise F0Error(f"option {key} must be an integer")
        elif expected == "float":
            if type(value) not in (int, float):
                raise F0Error(f"option {key} must be a real number")
            if not math.isfinite(float(value)):
                raise F0Error(f"option {key} must be finite")
        else:
            raise F0Error(f"option {key} has an unsupported contract type")
    for key in (
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "presence_penalty",
        "repeat_penalty",
        "num_ctx",
    ):
        if options[key] != sampling[key]:
            raise F0Error(
                f"option {key} differs from the frozen sampling policy"
            )
    if not 0 <= options["seed"] <= 0x7FFFFFFF:
        raise F0Error("option seed is outside the reproducible range")
    if options["num_predict"] < 1:
        raise F0Error("option num_predict must be positive")
    return payload


def _chat_payload(
    protocol,
    model,
    messages,
    tools,
    seed,
    num_predict=128,
):
    sampling = protocol["sampling"]
    payload = {
        "model": model,
        "messages": copy.deepcopy(messages),
        "tools": copy.deepcopy(tools),
        "stream": False,
        "think": sampling["think"],
        "keep_alive": "10m",
        "options": {
            "seed": seed,
            "num_ctx": sampling["num_ctx"],
            "num_predict": num_predict,
            "temperature": sampling["temperature"],
            "top_p": sampling["top_p"],
            "top_k": sampling["top_k"],
            "min_p": sampling["min_p"],
            "presence_penalty": sampling["presence_penalty"],
            "repeat_penalty": sampling["repeat_penalty"],
        },
    }
    return validate_chat_request(payload, protocol)


def _tool_calls(response):
    if not isinstance(response, dict):
        raise F0Error("Ollama chat response is not an object")
    message = response.get("message")
    if not isinstance(message, dict):
        raise F0Error("Ollama chat response has no message object")
    calls = message.get("tool_calls")
    if not isinstance(calls, list):
        return []
    parsed = []
    for item in calls:
        function = item.get("function") if isinstance(item, dict) else None
        if not isinstance(function, dict):
            raise F0Error("native tool call has no function object")
        name = function.get("name")
        arguments = function.get("arguments")
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise F0Error("native tool call name or arguments are malformed")
        parsed.append({"name": name, "arguments": arguments})
    return parsed


def _exact_call(response, name, arguments):
    return _tool_calls(response) == [
        {"name": name, "arguments": arguments}
    ]


def _thinking_disabled(response):
    message = response.get("message") if isinstance(response, dict) else None
    return (
        isinstance(message, dict)
        and message.get("thinking") in {None, ""}
    )


def _tool_response_envelope_valid(response, model):
    message = response.get("message") if isinstance(response, dict) else None
    return (
        isinstance(response, dict)
        and response.get("model") == model
        and response.get("done") is True
        and isinstance(message, dict)
        and message.get("role") == "assistant"
        and _thinking_disabled(response)
    )


def _request_case(
    client,
    protocol,
    model,
    digest,
    case_id,
    messages,
    tools,
    directory,
    index=1,
):
    payload = _chat_payload(
        protocol,
        model,
        messages,
        tools,
        _seed(_protocol_hash(protocol), digest, case_id),
    )
    _write_json(directory / f"request-{index}.json", payload)
    started = time.monotonic()
    response = client.chat(payload)
    wall = time.monotonic() - started
    response = copy.deepcopy(response)
    response["_f0_client_wall_seconds"] = wall
    _write_json(directory / f"response-{index}.json", response)
    if wall > protocol["request_timeout_seconds"]:
        raise F0Error(f"{case_id} exceeded the request deadline")
    return response


def run_conformance(client, protocol, model, digest, output_dir):
    output_dir = Path(output_dir)
    verdicts = []

    case_dir = output_dir / "single_typed"
    response = _request_case(
        client,
        protocol,
        model,
        digest,
        "single_typed",
        [
            {
                "role": "user",
                "content": (
                    "Call record_values exactly once with label delta-7, "
                    "count 3, and enabled true. Do not call another tool."
                ),
            }
        ],
        TOOLS_RECORD_VALUES,
        case_dir,
    )
    verdicts.append(
        {
            "case_id": "single_typed",
            "passed": _exact_call(
                response,
                "record_values",
                {"label": "delta-7", "count": 3, "enabled": True},
            )
            and _tool_response_envelope_valid(response, model),
        }
    )

    case_dir = output_dir / "tool_selection"
    response = _request_case(
        client,
        protocol,
        model,
        digest,
        "tool_selection",
        [
            {
                "role": "user",
                "content": (
                    "Use only lookup_shape for item_id unit-204. "
                    "Do not call lookup_color."
                ),
            }
        ],
        TOOLS_SELECTION,
        case_dir,
    )
    verdicts.append(
        {
            "case_id": "tool_selection",
            "passed": _exact_call(
                response, "lookup_shape", {"item_id": "unit-204"}
            )
            and _tool_response_envelope_valid(response, model),
        }
    )

    case_dir = output_dir / "result_roundtrip"
    messages = [
        {
            "role": "user",
            "content": (
                "First call read_nonce with key alpha. After its result, "
                "call submit_nonce with the returned nonce."
            ),
        }
    ]
    first = _request_case(
        client,
        protocol,
        model,
        digest,
        "result_roundtrip",
        messages,
        TOOLS_ROUNDTRIP,
        case_dir,
        index=1,
    )
    first_ok = (
        _exact_call(first, "read_nonce", {"key": "alpha"})
        and _tool_response_envelope_valid(first, model)
    )
    second_ok = False
    if first_ok:
        messages.append(copy.deepcopy(first["message"]))
        messages.append(
            {
                "role": "tool",
                "tool_name": "read_nonce",
                "content": '{"nonce":"F0-6E19"}',
            }
        )
        second = _request_case(
            client,
            protocol,
            model,
            digest,
            "result_roundtrip",
            messages,
            TOOLS_ROUNDTRIP,
            case_dir,
            index=2,
        )
        second_ok = (
            _exact_call(second, "submit_nonce", {"nonce": "F0-6E19"})
            and _tool_response_envelope_valid(second, model)
        )
    verdicts.append(
        {
            "case_id": "result_roundtrip",
            "passed": first_ok and second_ok,
            "step_1_passed": first_ok,
            "step_2_passed": second_ok,
        }
    )
    for verdict in verdicts:
        _write_json(
            output_dir / verdict["case_id"] / "verdict.json",
            {
                "schema_version": "brick.f0.conformance-verdict/1",
                **verdict,
            },
        )
    return {
        "schema_version": "brick.f0.conformance-summary/1",
        "suite": protocol["conformance_suite"],
        "passed": all(item["passed"] for item in verdicts),
        "cases": verdicts,
    }


def _recognition_case(
    client, output_dir, name, payload, key=None, expected_type=None
):
    """Post one deliberately-shaped payload and record it verbatim."""
    _write_json(output_dir / f"{name}-request.json", payload)
    response = client.rejected_post("/api/chat", payload)
    _write_json(output_dir / f"{name}-response.json", response)
    return _recognition_response(response, key, expected_type)


def _recognition_response(response, key=None, expected_type=None):
    """Reduce one raw recognition response without trusting summary prose."""
    status = response.get("status_code")
    serialized = json.dumps(
        response.get("body"), ensure_ascii=False, sort_keys=True
    )
    body = serialized[:2000]
    result = {
        "status_code": status,
        "is_success": type(status) is int and 200 <= status < 300,
        "is_http_error": type(status) is int and 400 <= status < 600,
        "body_text": body,
    }
    if key is not None and expected_type is not None:
        folded = body.casefold()
        result.update(
            {
                "body_names_key": key.casefold() in folded,
                "body_states_expected_type": (
                    expected_type.casefold() in folded
                ),
            }
        )
        result["recognized"] = (
            result["is_http_error"]
            and result["body_names_key"]
            and result["body_states_expected_type"]
        )
    return result


def _recognition_payload(protocol, model, digest, case_id):
    return _chat_payload(
        protocol,
        model,
        [{"role": "user", "content": "Reply with the word ok."}],
        [],
        _seed(_protocol_hash(protocol), digest, case_id),
        num_predict=4,
    )


def run_option_recognition(client, protocol, model, digest, output_dir):
    """Prove the server recognizes every frozen option name, key by key.

    F0 v1 gated on the server rejecting an *unknown* option name. Ollama does
    not promise that and 0.32.5 ignores unknown names, so that check tested an
    assumption the runtime never made. Recognition is instead proven
    positively: a real option name carrying a deliberately invalid value type
    must return a 4xx/5xx response whose body names that key and its declared
    type. The identical invalid value under an unknown name is diagnostic only:
    runtimes may either ignore or reject unknown names. Unlike an output
    differential, the real-key check holds at the frozen values -- including
    the neutral ones (``top_p=1.0``, ``min_p=0``,
    ``repeat_penalty=1.0``) where changing a no-op cannot change any output.

    This proves per-key recognition and the declared value type. It does not
    claim to prove the numerical semantics of any sampler.
    """
    output_dir = Path(output_dir)
    contract = protocol["option_contract"]
    sentinel = protocol["unknown_option_sentinel"]
    invalid = protocol["recognition_invalid_value"]
    def valid_payload(case_id):
        return _recognition_payload(protocol, model, digest, case_id)

    baseline = _recognition_case(
        client, output_dir, "baseline", valid_payload("recognition-baseline")
    )

    keys = {}
    for key in sorted(contract):
        payload = copy.deepcopy(valid_payload(f"recognition-{key}"))
        # Deliberately invalid: bypasses validate_chat_request by construction.
        payload["options"][key] = invalid
        observation = _recognition_case(
            client,
            output_dir,
            f"option-{key}",
            payload,
            key,
            contract[key],
        )
        keys[key] = {
            "expected_type": contract[key],
            "status_code": observation["status_code"],
            "rejected": not observation["is_success"],
            "http_error": observation["is_http_error"],
            "body_names_key": observation["body_names_key"],
            "body_states_expected_type": observation[
                "body_states_expected_type"
            ],
            "recognized": observation["recognized"],
            "body_text": observation["body_text"],
        }

    unknown_payload = copy.deepcopy(valid_payload("recognition-unknown"))
    unknown_payload["options"][sentinel] = invalid
    unknown = _recognition_case(
        client, output_dir, "unknown-option", unknown_payload
    )
    health = _recognition_case(
        client, output_dir, "health", valid_payload("recognition-health")
    )

    recognized = sorted(
        key for key, item in keys.items() if item["recognized"]
    )
    unrecognized = sorted(
        key for key, item in keys.items() if not item["recognized"]
    )
    rejected = sorted(key for key, item in keys.items() if item["rejected"])
    accepted = sorted(key for key, item in keys.items() if not item["rejected"])
    named = sorted(key for key, item in keys.items() if item["body_names_key"])
    typed = sorted(
        key
        for key, item in keys.items()
        if item["body_states_expected_type"]
    )
    error_status = sorted(
        key for key, item in keys.items() if item["http_error"]
    )
    passed = (
        baseline["is_success"]
        and health["is_success"]
        and len(recognized) == len(contract)
        and not unrecognized
    )
    failure_codes = []
    if not baseline["is_success"]:
        failure_codes.append("frozen_option_map_rejected")
    if unrecognized:
        failure_codes.append("option_names_not_recognized")
    if len(error_status) != len(contract):
        failure_codes.append("option_error_status_invalid")
    if len(named) != len(contract):
        failure_codes.append("option_error_did_not_name_key")
    if len(typed) != len(contract):
        failure_codes.append("option_error_did_not_state_type")
    if not health["is_success"]:
        failure_codes.append("server_unhealthy_after_probe")
    summary = {
        "schema_version": "brick.f0.option-recognition/2",
        "suite": protocol["recognition_suite"],
        "sentinel_option": sentinel,
        "invalid_value": invalid,
        "baseline_accepted": baseline["is_success"],
        "baseline_status_code": baseline["status_code"],
        "health_accepted": health["is_success"],
        "health_status_code": health["status_code"],
        "recognized_options": recognized,
        "unrecognized_options": unrecognized,
        "rejected_options": rejected,
        "accepted_options": accepted,
        "options_with_http_error": error_status,
        "options_named_in_error": named,
        "options_typed_in_error": typed,
        "options": keys,
        "unknown_option_status_code": unknown["status_code"],
        "unknown_option_accepted": unknown["is_success"],
        "unknown_option_body": unknown["body_text"],
        "passed": passed,
        "failure_codes": failure_codes,
        "interpretation": (
            "Every frozen option name was recognized: each returned a 4xx/5xx "
            "error naming the key and its expected type when given an invalid "
            "value. Recognition and declared type are established for the "
            "exact production option map; unknown-name behavior is diagnostic "
            "only, and numerical sampler behavior is not claimed."
            if passed
            else (
                "Option recognition failed. Unrecognized options: "
                + (", ".join(unrecognized) if unrecognized else "none")
                + ". Failure codes: "
                + (", ".join(failure_codes) if failure_codes else "none")
                + "."
            )
        ),
        "unknown_option_note": (
            "Unknown option names are ignored by this build rather than "
            "rejected. That is recorded as a diagnostic typo hazard and does "
            "not gate the run."
            if unknown["is_success"]
            else "This build also rejects unknown option names."
        ),
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


def _runtime_prompt():
    return (
        "Write a fictional inventory of about 220 short lowercase words, "
        "separated by spaces. Do not number the words and do not use tools."
    )


def run_runtime(client, protocol, model, digest, output_dir):
    output_dir = Path(output_dir)
    results = []
    total = protocol["runtime_warmups"] + protocol["runtime_samples"]
    for index in range(total):
        warmup = index < protocol["runtime_warmups"]
        case_id = f"runtime-{index + 1}"
        stem = (
            "warmup"
            if warmup
            else f"sample-{index - protocol['runtime_warmups'] + 1:02d}"
        )
        payload = _chat_payload(
            protocol,
            model,
            [{"role": "user", "content": _runtime_prompt()}],
            [],
            _seed(_protocol_hash(protocol), digest, case_id),
            num_predict=protocol["runtime_num_predict"],
        )
        _write_json(output_dir / f"{stem}-request.json", payload)
        started = time.monotonic()
        response = client.chat(payload)
        wall = time.monotonic() - started
        _write_json(output_dir / f"{stem}-response.json", response)
        if not isinstance(response, dict):
            raise F0Error("runtime chat response is not an object")
        message = (
            response.get("message")
            if isinstance(response, dict)
            else None
        )
        response_model = (
            response.get("model") if isinstance(response, dict) else None
        )
        assistant_content = (
            message.get("content") if isinstance(message, dict) else None
        )
        record = {
            "schema_version": "brick.f0.runtime-sample/1",
            "warmup": warmup,
            "client_wall_seconds": wall,
            "total_duration": response.get("total_duration"),
            "load_duration": response.get("load_duration"),
            "prompt_eval_count": response.get("prompt_eval_count"),
            "prompt_eval_duration": response.get("prompt_eval_duration"),
            "eval_count": response.get("eval_count"),
            "eval_duration": response.get("eval_duration"),
            "done": response.get("done"),
            "done_reason": response.get("done_reason"),
            "response_model": response_model,
            "assistant_message_valid": (
                isinstance(message, dict)
                and message.get("role") == "assistant"
                and isinstance(assistant_content, str)
                and bool(assistant_content.strip())
                and _thinking_disabled(response)
            ),
        }
        count = record["eval_count"]
        duration = record["eval_duration"]
        if (
            type(count) is int
            and count >= 128
            and type(duration) is int
            and duration > 0
            and record["done"] is True
            and response_model == model
            and record["assistant_message_valid"]
        ):
            record["eval_tps"] = count / (duration / 1_000_000_000)
        else:
            record["eval_tps"] = None
        _write_json(output_dir / f"{stem}.json", record)
        if not warmup:
            results.append(record)
        if wall > protocol["request_timeout_seconds"]:
            raise F0Error("runtime request exceeded the request deadline")
    valid = [
        item["eval_tps"]
        for item in results
        if item["eval_tps"] is not None
    ]
    return {
        "schema_version": "brick.f0.runtime-summary/1",
        "valid_samples": len(valid),
        "required_valid_samples": protocol[
            "minimum_valid_runtime_samples"
        ],
        "median_eval_tps": statistics.median(valid) if valid else None,
        "passed": (
            len(valid) >= protocol["minimum_valid_runtime_samples"]
        ),
    }


def _safe_model_slug(model):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", model).strip("._-")
    if not cleaned:
        raise F0Error("model tag cannot form a safe artifact directory")
    return cleaned


def _tag_entry(tags, model):
    entries = tags.get("models") if isinstance(tags, dict) else None
    if not isinstance(entries, list):
        raise F0Error("Ollama tags response is malformed")
    matches = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and entry.get("name", entry.get("model")) == model
    ]
    if len(matches) != 1:
        raise F0Error(f"exact installed model tag not found: {model}")
    digest = matches[0].get("digest")
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        raise F0Error(f"model {model} has no full immutable digest")
    return matches[0]


def _metadata_summary(model, tag, show):
    failures = []
    details = show.get("details") if isinstance(show, dict) else None
    if not isinstance(details, dict):
        failures.append("show response has no details object")
        details = {}
    quantization = details.get("quantization_level")
    if (
        not isinstance(quantization, str)
        or quantization.casefold() != "q4_k_m"
    ):
        failures.append("quantization is not Q4_K_M")
    tag_details = tag.get("details")
    if not isinstance(tag_details, dict):
        tag_details = {}
    family = details.get("family", tag_details.get("family"))
    if not isinstance(family, str) or "qwen" not in family.casefold():
        failures.append("model family is not identified as Qwen")
    expected_size = {
        "qwen3.5:2b-q4_K_M": "2",
        "qwen3.5:4b-q4_K_M": "4",
        "qwen3.5:9b-q4_K_M": "9",
    }[model]
    parameter_size = details.get(
        "parameter_size", tag_details.get("parameter_size")
    )
    if (
        not isinstance(parameter_size, str)
        or not re.fullmatch(
            rf"{expected_size}(?:\.[0-9]+)?B",
            parameter_size,
            flags=re.IGNORECASE,
        )
    ):
        failures.append(
            f"parameter size does not identify the expected {expected_size}B class"
        )
    capabilities = show.get("capabilities")
    if not isinstance(capabilities, list):
        capabilities = []
    if "tools" not in capabilities:
        failures.append("model does not advertise native tool capability")
    template = show.get("template")
    if not isinstance(template, str) or not template.strip():
        failures.append("show response has no effective chat template")
    return {
        "schema_version": "brick.f0.model-metadata/1",
        "tag": model,
        "digest": tag["digest"],
        "size": tag.get("size"),
        "details": details,
        "capabilities": capabilities,
        "family": family,
        "parameter_size": parameter_size,
        "tool_capability_advertised": "tools" in capabilities,
        "chat_template_sha256": (
            hashlib.sha256(template.encode("utf-8")).hexdigest()
            if isinstance(template, str)
            else None
        ),
        "failures": failures,
        "passed": not failures,
    }


def _behavior_tree_digest(project_root):
    """Hash tracked behavior while excluding release-only documentation."""
    project_root = Path(project_root)
    raw = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=str(project_root),
        check=True,
        capture_output=True,
        timeout=20,
    ).stdout
    names = [name for name in raw.split(b"\0") if name]
    digest = hashlib.sha256()
    for encoded in sorted(names):
        try:
            relative = encoded.decode("utf-8")
        except UnicodeError as exc:
            raise F0Error("tracked path is not UTF-8") from exc
        path = Path(relative)
        if path.suffix.casefold() == ".md" or path.parts[:2] == (
            "evidence",
            "f0",
        ):
            continue
        full = project_root / path
        if full.is_symlink():
            content = os.readlink(full).encode("utf-8")
        else:
            content = full.read_bytes()
        if relative == "pyproject.toml":
            content, replacements = re.subn(
                rb'(?m)^version\s*=\s*"[^"]*"\s*$',
                b'version = "<release-metadata>"',
                content,
            )
            if replacements != 1:
                raise F0Error(
                    "pyproject.toml must contain exactly one project version"
                )
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _git_environment(project_root):
    project_root = Path(project_root)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(project_root),
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z"],
        cwd=str(project_root),
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    ).stdout
    return {
        "schema_version": "brick.f0.repository/1",
        "commit": commit,
        "clean": status == "",
        "behavior_tree_sha256": _behavior_tree_digest(project_root),
    }


def _running_model_names(client):
    running = client.get("/api/ps")
    entries = running.get("models") if isinstance(running, dict) else None
    if not isinstance(entries, list):
        raise F0Error("Ollama ps response is malformed")
    names = {
        entry.get("name", entry.get("model"))
        for entry in entries
        if isinstance(entry, dict)
    }
    if None in names or any(not isinstance(name, str) for name in names):
        raise F0Error("Ollama ps contains an unnamed model")
    return sorted(names)


def _loaded_model_summary(ps, model, digest, minimum_context):
    entries = ps.get("models") if isinstance(ps, dict) else None
    if not isinstance(entries, list):
        raise F0Error("Ollama ps response is malformed")
    matches = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and (
            entry.get("name") == model
            or entry.get("model") == model
        )
    ]
    if len(matches) != 1:
        raise F0Error(f"Ollama ps does not show exactly one {model}")
    entry = matches[0]
    if entry.get("digest") != digest:
        raise F0Error(f"Ollama ps digest differs for {model}")
    context = entry.get("context_length")
    if type(context) is not int or context < minimum_context:
        raise F0Error(f"Ollama ps context is below {minimum_context}")
    size = entry.get("size")
    size_vram = entry.get("size_vram")
    if (
        type(size) is not int
        or size <= 0
        or type(size_vram) is not int
        or size_vram < 0
        or size_vram > size
    ):
        raise F0Error(
            f"Ollama ps cannot classify processor placement for {model}"
        )
    if size_vram == 0:
        placement = "cpu"
    elif size_vram == size:
        placement = "accelerator"
    else:
        placement = "mixed"
    return {
        "digest": entry["digest"],
        "context_length": context,
        "size": size,
        "size_vram": size_vram,
        "processor_placement": {
            "classification": placement,
            "source": "Ollama /api/ps size_vram relative to size",
        },
        "details": entry.get("details"),
    }


_RUNNER_IMAGE_TOKENS = ("ollama", "llama")


def _attest_inference_runners(samples, listener_pid):
    """Attest the identity and architecture of the real inference runners.

    F0 v1 only checked that *some* descendant whose image name looked like a
    runner existed. That cannot distinguish a native ARM64 runner from an
    x64 one running under emulation beneath an ARM64 listener, which is the
    exact claim the gate exists to establish. Every observed runner is now
    identified by full path, SHA-256 and PE machine, and its identity must not
    change while one model is probed.
    """
    if not isinstance(samples, list) or not samples:
        return {
            "schema_version": "brick.f0.runner-attestation/1",
            "observed": False,
            "passed": False,
            "runner_set_stable": False,
            "runner_sample_count": 0,
            "runners": [],
            "failure_codes": ["no_process_samples"],
        }
    seen = {}
    sampled_runner_sets = []
    for sample in samples:
        current = set()
        for process in sample.get("processes", []) or []:
            pid = process.get("pid")
            if pid == listener_pid:
                continue
            image = str(process.get("image", "")).casefold()
            if not any(token in image for token in _RUNNER_IMAGE_TOKENS):
                continue
            identity = (
                process.get("parent_pid"),
                process.get("path"),
                process.get("sha256"),
                (process.get("pe_machine") or {}).get("value"),
                (process.get("pe_machine") or {}).get("name"),
            )
            current.add((pid,) + identity)
            seen.setdefault(pid, {"image": image, "identities": []})
            if identity not in seen[pid]["identities"]:
                seen[pid]["identities"].append(identity)
        if current:
            sampled_runner_sets.append(current)
    runners = []
    failure_codes = []
    for pid in sorted(seen):
        entry = seen[pid]
        identities = entry["identities"]
        stable = len(identities) == 1
        (
            parent_pid,
            path,
            sha256,
            machine_value,
            machine_name,
        ) = identities[0]
        native = machine_value == f0_windows.ARM64_PE_MACHINE
        hashed = bool(_DIGEST.fullmatch(str(sha256 or "")))
        runners.append(
            {
                "pid": pid,
                "parent_pid": parent_pid,
                "image": entry["image"],
                "path": path,
                "sha256": sha256,
                "pe_machine": {"value": machine_value, "name": machine_name},
                "identity_stable": stable,
                "native_arm64": native,
                "hashed": hashed,
                "observed_identities": len(identities),
            }
        )
        if not stable:
            failure_codes.append(f"runner_identity_changed:{pid}")
        if not native:
            failure_codes.append(f"runner_not_arm64:{pid}")
        if not hashed:
            failure_codes.append(f"runner_not_hashed:{pid}")
    runner_set_stable = bool(sampled_runner_sets) and all(
        current == sampled_runner_sets[0]
        for current in sampled_runner_sets[1:]
    )
    if sampled_runner_sets and not runner_set_stable:
        failure_codes.append("runner_set_changed")
    if not runners:
        failure_codes.append("no_inference_runner_observed")
    return {
        "schema_version": "brick.f0.runner-attestation/1",
        "observed": bool(runners),
        "passed": bool(runners) and not failure_codes,
        "runner_set_stable": runner_set_stable,
        "runner_sample_count": len(sampled_runner_sets),
        "runners": runners,
        "failure_codes": sorted(set(failure_codes)),
    }


def _probe_one_model(
    client,
    protocol,
    model_spec,
    output_dir,
    listener,
    monitor_factory,
    processor_probe,
):
    model = model_spec["tag"]
    output_dir = Path(output_dir)
    before = _tag_entry(client.get("/api/tags"), model)
    show = client.post("/api/show", {"model": model, "verbose": False})
    _write_json(output_dir / "show.json", show)
    metadata = _metadata_summary(model, before, show)
    _write_json(output_dir / "metadata.json", metadata)
    if not metadata["passed"]:
        raise F0Error("; ".join(metadata["failures"]))

    listener_pid = listener["pid"]
    _write_json(output_dir / "listener.json", listener)
    monitor = monitor_factory(listener_pid)
    monitor.start()
    memory = None
    try:
        option_recognition = run_option_recognition(
            client,
            protocol,
            model,
            before["digest"],
            output_dir / "option-recognition",
        )
        conformance = run_conformance(
            client,
            protocol,
            model,
            before["digest"],
            output_dir / "conformance",
        )
        runtime = run_runtime(
            client,
            protocol,
            model,
            before["digest"],
            output_dir / "runtime",
        )
        ps = client.get("/api/ps")
        _write_json(output_dir / "ps.json", ps)
        loaded = _loaded_model_summary(
            ps,
            model,
            before["digest"],
            protocol["sampling"]["num_ctx"],
        )
        processor_report = processor_probe(listener["path"])
        _write_bytes(
            output_dir / "ollama-ps.txt",
            processor_report.encode("utf-8"),
        )
    finally:
        memory = monitor.stop()
        _write_json(
            output_dir / "runtime" / "memory-summary.json",
            memory,
        )
        try:
            client.unload(model)
        except Exception:
            pass
    after = _tag_entry(client.get("/api/tags"), model)
    digest_stable = after["digest"] == before["digest"]
    minimum_tps = model_spec.get("min_eval_tps")
    throughput_passed = (
        runtime["passed"]
        and (
            minimum_tps is None
            or (
                runtime["median_eval_tps"] is not None
                and runtime["median_eval_tps"] >= minimum_tps
            )
        )
    )
    memory_peak = memory.get("peak_private_commit_bytes")
    expected_listener_image = Path(listener["path"]).name.casefold()
    samples = memory.get("samples")
    listener_identity_passed = (
        isinstance(samples, list)
        and bool(samples)
        and all(
            any(
                process.get("pid") == listener_pid
                and str(process.get("image", "")).casefold()
                == expected_listener_image
                for process in sample.get("processes", [])
            )
            for sample in samples
        )
    )
    runner_attestation = _attest_inference_runners(samples, listener_pid)
    runner_observed = runner_attestation["observed"]
    memory_passed = (
        memory.get("error") is None
        and type(memory_peak) is int
        and memory_peak <= protocol["max_tree_private_commit_bytes"]
        and listener_identity_passed
        and runner_observed
        and runner_attestation["passed"]
    )
    return {
        "schema_version": "brick.f0.model-summary/2",
        "tag": model,
        "role": model_spec["role"],
        "digest": before["digest"],
        "digest_stable": digest_stable,
        "metadata_passed": metadata["passed"],
        "loaded_model": loaded,
        "option_recognition_passed": option_recognition["passed"],
        "option_recognition_failure_codes": option_recognition[
            "failure_codes"
        ],
        "unknown_option_accepted": option_recognition[
            "unknown_option_accepted"
        ],
        "native_tools_passed": conformance["passed"],
        "runtime": runtime,
        "minimum_eval_tps": minimum_tps,
        "throughput_passed": throughput_passed,
        "memory": {
            "peak_private_commit_bytes": memory_peak,
            "maximum_private_commit_bytes": protocol[
                "max_tree_private_commit_bytes"
            ],
            "listener_identity_passed": listener_identity_passed,
            "runner_observed": runner_observed,
            "runner_attestation": runner_attestation,
            "passed": memory_passed,
        },
        "passed": (
            digest_stable
            and metadata["passed"]
            and option_recognition["passed"]
            and conformance["passed"]
            and throughput_passed
            and memory_passed
        ),
    }


def _validate_report_manifest(run_dir, manifest):
    """Validate one prepared report without requiring its commit marker."""
    run_dir = Path(run_dir)
    if manifest.get("schema_version") != PREPARED_SCHEMA:
        raise F0Error("F0 report manifest schema is unsupported")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise F0Error("F0 report manifest has no files")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise F0Error("F0 report member is malformed")
        relative = entry.get("path")
        relative_path = Path(relative) if isinstance(relative, str) else Path()
        if (
            not relative
            or relative_path.is_absolute()
            or ".." in relative_path.parts
            or relative_path.as_posix() != relative
            or relative in seen
        ):
            raise F0Error("F0 report member path is unsafe or duplicated")
        seen.add(relative)
        path = run_dir.joinpath(*relative_path.parts)
        if not path.is_file() or path.is_symlink():
            raise F0Error(f"F0 report member is missing: {relative}")
        if path.stat().st_size != entry.get("size"):
            raise F0Error(f"F0 report member size changed: {relative}")
        if _sha256(path) != entry.get("sha256"):
            raise F0Error(f"F0 report member hash changed: {relative}")
    actual = {
        path.relative_to(run_dir).as_posix()
        for path in run_dir.rglob("*")
        if path.is_file()
        and path.relative_to(run_dir).as_posix()
        not in {"PREPARED.json", "COMMITTED"}
    }
    if actual != seen:
        raise F0Error("F0 report contains unmanifested files")


def _report_json(run_dir, relative):
    try:
        value = json.loads(
            (Path(run_dir) / relative).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise F0Error(f"F0 evidence is unreadable: {relative}") from exc
    if not isinstance(value, dict):
        raise F0Error(f"F0 evidence is not an object: {relative}")
    return value


def _optional_report_json(run_dir, relative):
    path = Path(run_dir) / relative
    if not path.is_file():
        return None
    return _report_json(run_dir, relative)


def _require_evidence(condition, message):
    if not condition:
        raise F0Error("F0 eligibility evidence failed: " + message)


def _pull_log_succeeded(path):
    try:
        lines = [
            line
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        final = json.loads(lines[-1])
    except (IndexError, OSError, UnicodeError, ValueError) as exc:
        raise F0Error(f"F0 pull log is invalid: {path.name}") from exc
    return isinstance(final, dict) and final.get("status") == "success"


def _verify_option_recognition_evidence(
    run_dir, protocol, model, digest
):
    """Recompute option-recognition eligibility from raw requests/responses."""
    run_dir = Path(run_dir)
    slug = _safe_model_slug(model)
    base = Path("models") / slug / "option-recognition"
    summary = _report_json(run_dir, base / "summary.json")
    contract = protocol["option_contract"]

    def raw_case(name, case_id, key=None):
        request = _report_json(run_dir, base / f"{name}-request.json")
        expected = _recognition_payload(protocol, model, digest, case_id)
        if key is not None:
            expected["options"][key] = protocol[
                "recognition_invalid_value"
            ]
        elif name == "unknown-option":
            expected["options"][protocol["unknown_option_sentinel"]] = (
                protocol["recognition_invalid_value"]
            )
        _require_evidence(
            request == expected,
            f"option-recognition request changed for {model}/{name}",
        )
        response = _report_json(run_dir, base / f"{name}-response.json")
        return _recognition_response(
            response,
            key,
            contract[key] if key is not None else None,
        )

    baseline = raw_case(
        "baseline", "recognition-baseline"
    )
    observations = {
        key: raw_case(
            f"option-{key}", f"recognition-{key}", key
        )
        for key in sorted(contract)
    }
    unknown = raw_case("unknown-option", "recognition-unknown")
    health = raw_case("health", "recognition-health")

    option_records = {
        key: {
            "expected_type": contract[key],
            "status_code": observation["status_code"],
            "rejected": not observation["is_success"],
            "http_error": observation["is_http_error"],
            "body_names_key": observation["body_names_key"],
            "body_states_expected_type": observation[
                "body_states_expected_type"
            ],
            "recognized": observation["recognized"],
            "body_text": observation["body_text"],
        }
        for key, observation in observations.items()
    }
    recognized = sorted(
        key for key, item in option_records.items() if item["recognized"]
    )
    unrecognized = sorted(set(contract) - set(recognized))
    rejected = sorted(
        key for key, item in option_records.items() if item["rejected"]
    )
    accepted = sorted(set(contract) - set(rejected))
    error_status = sorted(
        key for key, item in option_records.items() if item["http_error"]
    )
    named = sorted(
        key
        for key, item in option_records.items()
        if item["body_names_key"]
    )
    typed = sorted(
        key
        for key, item in option_records.items()
        if item["body_states_expected_type"]
    )
    passed = (
        baseline["is_success"]
        and health["is_success"]
        and len(recognized) == len(contract)
        and not unrecognized
    )
    failure_codes = []
    if not baseline["is_success"]:
        failure_codes.append("frozen_option_map_rejected")
    if unrecognized:
        failure_codes.append("option_names_not_recognized")
    if len(error_status) != len(contract):
        failure_codes.append("option_error_status_invalid")
    if len(named) != len(contract):
        failure_codes.append("option_error_did_not_name_key")
    if len(typed) != len(contract):
        failure_codes.append("option_error_did_not_state_type")
    if not health["is_success"]:
        failure_codes.append("server_unhealthy_after_probe")

    recorded_options = summary.get("options")
    legacy_option_fields = (
        "expected_type",
        "status_code",
        "rejected",
        "body_names_key",
        "body_states_expected_type",
        "body_text",
    )
    _require_evidence(
        summary.get("schema_version")
        == "brick.f0.option-recognition/2"
        and summary.get("suite") == protocol["recognition_suite"]
        and summary.get("sentinel_option")
        == protocol["unknown_option_sentinel"]
        and summary.get("invalid_value")
        == protocol["recognition_invalid_value"]
        and summary.get("baseline_accepted") == baseline["is_success"]
        and summary.get("baseline_status_code") == baseline["status_code"]
        and summary.get("health_accepted") == health["is_success"]
        and summary.get("health_status_code") == health["status_code"]
        and summary.get("recognized_options") == recognized
        and summary.get("unrecognized_options") == unrecognized
        and summary.get("options_named_in_error") == named
        and isinstance(recorded_options, dict)
        and sorted(recorded_options) == sorted(contract)
        and all(
            all(
                recorded_options[key].get(field)
                == option_records[key][field]
                for field in legacy_option_fields
            )
            for key in sorted(contract)
        )
        and summary.get("unknown_option_status_code")
        == unknown["status_code"]
        and summary.get("unknown_option_accepted") == unknown["is_success"]
        and summary.get("unknown_option_body") == unknown["body_text"]
        and summary.get("passed") == passed
        and summary.get("failure_codes") == failure_codes,
        f"option recognition summary disagrees with raw evidence for {model}",
    )
    optional_derived = {
        "rejected_options": rejected,
        "accepted_options": accepted,
        "options_with_http_error": error_status,
        "options_typed_in_error": typed,
    }
    _require_evidence(
        all(
            field not in summary or summary.get(field) == expected
            for field, expected in optional_derived.items()
        )
        and all(
            all(
                field not in recorded_options[key]
                or recorded_options[key].get(field)
                == option_records[key][field]
                for field in ("http_error", "recognized")
            )
            for key in sorted(contract)
        ),
        f"derived option recognition fields disagree for {model}",
    )
    verified = copy.deepcopy(summary)
    verified.update(optional_derived)
    verified["options"] = option_records
    return verified


def _model_failure_substantiated(model_summary):
    return bool(model_summary.get("error")) or any(
        model_summary.get(field) is False
        for field in (
            "digest_stable",
            "metadata_passed",
            "option_recognition_passed",
            "native_tools_passed",
            "throughput_passed",
        )
    ) or (model_summary.get("memory", {}).get("passed") is False)


def _verify_passing_report(run_dir, summary):
    """Recompute pass eligibility from committed evidence files."""
    run_dir = Path(run_dir)
    protocol = _verify_common_identity(run_dir, summary)
    run = _report_json(run_dir, "run.json")
    repository = _report_json(run_dir, "repository.json")
    _require_evidence(
        run.get("pull_requested") is True,
        "run identity or pull attestation is invalid",
    )
    _require_evidence(
        repository.get("clean") is True,
        "passing F0 evidence requires a clean repository",
    )

    environment = _report_json(run_dir, "environment.json")
    volume = environment.get("volume")
    python = environment.get("python")
    ollama = environment.get("ollama_listener")
    hardware = environment.get("hardware")
    _require_evidence(
        environment.get("schema_version") == "brick.f0.environment/1"
        and environment.get("passed") is True
        and environment.get("failures") == []
        and type(environment.get("windows_build")) is int
        and environment["windows_build"] >= 22000
        and str(environment.get("machine", "")).casefold()
        in {"arm64", "aarch64"}
        and type(environment.get("physical_memory_bytes")) is int
        and environment["physical_memory_bytes"]
        >= protocol["minimum_physical_memory_bytes"]
        and isinstance(volume, dict)
        and str(volume.get("filesystem", "")).casefold() == "ntfs"
        and volume.get("drive_type") == 3
        and type(volume.get("free_bytes")) is int
        and volume["free_bytes"]
        >= protocol["minimum_free_disk_bytes_after_pulls"]
        and environment.get("onedrive_contained") is False
        and isinstance(python, dict)
        and python.get("pe_machine", {}).get("value")
        == f0_windows.ARM64_PE_MACHINE
        and bool(_DIGEST.fullmatch(str(python.get("sha256", ""))))
        and isinstance(ollama, dict)
        and ollama.get("pe_machine", {}).get("value")
        == f0_windows.ARM64_PE_MACHINE
        and bool(_DIGEST.fullmatch(str(ollama.get("sha256", ""))))
        and isinstance(hardware, dict),
        "native Lenovo environment record is incomplete",
    )

    storage = _report_json(run_dir, "storage/summary.json")
    records = storage.get("records")
    _require_evidence(
        storage.get("schema_version") == "brick.f0.storage-summary/1"
        and storage.get("passed") is True
        and storage.get("cycles") == protocol["storage_cycles"]
        and storage.get("forced_exits")
        == protocol["storage_process_exits"]
        and storage.get("held_handle_cycles")
        == protocol["storage_held_handle_cycles"]
        and storage.get("committed") == protocol["storage_cycles"]
        and storage.get("logical_commits") == protocol["storage_cycles"]
        and storage.get("invalid_committed") == 0
        and storage.get("duplicate_valid_candidates") == {}
        and storage.get("directory_renames") == 0
        and isinstance(records, list)
        and len(records) == protocol["storage_cycles"]
        and all(record.get("state") == "committed" for record in records),
        "storage spike attestation is incomplete",
    )

    disk = _report_json(run_dir, "ollama/disk-after-pulls.json")
    _require_evidence(
        disk.get("schema_version") == "brick.f0.disk-after-pulls/1"
        and disk.get("passed") is True
        and disk.get("minimum_free_bytes")
        == protocol["minimum_free_disk_bytes_after_pulls"]
        and type(disk.get("free_bytes")) is int
        and disk["free_bytes"] >= disk["minimum_free_bytes"]
        and summary.get("disk_after_pulls") == disk,
        "post-pull disk record failed",
    )
    version = _report_json(run_dir, "ollama/version.json")
    _require_evidence(
        isinstance(version.get("version"), str)
        and bool(version["version"].strip())
        and summary.get("ollama_version") == version["version"],
        "Ollama version record is invalid",
    )
    tags_before = _report_json(run_dir, "ollama/tags-before.json")
    tags_after = _report_json(run_dir, "ollama/tags-after.json")

    model_summaries = []
    for model_spec in protocol["models"]:
        tag = model_spec["tag"]
        slug = _safe_model_slug(tag)
        relative = f"models/{slug}/summary.json"
        model_summary = _report_json(run_dir, relative)
        _require_evidence(
            model_summary.get("tag") == tag
            and model_summary.get("role") == model_spec["role"]
            and model_summary.get("status")
            == ("eligible" if model_summary.get("passed") else "ineligible"),
            f"model summary identity is invalid for {tag}",
        )
        model_summaries.append(model_summary)
        if not model_summary.get("passed"):
            _require_evidence(
                model_spec["role"] == "descriptive"
                and _model_failure_substantiated(model_summary),
                "a passing report contains an unsubstantiated ineligible model",
            )
            continue

        before = _tag_entry(tags_before, tag)
        after = _tag_entry(tags_after, tag)
        digest = model_summary.get("digest")
        _require_evidence(
            before["digest"] == digest
            and after["digest"] == digest
            and model_summary.get("digest_stable") is True
            and model_summary.get("metadata_passed") is True
            and model_summary.get("option_recognition_passed") is True
            and model_summary.get("native_tools_passed") is True
            and model_summary.get("throughput_passed") is True
            and model_summary.get("memory", {}).get("passed") is True
            and model_summary.get("memory", {}).get(
                "listener_identity_passed"
            )
            is True
            and model_summary.get("memory", {}).get("runner_observed")
            is True
            and model_summary.get("loaded_model", {}).get("digest") == digest
            and model_summary.get("loaded_model", {})
            .get("processor_placement", {})
            .get("classification")
            in {"cpu", "accelerator", "mixed"},
            f"model eligibility fields failed for {tag}",
        )
        pull_log = (
            run_dir / "ollama" / f"pull-{_safe_model_slug(tag)}.jsonl"
        )
        _require_evidence(
            _pull_log_succeeded(pull_log),
            f"model pull did not succeed for {tag}",
        )
        metadata = _report_json(
            run_dir, f"models/{slug}/metadata.json"
        )
        recognition = _verify_option_recognition_evidence(
            run_dir, protocol, tag, digest
        )
        _require_evidence(
            metadata.get("passed") is True
            and metadata.get("digest") == digest
            and metadata.get("tool_capability_advertised") is True
            and recognition.get("passed") is True,
            f"model metadata or option recognition failed for {tag}",
        )
        # Recomputed from the recognition record rather than trusted: every
        # frozen option name must have been individually recognized, and the
        # server must have been healthy before and after the invalid probes.
        contract_keys = sorted(protocol["option_contract"])
        _require_evidence(
            recognition.get("schema_version")
            == "brick.f0.option-recognition/2"
            and recognition.get("suite") == protocol["recognition_suite"]
            and recognition.get("baseline_accepted") is True
            and recognition.get("health_accepted") is True
            and recognition.get("unrecognized_options") == []
            and sorted(recognition.get("recognized_options") or [])
            == contract_keys
            and recognition.get("failure_codes") == []
            and isinstance(recognition.get("options"), dict)
            and sorted(recognition["options"]) == contract_keys
            and all(
                recognition["options"][key].get("rejected") is True
                and recognition["options"][key].get("http_error") is True
                and recognition["options"][key].get("body_names_key") is True
                and recognition["options"][key].get(
                    "body_states_expected_type"
                )
                is True
                and recognition["options"][key].get("recognized") is True
                and recognition["options"][key].get("expected_type")
                == protocol["option_contract"][key]
                for key in contract_keys
            ),
            f"option recognition evidence is incomplete for {tag}",
        )
        recorded_attestation = (
            model_summary.get("memory", {}).get("runner_attestation") or {}
        )
        memory_evidence = _report_json(
            run_dir, f"models/{slug}/runtime/memory-summary.json"
        )
        listener_record = _report_json(
            run_dir, f"models/{slug}/listener.json"
        )
        attestation = _attest_inference_runners(
            memory_evidence.get("samples"),
            listener_record.get("pid"),
        )
        recorded_runners = recorded_attestation.get("runners")
        runners = attestation.get("runners")
        legacy_runner_fields = (
            "pid",
            "image",
            "path",
            "sha256",
            "pe_machine",
            "identity_stable",
            "native_arm64",
            "hashed",
            "observed_identities",
        )
        _require_evidence(
            recorded_attestation.get("schema_version")
            == "brick.f0.runner-attestation/1"
            and recorded_attestation.get("observed")
            == attestation.get("observed")
            and recorded_attestation.get("passed")
            == attestation.get("passed")
            and recorded_attestation.get("failure_codes")
            == attestation.get("failure_codes")
            and isinstance(recorded_runners, list)
            and len(recorded_runners) == len(runners)
            and all(
                all(
                    recorded.get(field) == recomputed.get(field)
                    for field in legacy_runner_fields
                )
                for recorded, recomputed in zip(recorded_runners, runners)
            )
            and (
                "runner_set_stable" not in recorded_attestation
                or recorded_attestation.get("runner_set_stable")
                == attestation.get("runner_set_stable")
            )
            and (
                "runner_sample_count" not in recorded_attestation
                or recorded_attestation.get("runner_sample_count")
                == attestation.get("runner_sample_count")
            )
            and attestation.get("observed") is True
            and attestation.get("passed") is True
            and attestation.get("runner_set_stable") is True
            and type(attestation.get("runner_sample_count")) is int
            and attestation["runner_sample_count"] >= 1
            and attestation.get("failure_codes") == []
            and isinstance(runners, list)
            and bool(runners)
            and all(
                runner.get("native_arm64") is True
                and runner.get("identity_stable") is True
                and runner.get("hashed") is True
                and type(runner.get("pid")) is int
                and type(runner.get("parent_pid")) is int
                and bool(_DIGEST.fullmatch(str(runner.get("sha256", ""))))
                and (runner.get("pe_machine") or {}).get("value")
                == f0_windows.ARM64_PE_MACHINE
                for runner in runners
            ),
            f"inference-runner attestation failed for {tag}",
        )
        for case in (
            "single_typed",
            "tool_selection",
            "result_roundtrip",
        ):
            verdict = _report_json(
                run_dir,
                f"models/{slug}/conformance/{case}/verdict.json",
            )
            _require_evidence(
                verdict.get("passed") is True,
                f"native-tool conformance failed for {tag}/{case}",
            )
        runtime = model_summary.get("runtime")
        _require_evidence(
            isinstance(runtime, dict)
            and runtime.get("passed") is True
            and runtime.get("valid_samples")
            >= protocol["minimum_valid_runtime_samples"]
            and (
                model_spec["min_eval_tps"] is None
                or runtime.get("median_eval_tps")
                >= model_spec["min_eval_tps"]
            ),
            f"runtime evidence failed for {tag}",
        )
        required_runtime = ["warmup"]
        required_runtime.extend(
            f"sample-{index:02d}"
            for index in range(1, protocol["runtime_samples"] + 1)
        )
        for stem in required_runtime:
            for suffix in ("", "-request", "-response"):
                path = run_dir / "models" / slug / "runtime" / (
                    stem + suffix + ".json"
                )
                _require_evidence(
                    path.is_file(),
                    f"runtime raw evidence is missing for {tag}/{stem}{suffix}",
                )
        _require_evidence(
            memory_evidence.get("error") is None
            and type(memory_evidence.get("peak_private_commit_bytes")) is int
            and memory_evidence["peak_private_commit_bytes"]
            <= protocol["max_tree_private_commit_bytes"]
            and type(memory_evidence.get("peak_process_count")) is int
            and memory_evidence["peak_process_count"] >= 2,
            f"process-memory evidence failed for {tag}",
        )
        _require_evidence(
            (run_dir / "models" / slug / "show.json").is_file()
            and (run_dir / "models" / slug / "ps.json").is_file()
            and (run_dir / "models" / slug / "ollama-ps.txt").is_file(),
            f"model metadata artifacts are missing for {tag}",
        )

    expected_codes = _classify_failures(
        environment,
        storage,
        disk,
        model_summaries,
        run.get("pull_requested"),
        repository=repository,
        expected_models=protocol["models"],
        run_failures=summary.get("failures"),
    )
    _require_evidence(
        summary.get("failure_codes") == expected_codes
        and summary.get("failure_domains")
        == sorted({code["domain"] for code in expected_codes}),
        "structured failure codes do not match passing component evidence",
    )

    primary = model_summaries[0]
    _require_evidence(
        primary.get("passed") is True
        and summary.get("primary") == primary
        and summary.get("descriptive_models") == model_summaries[1:]
        and summary.get("environment_status") == "pass"
        and summary.get("storage_status") == "pass"
        and summary.get("failures") == [],
        "summary does not match recomputed eligibility",
    )


def _load_report_manifest(run_dir):
    prepared = Path(run_dir) / "PREPARED.json"
    if prepared.is_symlink() or not prepared.is_file():
        raise F0Error("F0 report manifest is absent or irregular")
    try:
        manifest = json.loads(prepared.read_text(encoding="utf-8"))
    except OSError:
        raise
    except (UnicodeError, ValueError) as exc:
        raise F0Error("F0 report manifest is unreadable") from exc
    if not isinstance(manifest, dict):
        raise F0Error("F0 report manifest is not an object")
    return manifest


def _commit_prepared_report(
    run_dir,
    deadline_seconds=30.0,
    clock=time.monotonic,
    sleeper=time.sleep,
):
    run_dir = Path(run_dir)
    marker = run_dir / "COMMITTED"
    started = clock()
    attempt = 0
    while True:
        try:
            manifest = _load_report_manifest(run_dir)
            _validate_report_manifest(run_dir, manifest)
            try:
                _write_bytes(marker, b"")
            except FileExistsError:
                if (
                    marker.is_symlink()
                    or not marker.is_file()
                    or marker.stat().st_size != 0
                ):
                    raise F0Error(
                        "existing F0 report marker is invalid"
                    )
            # State inspection after marker creation is mandatory.
            committed_manifest = _load_report_manifest(run_dir)
            _validate_report_manifest(run_dir, committed_manifest)
            return committed_manifest
        except OSError as exc:
            if not f0_storage.is_retryable_filesystem_error(exc):
                raise
            if clock() - started >= deadline_seconds:
                raise F0Error(
                    "F0 report publication exceeded its retry deadline"
                ) from exc
            delay = (
                _REPORT_RETRY_DELAYS[attempt]
                if attempt < len(_REPORT_RETRY_DELAYS)
                else 2.0
            )
            attempt += 1
            sleeper(delay)


def _publish_report(run_dir):
    run_dir = Path(run_dir)
    members = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(run_dir).as_posix()
        if relative in {"PREPARED.json", "COMMITTED"}:
            continue
        members.append(
            {
                "path": relative,
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    manifest = {
        "schema_version": PREPARED_SCHEMA,
        "files": members,
    }
    _write_json(run_dir / "PREPARED.json", manifest)
    # Marker-last requires parsing and hashing from disk before visibility.
    return _commit_prepared_report(run_dir)


def verify_report(run_dir):
    run_dir = Path(run_dir)
    marker = run_dir / "COMMITTED"
    if (
        marker.is_symlink()
        or not marker.is_file()
        or marker.stat().st_size != 0
    ):
        raise F0Error("F0 report has no valid COMMITTED marker")
    manifest = _load_report_manifest(run_dir)
    _validate_report_manifest(run_dir, manifest)
    summary = json.loads(
        (run_dir / "summary.json").read_text(encoding="utf-8")
    )
    schema = summary.get("schema_version")
    status = summary.get("overall_status")
    if schema == SUMMARY_SCHEMA:
        if status == "pass":
            _verify_passing_report(run_dir, summary)
        elif status == "fail":
            _verify_failed_report(run_dir, summary)
        else:
            raise F0Error("F0 summary status is unsupported")
    elif schema == LEGACY_SUMMARY_SCHEMA:
        _verify_legacy_report(run_dir, summary)
    else:
        raise F0Error("F0 summary schema is unsupported")
    return summary


def _verify_common_identity(run_dir, summary, validate=True):
    """Recompute the run, protocol and repository identity of any report."""
    run_dir = Path(run_dir)
    protocol = _report_json(run_dir, "protocol.json")
    if validate:
        validate_protocol(protocol)
    protocol_digest = _protocol_hash(protocol)
    try:
        recorded = (run_dir / "protocol.sha256").read_text(
            encoding="ascii"
        ).strip()
    except (OSError, UnicodeError) as exc:
        raise F0Error("F0 protocol digest is unreadable") from exc
    _require_evidence(
        recorded == protocol_digest
        and summary.get("protocol_sha256") == protocol_digest,
        "protocol digest mismatch",
    )
    run = _report_json(run_dir, "run.json")
    _require_evidence(
        run.get("schema_version") == "brick.f0.run/1"
        and run.get("run_id") == summary.get("run_id")
        and run.get("run_id") == run_dir.name,
        "run identity is invalid",
    )
    repository = _report_json(run_dir, "repository.json")
    _require_evidence(
        repository.get("schema_version") == "brick.f0.repository/1"
        and type(repository.get("clean")) is bool
        and isinstance(repository.get("commit"), str)
        and bool(re.fullmatch(r"[0-9a-f]{40,64}", repository["commit"]))
        and bool(
            _DIGEST.fullmatch(
                str(repository.get("behavior_tree_sha256", ""))
            )
        ),
        "repository was not a clean pinned commit",
    )
    return protocol


def _verify_failed_report(run_dir, summary):
    """Semantically verify a *failed* report instead of trusting its status.

    A failed bundle is evidence too: it must be internally consistent, its
    identity must recompute, and every declared failure must be substantiated
    by the underlying per-model records. Without this, a failed run could
    misattribute an instrument fault to a model or hide a fault entirely.
    """
    run_dir = Path(run_dir)
    protocol = _verify_common_identity(run_dir, summary)
    run = _report_json(run_dir, "run.json")
    repository = _report_json(run_dir, "repository.json")
    failures = summary.get("failures")
    _require_evidence(
        isinstance(failures, list) and bool(failures),
        "a failed F0 report must record at least one failure",
    )
    codes = summary.get("failure_codes")
    known_domains = {
        "environment",
        "storage",
        "instrument",
        "protocol_contract",
        "model_runtime",
    }
    _require_evidence(
        isinstance(codes, list)
        and all(
            isinstance(code, dict)
            and code.get("domain") in known_domains
            and isinstance(code.get("code"), str)
            and bool(code["code"])
            for code in codes
        ),
        "a structured failure code is malformed or misattributed",
    )
    for axis in ("environment_status", "storage_status"):
        _require_evidence(
            summary.get(axis) in {"pass", "fail"},
            f"{axis} is not a recognized status",
        )
    environment = _optional_report_json(run_dir, "environment.json")
    _require_evidence(
        (environment is not None and environment.get("passed") is True)
        == (summary.get("environment_status") == "pass"),
        "environment status disagrees with the environment record",
    )
    storage = _optional_report_json(run_dir, "storage/summary.json")
    _require_evidence(
        (storage is not None and storage.get("passed") is True)
        == (summary.get("storage_status") == "pass"),
        "storage status disagrees with the storage record",
    )
    disk = _optional_report_json(
        run_dir, "ollama/disk-after-pulls.json"
    )
    primary = summary.get("primary")
    descriptive = summary.get("descriptive_models")
    _require_evidence(
        primary is None or isinstance(primary, dict),
        "failed report primary model entry is malformed",
    )
    _require_evidence(
        isinstance(descriptive, list),
        "failed report descriptive model list is malformed",
    )
    recorded = ([] if primary is None else [primary]) + descriptive
    by_tag = {}
    for model_summary in recorded:
        tag = model_summary.get("tag") if isinstance(model_summary, dict) else None
        _require_evidence(
            isinstance(tag, str)
            and bool(tag)
            and tag not in by_tag,
            "a recorded model summary has no unique tag",
        )
        by_tag[tag] = model_summary

    expected_tags = {spec["tag"] for spec in protocol["models"]}
    _require_evidence(
        set(by_tag) <= expected_tags,
        "failed report contains an unexpected model",
    )
    on_disk_models = []
    for spec in protocol["models"]:
        tag = spec["tag"]
        relative = (
            Path("models") / _safe_model_slug(tag) / "summary.json"
        )
        on_disk = _optional_report_json(run_dir, relative)
        model_summary = by_tag.get(tag)
        _require_evidence(
            (on_disk is None) == (model_summary is None),
            f"failed report model presence disagrees for {tag}",
        )
        if on_disk is None:
            continue
        _require_evidence(
            on_disk == model_summary
            and on_disk.get("schema_version")
            == "brick.f0.model-summary/2"
            and on_disk.get("tag") == tag
            and on_disk.get("role") == spec["role"],
            f"model summary on disk disagrees with the report for {tag}",
        )
        on_disk_models.append(on_disk)
        expected = "eligible" if model_summary.get("passed") else "ineligible"
        _require_evidence(
            model_summary.get("status") == expected,
            f"model status disagrees with its passed flag for {tag}",
        )
        if not model_summary.get("passed"):
            _require_evidence(
                _model_failure_substantiated(model_summary),
                f"failed model {tag} records no substantiating cause",
            )
        if model_summary.get("option_recognition_passed") in {True, False}:
            recognition = _verify_option_recognition_evidence(
                run_dir,
                protocol,
                tag,
                model_summary.get("digest"),
            )
            _require_evidence(
                recognition.get("passed")
                == model_summary["option_recognition_passed"],
                f"option-recognition status disagrees for {tag}",
            )

    # A late run-level failure can occur after every eligibility component
    # passed. In that case, validate those components through the full passing
    # verifier before attributing the final run failure.
    primary_record = by_tag.get(protocol["primary_model"])
    if (
        repository.get("clean") is True
        and environment is not None
        and environment.get("passed") is True
        and storage is not None
        and storage.get("passed") is True
        and disk is not None
        and disk.get("passed") is True
        and run.get("pull_requested") is True
        and primary_record is not None
        and primary_record.get("passed") is True
        and (run_dir / "ollama" / "tags-after.json").is_file()
    ):
        component_codes = _classify_failures(
            environment,
            storage,
            disk,
            on_disk_models,
            True,
            repository=repository,
            expected_models=protocol["models"],
            run_failures=[],
        )
        component_summary = dict(summary)
        component_summary.update(
            {
                "overall_status": "pass",
                "failures": [],
                "failure_codes": component_codes,
                "failure_domains": sorted(
                    {code["domain"] for code in component_codes}
                ),
            }
        )
        _verify_passing_report(run_dir, component_summary)

    expected_codes = _classify_failures(
        environment,
        storage,
        disk,
        on_disk_models,
        run.get("pull_requested"),
        repository=repository,
        expected_models=protocol["models"],
        run_failures=failures,
    )
    _require_evidence(
        bool(codes) and codes == expected_codes,
        "structured failure codes disagree with component evidence",
    )
    for code in codes:
        evidence = code.get("evidence")
        if evidence:
            evidence_path = run_dir / Path(evidence)
            _require_evidence(
                evidence_path.exists(),
                f"failure evidence path is missing: {evidence}",
            )
    _require_evidence(
        summary.get("failure_domains")
        == sorted({code["domain"] for code in expected_codes}),
        "recorded failure domains disagree with the failure codes",
    )
    if any(not model.get("passed") for model in on_disk_models):
        _require_evidence(
            bool(codes),
            "a failed model produced no structured failure code",
        )


def _verify_legacy_report(run_dir, summary):
    """Verify integrity and identity of a pre-v2 bundle.

    The v1 candidate's failed bundle is immutable retained diagnostic evidence.
    Its protocol predates the option-recognition contract, so it is verified
    for hash integrity, identity and internal status consistency only. It is
    never eligible to support a release.
    """
    run_dir = Path(run_dir)
    _verify_common_identity(run_dir, summary, validate=False)
    protocol = _report_json(run_dir, "protocol.json")
    _require_evidence(
        protocol.get("schema_version") == "brick.f0.protocol/1",
        "legacy verification requires a version-1 protocol record",
    )
    _require_evidence(
        summary.get("overall_status") in {"pass", "fail"},
        "legacy F0 summary status is unsupported",
    )
    _require_evidence(
        summary.get("overall_status") == "fail",
        "a version-1 bundle can never establish a passing gate",
    )


def _classify_failures(
    environment,
    storage,
    disk,
    models,
    pull,
    repository=None,
    expected_models=None,
    run_failures=None,
):
    """Attribute each failure to a domain so causes are never conflated.

    A protocol-contract failure means the pinned runtime does not honour a
    contract Brick declared; a model/runtime failure means the model itself did
    not meet a measured floor. Collapsing the two is how a runner or transport
    fault becomes a false statement about a model.
    """
    codes = []

    def add(domain, code, detail=None, evidence=None):
        entry = {"domain": domain, "code": code}
        if detail:
            entry["detail"] = detail
        if evidence:
            entry["evidence"] = evidence
        codes.append(entry)

    if repository is None and expected_models is not None:
        add("instrument", "repository_not_probed")
    elif repository is not None and not repository.get("clean"):
        add(
            "instrument",
            "repository_not_clean",
            None,
            "repository.json",
        )
    if environment is None:
        add("environment", "environment_not_probed")
    elif not environment.get("passed"):
        for failure in environment.get("failures") or []:
            add("environment", "environment_requirement_failed", failure,
                "environment.json")
    if storage is None:
        add("storage", "storage_spike_not_run")
    elif not storage.get("passed"):
        add("storage", "marker_last_storage_failed", None,
            "storage/summary.json")
    if not pull:
        add("instrument", "model_pull_not_requested")
    if (
        disk is None
        and pull
        and expected_models is not None
        and environment is not None
        and environment.get("passed")
    ):
        add("instrument", "post_pull_disk_not_recorded")
    elif disk is not None and not disk.get("passed"):
        add("instrument", "free_disk_below_minimum", None,
            "ollama/disk-after-pulls.json")
    for model in models or []:
        tag = model.get("tag")
        slug = _safe_model_slug(tag) if isinstance(tag, str) else "unknown"
        base = f"models/{slug}/summary.json"
        if model.get("passed"):
            continue
        if model.get("error"):
            add("instrument", "model_probe_raised", model["error"], base)
        if model.get("unload_error"):
            add("instrument", "model_unload_failed",
                model["unload_error"], base)
        if model.get("option_recognition_passed") is False:
            add(
                "protocol_contract",
                "option_recognition_failed",
                "; ".join(model.get("option_recognition_failure_codes") or [])
                or None,
                f"models/{slug}/option-recognition/summary.json",
            )
        if model.get("native_tools_passed") is False:
            add("protocol_contract", "native_tool_transport_failed", None,
                f"models/{slug}/conformance")
        if model.get("metadata_passed") is False:
            add("instrument", "model_metadata_failed", None,
                f"models/{slug}/metadata.json")
        if model.get("digest_stable") is False:
            add("instrument", "model_digest_changed", None, base)
        if model.get("throughput_passed") is False:
            runtime = model.get("runtime") or {}
            add(
                "model_runtime",
                "throughput_below_floor",
                f"median_eval_tps={runtime.get('median_eval_tps')} "
                f"minimum={model.get('minimum_eval_tps')}",
                f"models/{slug}/runtime",
            )
        memory = model.get("memory") or {}
        if memory.get("passed") is False:
            attestation = memory.get("runner_attestation") or {}
            if attestation.get("failure_codes"):
                add("instrument", "inference_runner_attestation_failed",
                    "; ".join(attestation["failure_codes"]), base)
            elif memory.get("listener_identity_passed") is False:
                add("instrument", "listener_identity_unstable", None, base)
            else:
                add("model_runtime", "process_memory_exceeded_ceiling",
                    f"peak={memory.get('peak_private_commit_bytes')}", base)
    if expected_models is not None:
        recorded_tags = {
            model.get("tag")
            for model in models or []
            if isinstance(model, dict)
        }
        for spec in expected_models:
            if spec["tag"] not in recorded_tags:
                add(
                    "instrument",
                    "model_not_probed",
                    spec["tag"],
                )
    known_messages = {
        "repository worktree is not clean",
        "environment prerequisites failed",
        "F0Error: environment prerequisites failed",
        "marker-last storage spike failed",
        "model pull was not requested",
        "free disk is below the post-pull minimum",
        "primary 4B model feasibility failed",
    }
    if environment is not None:
        known_messages.update(environment.get("failures") or [])
    for failure in run_failures or []:
        if failure not in known_messages:
            add("instrument", "run_exception", str(failure))
    return codes


def run_probe(
    outdir,
    pull=False,
    protocol_path=PROTOCOL_PATH,
    client_factory=OllamaProbeClient,
    environment_probe=f0_windows.collect_environment,
    repository_probe=_git_environment,
    storage_runner=f0_storage.run_spike,
    monitor_factory=f0_windows.ProcessTreeMonitor,
    processor_probe=f0_windows.ollama_ps,
    listener_probe=f0_windows.listener_process,
    run_id=None,
):
    protocol = load_protocol(protocol_path)
    started = _utc_now()
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    run_id = run_id or (
        "f0-"
        + datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        + "-"
        + uuid.uuid4().hex[:8]
    )
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise F0Error("F0 run id is not a safe path component")
    run_dir = outdir / run_id
    run_dir.mkdir(exist_ok=False)
    _write_json(run_dir / "protocol.json", protocol)
    _write_bytes(
        run_dir / "protocol.sha256",
        (_protocol_hash(protocol) + "\n").encode("ascii"),
    )
    _write_json(
        run_dir / "run.json",
        {
            "schema_version": "brick.f0.run/1",
            "run_id": run_id,
            "started_at_utc": started,
            "pull_requested": bool(pull),
        },
    )
    failures = []
    models = []
    environment = None
    repository = None
    storage = None
    disk_after_pulls = None
    version = None
    client = None
    try:
        repository = repository_probe(Path(__file__).resolve().parents[1])
        _write_json(run_dir / "repository.json", repository)
        if not repository.get("clean"):
            failures.append("repository worktree is not clean")
            raise F0Error("repository worktree is not clean")
        environment = environment_probe(
            run_dir,
            protocol["minimum_physical_memory_bytes"],
            protocol["minimum_free_disk_bytes_after_pulls"],
        )
        _write_json(run_dir / "environment.json", environment)
        if not environment.get("passed"):
            failures.extend(environment.get("failures") or [])
            raise F0Error("environment prerequisites failed")

        storage = storage_runner(
            run_dir / "storage" / "spike",
            cycles=protocol["storage_cycles"],
            crash_cycles=protocol["storage_process_exits"],
            held_handle_cycles=protocol["storage_held_handle_cycles"],
        )
        _write_json(run_dir / "storage" / "summary.json", storage)
        if not storage.get("passed"):
            failures.append("marker-last storage spike failed")

        client = client_factory(
            endpoint=OLLAMA_URL,
            timeout=protocol["request_timeout_seconds"],
        )
        version = client.get("/api/version")
        if (
            not isinstance(version, dict)
            or not isinstance(version.get("version"), str)
            or not version["version"].strip()
        ):
            raise F0Error("Ollama version response is malformed")
        _write_json(run_dir / "ollama" / "version.json", version)
        configured = [item["tag"] for item in protocol["models"]]
        for model in configured:
            try:
                client.unload(model)
            except Exception:
                pass
        running = _running_model_names(client)
        if running:
            raise F0Error(
                "Ollama models remain loaded before probing: "
                + ", ".join(running)
            )

        ordered = sorted(
            protocol["models"],
            key=lambda item: 0 if item["role"] == "primary" else 1,
        )
        pull_errors = {}
        if pull:
            for spec in ordered:
                try:
                    client.pull(
                        spec["tag"],
                        run_dir
                        / "ollama"
                        / ("pull-" + _safe_model_slug(spec["tag"]) + ".jsonl"),
                    )
                except Exception as exc:
                    pull_errors[spec["tag"]] = (
                        f"{type(exc).__name__}: {exc}"
                    )
        else:
            failures.append("model pull was not requested")
        tags = client.get("/api/tags")
        _write_json(run_dir / "ollama" / "tags-before.json", tags)
        free_after = shutil.disk_usage(str(run_dir)).free
        disk_after_pulls = {
            "schema_version": "brick.f0.disk-after-pulls/1",
            "free_bytes": free_after,
            "minimum_free_bytes": protocol[
                "minimum_free_disk_bytes_after_pulls"
            ],
            "passed": (
                free_after
                >= protocol["minimum_free_disk_bytes_after_pulls"]
            ),
        }
        _write_json(
            run_dir / "ollama" / "disk-after-pulls.json",
            disk_after_pulls,
        )
        if not disk_after_pulls["passed"]:
            failures.append("free disk is below the post-pull minimum")

        expected_listener = environment["ollama_listener"]
        primary_failed = False
        for spec in ordered:
            if spec["tag"] in pull_errors:
                result = {
                    "schema_version": "brick.f0.model-summary/2",
                    "tag": spec["tag"],
                    "role": spec["role"],
                    "passed": False,
                    "error": pull_errors[spec["tag"]],
                }
            elif primary_failed:
                result = {
                    "schema_version": "brick.f0.model-summary/2",
                    "tag": spec["tag"],
                    "role": spec["role"],
                    "passed": False,
                    "error": "not run because the primary model failed",
                }
            else:
                try:
                    current_listener = listener_probe()
                    listener_path = str(current_listener.get("path", ""))
                    listener_identity = {
                        "pid": current_listener.get("pid"),
                        "path": listener_path,
                        "sha256": (
                            current_listener.get("sha256")
                            or f0_windows.sha256_file(listener_path)
                        ),
                        "pe_machine": (
                            current_listener.get("pe_machine")
                            or f0_windows.pe_machine(listener_path)
                        ),
                    }
                    if (
                        listener_identity["pid"]
                        != expected_listener["pid"]
                        or os.path.normcase(
                            os.path.realpath(listener_identity["path"])
                        )
                        != os.path.normcase(
                            os.path.realpath(expected_listener["path"])
                        )
                        or listener_identity["sha256"]
                        != expected_listener["sha256"]
                        or listener_identity["pe_machine"]["value"]
                        != f0_windows.ARM64_PE_MACHINE
                    ):
                        raise F0Error(
                            "Ollama listener identity changed before model probe"
                        )
                    result = _probe_one_model(
                        client,
                        protocol,
                        spec,
                        run_dir / "models" / _safe_model_slug(spec["tag"]),
                        listener_identity,
                        monitor_factory,
                        processor_probe,
                    )
                except Exception as exc:
                    result = {
                        "schema_version": "brick.f0.model-summary/2",
                        "tag": spec["tag"],
                        "role": spec["role"],
                        "passed": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
            try:
                still_loaded = _running_model_names(client)
            except Exception as exc:
                still_loaded = []
                result["passed"] = False
                result["unload_error"] = (
                    f"{type(exc).__name__}: {exc}"
                )
            if still_loaded:
                result["passed"] = False
                result["unload_error"] = (
                    "models remain loaded after probe: "
                    + ", ".join(still_loaded)
                )
            result["status"] = (
                "eligible" if result["passed"] else "ineligible"
            )
            _write_json(
                run_dir
                / "models"
                / _safe_model_slug(spec["tag"])
                / "summary.json",
                result,
            )
            models.append(result)
            if spec["role"] == "primary" and not result["passed"]:
                primary_failed = True
                failures.append("primary 4B model feasibility failed")
        tags_after = client.get("/api/tags")
        _write_json(run_dir / "ollama" / "tags-after.json", tags_after)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        if message not in failures:
            failures.append(message)

    primary = next(
        (
            model
            for model in models
            if model.get("role") == "primary"
        ),
        None,
    )
    failure_codes = _classify_failures(
        environment,
        storage,
        disk_after_pulls,
        models,
        pull,
        repository=repository,
        expected_models=protocol["models"],
        run_failures=failures,
    )
    overall = bool(
        environment
        and environment.get("passed")
        and repository
        and repository.get("clean")
        and storage
        and storage.get("passed")
        and primary
        and primary.get("passed")
        and pull
        and disk_after_pulls
        and disk_after_pulls.get("passed")
        and not failures
    )
    summary = {
        "schema_version": SUMMARY_SCHEMA,
        "run_id": run_id,
        "protocol_sha256": _protocol_hash(protocol),
        "started_at_utc": started,
        "finished_at_utc": _utc_now(),
        "overall_status": "pass" if overall else "fail",
        "environment_status": (
            "pass" if environment and environment.get("passed") else "fail"
        ),
        "storage_status": (
            "pass" if storage and storage.get("passed") else "fail"
        ),
        "disk_after_pulls": disk_after_pulls,
        "ollama_version": (
            version.get("version") if isinstance(version, dict) else None
        ),
        "primary": primary,
        "descriptive_models": [
            model for model in models if model.get("role") == "descriptive"
        ],
        "failures": failures,
        "failure_codes": failure_codes,
        "failure_domains": sorted({code["domain"] for code in failure_codes}),
    }
    _write_json(run_dir / "summary.json", summary)
    _publish_report(run_dir)
    verify_report(run_dir)
    return run_dir, summary


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run or verify the native Windows ARM64 F0 feasibility gate."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--outdir", required=True)
    run.add_argument("--pull", action="store_true")
    verify = commands.add_parser("verify")
    verify.add_argument("run_dir")
    commands.add_parser(
        "fingerprint",
        help="print the current clean-commit and behavior-tree identity",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    if args.command == "verify":
        summary = verify_report(args.run_dir)
        print(
            json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True)
        )
        return 0 if summary.get("overall_status") == "pass" else 1
    if args.command == "fingerprint":
        repository = _git_environment(
            Path(__file__).resolve().parents[1]
        )
        print(
            json.dumps(
                repository,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0 if repository["clean"] else 1
    run_dir, summary = run_probe(args.outdir, pull=args.pull)
    print(
        f"F0 {summary['overall_status'].upper()} run={run_dir}",
        flush=True,
    )
    return 0 if summary["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
