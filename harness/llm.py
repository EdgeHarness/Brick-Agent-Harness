"""Thin Ollama chat client with per-episode usage accounting."""
import json
import time

import requests

OLLAMA_URL = "http://127.0.0.1:11434"


class ModelNotInstalled(RuntimeError):
    """The model a run is configured for is not on this machine.

    Worth its own type and its own message because the alternative is what it
    replaced: a bare `404 Client Error: Not Found for url: /api/chat` several
    seconds into the run, which names neither the model nor the fix.
    """

    def __init__(self, tag, installed):
        self.tag = tag
        self.installed = sorted(installed or ())
        have = ", ".join(self.installed) if self.installed else "nothing"
        super().__init__(
            f"{tag} is not installed. This machine has: {have}. "
            f"Run `ollama pull {tag}`, or point the agent at an installed "
            f"model with --model."
        )


def installed_models(timeout=1.5):
    """Best-effort GET /api/tags, returning the installed tag set.

    Returns None if the installed set could not be determined (connection
    error, timeout, non-200, or a body that doesn't parse as expected).
    Never raises: a check that can crash the run is worse than the problem
    it exists to prevent. Unknown is not the same as missing, so callers
    should treat None as "proceed as if nothing is confirmed absent".
    """
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return {m["name"] for m in data["models"]}
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def model_installed(tag, installed):
    """Whether `tag` is present in `installed`.

    Ollama reports a bare tag like "llama3.2" as "llama3.2:latest", so a
    config tag with no ":" suffix is checked against the ":latest" form too.
    """
    if tag in installed:
        return True
    if ":" not in tag:
        return f"{tag}:latest" in installed
    return False

# Optional per-client observation hook for live watchers:
#   ("start", {"model", "role"})                     before the request goes out
#   ("token", {"text"})                              per streamed chunk
#   ("end",   {"model", "role", "output_tokens", "ms"})
# While a hook is installed the reply is streamed so a watcher can see it
# being written.  Keeping it on the LLM instance prevents concurrent attempts
# in the same process from intercepting one another's output.


class LLM:
    def __init__(self, model, num_ctx=8192, temperature=0.0, timeout=900,
                 keep_alive="30m", stream_hook=None, retries=0):
        if stream_hook is not None and not callable(stream_hook):
            raise TypeError("stream_hook must be callable or None")
        if type(retries) is not int or retries < 0:
            raise ValueError("retries must be a nonnegative integer")
        self.model = model
        self.num_ctx = num_ctx
        self.temperature = temperature
        self.timeout = timeout
        self.keep_alive = keep_alive  # "0" evicts the model right after the call
        self.stream_hook = stream_hook
        # Transport-level retries with backoff. Default 0 so the benchmark's
        # recorded behavior is byte-identical; interactive callers opt in.
        # Retried: connection failures, timeouts, and 5xx (a local Ollama
        # under memory pressure returns 500s that clear on their own).
        # Never retried: 4xx, or a response that parses but is malformed -
        # those reproduce identically.
        self.retries = retries
        self.reset_usage()

    def reset_usage(self):
        self.calls = 0
        self.prompt_tokens = 0
        self.output_tokens = 0
        self.wall = 0.0

    def chat(self, messages, force_json=False, num_predict=700, role=None,
             keep_alive=None):
        # role is accepted so a plain LLM is drop-in interchangeable with the
        # tiered ModelRouter (which selects a model from it); here it only
        # labels the stream events.
        hook = self.stream_hook
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": bool(hook),
            "keep_alive": keep_alive or self.keep_alive,
            "options": {
                "temperature": self.temperature,
                "seed": 42,
                "num_ctx": self.num_ctx,
                "num_predict": num_predict,
            },
        }
        if force_json:
            payload["format"] = "json"
        if hook:
            hook("start", {"model": self.model, "role": role})
        t0 = time.time()
        content, data = self._attempt_with_retries(payload, hook)
        self.calls += 1
        self.wall += time.time() - t0
        self.prompt_tokens += data.get("prompt_eval_count", 0)
        self.output_tokens += data.get("eval_count", 0)
        if hook:
            hook("end", {"model": self.model, "role": role,
                         "output_tokens": data.get("eval_count", 0),
                         "ms": int((time.time() - t0) * 1000)})
        return content

    def _attempt_with_retries(self, payload, hook):
        attempt = 0
        while True:
            try:
                return self._attempt(payload, hook)
            except (requests.ConnectionError, requests.Timeout,
                    requests.HTTPError) as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                transient = status is None or status >= 500
                # A stream that already emitted tokens is not retried: the
                # viewer would see the reply twice.
                if getattr(e, "streamed_partial", False) \
                        or not transient or attempt >= self.retries:
                    raise
                attempt += 1
                time.sleep(min(0.5 * (2 ** (attempt - 1)), 4.0))

    def _attempt(self, payload, hook):
        if hook:
            return self._chat_streamed(payload, hook)
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        return data["message"]["content"], data

    def _chat_streamed(self, payload, hook):
        """Same request with stream=True: hand each chunk to the hook and
        return the joined reply plus the final chunk (which carries usage)."""
        parts, final = [], {}
        try:
            with requests.post(f"{OLLAMA_URL}/api/chat", json=payload,
                               timeout=self.timeout, stream=True) as r:
                r.raise_for_status()
                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    chunk = json.loads(line)
                    piece = chunk.get("message", {}).get("content", "")
                    if piece:
                        parts.append(piece)
                        hook("token", {"text": piece})
                    if chunk.get("done"):
                        final = chunk
        except (requests.ConnectionError, requests.Timeout,
                requests.HTTPError) as e:
            e.streamed_partial = bool(parts)
            raise
        return "".join(parts), final
