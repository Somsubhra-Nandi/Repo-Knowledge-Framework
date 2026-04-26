"""Call graph resolution utilities."""

from dataclasses import dataclass


@dataclass
class ResolvedCall:
    callee_fqn: str
    confidence: float
    resolved: bool
    line: int


class CallResolver:
    """
    Resolves raw callee names from CallInfo into fully-qualified FQNs.

    Resolution strategy (try each in order, stop at first match):
    1. Exact FQN match
    2. Suffix match
    3. Attribute chain match with receiver stripping
    4. Import-resolved match
    5. Unresolved fallback
    """

    def __init__(self, known_fqns: set[str], import_map: dict[str, str]) -> None:
        self._known_fqns = known_fqns
        self._import_map = import_map

    def _suffix_candidates(self, name: str) -> list[str]:
        suffix = f".{name}"
        return [fqn for fqn in self._known_fqns if fqn.endswith(suffix)]

    def _build_from_candidates(self, candidates: list[str], line: int) -> ResolvedCall | None:
        if not candidates:
            return None
        if len(candidates) == 1:
            return ResolvedCall(callee_fqn=candidates[0], confidence=1.0, resolved=True, line=line)
        return ResolvedCall(callee_fqn=candidates[0], confidence=0.7, resolved=True, line=line)

    def resolve(self, callee_name: str, line: int) -> ResolvedCall:
        """Resolve a single raw callee name to a ResolvedCall."""
        if callee_name in self._known_fqns:
            return ResolvedCall(callee_fqn=callee_name, confidence=1.0, resolved=True, line=line)

        suffix_match = self._build_from_candidates(self._suffix_candidates(callee_name), line)
        if suffix_match is not None:
            return suffix_match

        if "." in callee_name:
            parts = callee_name.split(".")
            if len(parts) >= 2:
                stripped = ".".join(parts[1:])
                stripped_candidates = self._suffix_candidates(stripped)
                if stripped_candidates:
                    return ResolvedCall(
                        callee_fqn=stripped_candidates[0],
                        confidence=0.9,
                        resolved=True,
                        line=line,
                    )

                receiver = parts[0]
                if receiver in self._import_map:
                    return ResolvedCall(
                        callee_fqn=callee_name,
                        confidence=0.7,
                        resolved=True,
                        line=line,
                    )

        return ResolvedCall(
            callee_fqn=f"unresolved.{callee_name}",
            confidence=0.2,
            resolved=False,
            line=line,
        )
