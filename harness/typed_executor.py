"""The typed tool contract and its fail-closed executor (S1R).

This is where the other S1R pieces compose into one path. A call is admitted
only after every gate agrees, and each gate answers a different question:

1. **Is the tool known?** An unknown name is a model fault.
2. **Alias repair** -- explicit table only, never inference, and never a global
   alias on a mutating argument (``harness.parsing``).
3. **Schema validation** -- types, ranges, formats, nested shape, no unknown
   properties (``harness.schema``).
4. **Semantic invariants** -- deterministic cross-field rules that JSON Schema
   cannot express: an end after its start, a due date not already past, a
   quantity consistent with a mode. Structural validity is not semantic
   validity, and a structurally perfect call can still be nonsense.
5. **Execution** -- every escaping exception is classified by origin
   (``harness.faults``) instead of being handed to the model.

The ordering matters. Semantic invariants run only after the schema passes, so
an invariant never has to defend itself against a missing key or a string where
a number belongs; it can assume shape and check meaning. Invariants are
therefore allowed to be simple, which is what makes them reliable.

The failure asymmetry is the point of the whole module. A model fault produces a
message and costs a turn. A runner or environment fault aborts and is never
shown to the model, because the released executor did show them, and a model
retrying a disk-full error burns the opportunity budget on something it cannot
fix -- then loses the attempt in a way a grader may score as a genuine model
failure.

The registry holds no domain knowledge. A domain pack supplies schemas,
invariant callables and executors; the core supplies the ordering and the
failure semantics.
"""

import copy
from collections.abc import Mapping

from harness import faults, parsing, schema as schema_module


EXECUTOR_VERSION = "brick.typed-executor/1"


class ContractError(ValueError):
    """A tool contract is malformed. A developer defect."""


class ToolContract:
    """One tool: its schema, its semantics, and whether it mutates state."""

    __slots__ = ("name", "description", "schema", "executor", "mutating",
                 "invariants")

    def __init__(self, name, description, schema, executor, mutating=False,
                 invariants=()):
        if not isinstance(name, str) or not name:
            raise ContractError("tool name must be a nonempty string")
        if not isinstance(description, str) or not description:
            raise ContractError(
                "tool {!r} needs a nonempty description".format(name)
            )
        schema_module.validate_schema(schema)
        if schema["type"] != "object":
            raise ContractError(
                "tool {!r} argument schema must be an object".format(name)
            )
        if not callable(executor):
            raise ContractError("tool {!r} executor must be callable".format(name))
        if type(mutating) is not bool:
            raise ContractError("tool {!r} mutating must be a bool".format(name))
        for invariant in invariants:
            if not callable(invariant):
                raise ContractError(
                    "tool {!r} invariants must be callables".format(name)
                )
        self.name = name
        self.description = description
        self.schema = schema
        self.executor = executor
        self.mutating = mutating
        self.invariants = tuple(invariants)

    @property
    def parameter_names(self):
        return set(self.schema.get("properties", {}))

    def native_schema(self):
        return schema_module.to_ollama_function(
            self.name, self.description, self.schema
        )

    def prompt_doc(self):
        return schema_module.to_prompt_doc(
            self.name, self.description, self.schema
        )


class ExecutionOutcome:
    """What happened, on which axis, and what the model may be told."""

    __slots__ = ("status", "observation", "problems", "fault", "result",
                 "repairs")

    OK = "ok"
    REJECTED = "rejected"          # model fault: invalid call, attempt continues
    FAILED = "failed"              # non-model fault: attempt aborts

    def __init__(self, status, observation=None, problems=(), fault=None,
                 result=None, repairs=()):
        self.status = status
        self.observation = observation
        self.problems = tuple(problems)
        self.fault = fault
        self.result = result
        self.repairs = tuple(repairs)

    @property
    def ok(self):
        return self.status == self.OK

    @property
    def aborts_attempt(self):
        """Only a non-model fault ends the attempt."""
        return self.status == self.FAILED

    def as_record(self):
        return {
            "schema_version": EXECUTOR_VERSION,
            "status": self.status,
            "problems": list(self.problems),
            "repairs": list(self.repairs),
            "fault": self.fault.as_record() if self.fault else None,
        }

    def __repr__(self):
        return "ExecutionOutcome({!r})".format(self.status)


def _rejection_text(name, problems):
    lines = ["ERROR: call to {!r} was rejected:".format(name)]
    lines.extend("  - {}".format(problem) for problem in problems)
    return "\n".join(lines)


class TypedToolRegistry:
    """An ordered registry of typed contracts with a fail-closed executor."""

    def __init__(self, contracts=(), alias_table=None):
        self._contracts = {}
        for contract in contracts:
            self.register(contract)
        self.alias_table = parsing.validate_alias_table(alias_table or {})

    def register(self, contract):
        if not isinstance(contract, ToolContract):
            raise ContractError("expected a ToolContract")
        if contract.name in self._contracts:
            raise ContractError(
                "tool {!r} is already registered".format(contract.name)
            )
        self._contracts[contract.name] = contract
        return self

    def __contains__(self, name):
        return name in self._contracts

    def __len__(self):
        return len(self._contracts)

    def names(self):
        return list(self._contracts)

    def get(self, name):
        return self._contracts.get(name)

    def native_schemas(self):
        """Derived native tool schemas, in registration order."""
        return [c.native_schema() for c in self._contracts.values()]

    def prompt_docs(self):
        return "\n".join(c.prompt_doc() for c in self._contracts.values())

    def invoke(self, name, args, context=None):
        """Run one call through every gate. Never raises for a tool failure."""
        contract = self._contracts.get(name)
        if contract is None:
            known = ", ".join(sorted(self._contracts)) or "none"
            problem = "unknown tool {!r} (known: {})".format(name, known)
            return ExecutionOutcome(
                ExecutionOutcome.REJECTED,
                observation=_rejection_text(name, [problem]),
                problems=[problem],
                fault=faults.classify(faults.ModelInputFault(problem)),
            )

        repaired, repairs, problems = parsing.apply_aliases(
            name, args, self.alias_table, contract.parameter_names,
            mutating=contract.mutating,
        )
        if problems:
            return ExecutionOutcome(
                ExecutionOutcome.REJECTED,
                observation=_rejection_text(name, problems),
                problems=problems,
                fault=faults.classify(faults.ModelInputFault(problems[0])),
                repairs=repairs,
            )

        problems = schema_module.validate_value(
            contract.schema, repaired, "args"
        )
        if problems:
            return ExecutionOutcome(
                ExecutionOutcome.REJECTED,
                observation=_rejection_text(name, problems),
                problems=problems,
                fault=faults.classify(faults.ModelInputFault(problems[0])),
                repairs=repairs,
            )

        # Semantic invariants run only once the shape is known good, so they may
        # assume the schema held and check meaning rather than structure.
        semantic, fault = self._check_invariants(contract, repaired)
        if fault is not None:
            return ExecutionOutcome(
                ExecutionOutcome.FAILED, fault=fault, repairs=repairs
            )
        if semantic:
            return ExecutionOutcome(
                ExecutionOutcome.REJECTED,
                observation=_rejection_text(name, semantic),
                problems=semantic,
                fault=faults.classify(faults.ModelInputFault(semantic[0])),
                repairs=repairs,
            )

        try:
            result = contract.executor(context, copy.deepcopy(repaired))
        except Exception as exc:  # noqa: BLE001 - classified, never swallowed
            classification = faults.classify(exc)
            if classification.is_model_fault:
                message = faults.observation_for(classification)
                return ExecutionOutcome(
                    ExecutionOutcome.REJECTED,
                    observation=message,
                    problems=[classification.message],
                    fault=classification,
                    repairs=repairs,
                )
            # A runner or environment fault aborts and is never described to
            # the model as though it were something the model did.
            return ExecutionOutcome(
                ExecutionOutcome.FAILED,
                fault=classification,
                repairs=repairs,
            )
        return ExecutionOutcome(
            ExecutionOutcome.OK, result=result, repairs=repairs
        )

    def _check_invariants(self, contract, args):
        """Run deterministic invariants. Returns ``(problems, fault)``.

        A raising invariant is our defect, not the model's, so it becomes a
        runner fault rather than a rejection the model would try to fix.
        """
        collected = []
        for invariant in contract.invariants:
            try:
                reported = invariant(args)
            except Exception as exc:  # noqa: BLE001
                return [], faults.classify(
                    faults.RunnerFault(
                        "invariant for {!r} raised {}: {}".format(
                            contract.name, type(exc).__name__, exc
                        )
                    )
                )
            if reported is None:
                continue
            if isinstance(reported, str):
                collected.append(reported)
                continue
            if isinstance(reported, Mapping) or not hasattr(
                reported, "__iter__"
            ):
                return [], faults.classify(
                    faults.RunnerFault(
                        "invariant for {!r} returned {!r}".format(
                            contract.name, type(reported).__name__
                        )
                    )
                )
            for problem in reported:
                if not isinstance(problem, str) or not problem:
                    return [], faults.classify(
                        faults.RunnerFault(
                            "invariant for {!r} returned a non-string "
                            "problem".format(contract.name)
                        )
                    )
                collected.append(problem)
        return collected, None
