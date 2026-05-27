🔹 1. PEP 695 — New generics syntax (Python 3.13+)

Use inline type parameters instead of TypeVar + Generic.

    Use class X[T]: instead of class X(Generic[T]):

    Use def fn[T](x: T) -> T: instead of TypeVar‑based generics

    Type parameters are declared inline, not separately

    Prefer built‑in generics over typing equivalents

Example:
python

class TypedConsumer[T]:
    def consume(self, event: T): ...

🔹 2. PEP 649 — Deferred annotation evaluation (Python 3.14+)

Annotations are lazily evaluated at runtime.

    Do NOT use from __future__ import annotations

    Do NOT quote forward references

    Annotations are stored as expressions, not strings

    Forward references resolve automatically

    No need for string hacks in type hints

Example:
python

def handle(e: ExecutionRequestEvent) -> TypedConsumer[ExecutionRequestEvent]:
    ...

🔹 3. Built‑in generics everywhere (Python 3.12 → 3.14)

Prefer built‑in types over typing module.

    Use list[int], dict[str, Any], tuple[int, ...]

    Avoid typing.List, typing.Dict, typing.Tuple

    Use type[T] instead of typing.Type[T]

🔹 4. TypedDict improvements

    TypedDict now supports NotRequired and Required

    Use dict[str, X] when structure is not strict

    Prefer dataclass or PEP 695 generics for structured data

🔹 5. typing cleanup & deprecations

    typing aliases for built‑ins are deprecated

    typing runtime behavior is more consistent

    typing.get_type_hints() now uses PEP 649 lazy evaluation

🔹 6. Pattern matching typing improvements

    match/case now integrates better with type checkers

    Structural pattern matching supports more precise narrowing

🔹 7. Better error messages for typing

    Python 3.13+ produces clearer errors for generics

    Type parameter misuse is detected earlier

    Invalid generic instantiation errors are more explicit

🔹 8. No syntax changes to using generics

Your usage stays the same:
python

consumer: TypedConsumer[ExecutionRequestEvent]

Only definitions changed (PEP 695), not usage.
🔹 9. LLM‑ready migration rules (copy/paste block)

“Use PEP 695 generics (class X[T]:).
Avoid Generic and TypeVar unless needed for compatibility.
Use built‑in generics (list[int], dict[str, T]).
Do not quote type hints; Python 3.14 uses PEP 649 lazy evaluation.
Remove from __future__ import annotations.
Forward references resolve automatically.
Keep using X[Y] syntax for type application.
Prefer modern typing constructs over deprecated typing aliases.”
