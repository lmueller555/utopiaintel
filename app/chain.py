"""Build maximum-hit province assignments for a kingdom chain."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Province:
    name: str
    strength: int
    networth: int


def plan_chain(attackers: list[Province], targets: list[Province]):
    """Return a maximum cardinality, deterministic attacker-to-target matching.

    Each attacker and target can appear at most once. An attack is possible when
    the attacker's offense meets the target's defense and the target is within
    90–110% of the attacker's networth.
    """
    eligible = {
        attacker_index: [
            target_index
            for target_index, target in enumerate(targets)
            if attacker.strength >= target.strength
            and attacker.networth * 9 <= target.networth * 10
            and target.networth * 10 <= attacker.networth * 11
        ]
        for attacker_index, attacker in enumerate(attackers)
    }
    for attacker_index, choices in eligible.items():
        choices.sort(
            key=lambda target_index: (
                attackers[attacker_index].strength - targets[target_index].strength,
                abs(attackers[attacker_index].networth - targets[target_index].networth),
                targets[target_index].name.casefold(),
            )
        )

    target_to_attacker: dict[int, int] = {}

    def assign(attacker_index: int, seen: set[int]) -> bool:
        for target_index in eligible[attacker_index]:
            if target_index in seen:
                continue
            seen.add(target_index)
            current = target_to_attacker.get(target_index)
            if current is None or assign(current, seen):
                target_to_attacker[target_index] = attacker_index
                return True
        return False

    # Constrained attackers go first; this also makes the resulting plan stable.
    for attacker_index in sorted(
        range(len(attackers)),
        key=lambda index: (
            len(eligible[index]),
            attackers[index].strength,
            attackers[index].name.casefold(),
        ),
    ):
        assign(attacker_index, set())

    attacker_to_target = {
        attacker_index: target_index
        for target_index, attacker_index in target_to_attacker.items()
    }
    return [
        (attacker, targets[attacker_to_target[index]] if index in attacker_to_target else None)
        for index, attacker in enumerate(attackers)
    ]


def parse_provinces(value: str, strength_label: str) -> list[Province]:
    """Parse one ``name, strength, networth`` province per line."""
    provinces = []
    for line_number, raw_line in enumerate(value.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.rsplit(",", 2)]
        if len(parts) != 3 or not parts[0]:
            raise ValueError(
                f"Line {line_number} must be: province name, {strength_label}, networth."
            )
        try:
            strength = int(parts[1].replace(",", ""))
            networth = int(parts[2].replace(",", ""))
        except ValueError as exc:
            raise ValueError(
                f"Line {line_number} has an invalid {strength_label} or networth."
            ) from exc
        if strength < 0 or networth <= 0:
            raise ValueError(
                f"Line {line_number} requires non-negative {strength_label} and positive networth."
            )
        provinces.append(Province(parts[0], strength, networth))
    return provinces
