from __future__ import annotations

from typing import Callable, List, Sequence, Tuple

from eval1.layer1.faq_step_context import faq_path_desc_tag, infer_faq_step_knowledge
from eval1.layer1.path_probe import is_probe_node

PathItem = Tuple[List[str], List[str], int, str, float]

_INTERRUPT = frozenset({"FAQ_NORMAL", "FAQ_OOB", "OBJECTION", "F3_RETAIN", "OBJ_FINAL"})

# Re-export for tests; canonical source is PathPlanConfig via infer_path_plan_config().
def _linear_faq_steps() -> tuple[str, ...]:
    return ("F2", "F3", "F4")


def _linear_oob_steps() -> tuple[str, ...]:
    return _linear_faq_steps()


FAQ_ATTACH_STEPS = _linear_faq_steps()
OOB_ATTACH_STEPS = _linear_oob_steps()


def _path_key(path: Sequence[str]) -> tuple:
    return tuple(path)


def _is_mainline(path: Sequence[str]) -> bool:
    return not any(n in _INTERRUPT or is_probe_node(n) for n in path)


def _faq_anchor_step(path: Sequence[str]) -> str:
    if "FAQ_NORMAL" not in path:
        return ""
    idx = path.index("FAQ_NORMAL")
    for n in reversed(path[:idx]):
        if n.startswith("F") and n[1:].isdigit():
            return str(n)
    return ""


def _oob_anchor_step(path: Sequence[str]) -> str:
    if "FAQ_OOB" not in path:
        return ""
    idx = path.index("FAQ_OOB")
    for n in reversed(path[:idx]):
        if n.startswith("F") and n[1:].isdigit():
            return str(n)
    return ""


def _has_pure_faq_after(path: Sequence[str], flow_step: str) -> bool:
    if "FAQ_NORMAL" not in path or "FAQ_OOB" in path or "F3_RETAIN" in path or "OBJ_FINAL" in path:
        return False
    return _faq_anchor_step(path) == flow_step


def _has_pure_oob_after(path: Sequence[str], flow_step: str) -> bool:
    if "FAQ_OOB" not in path or "FAQ_NORMAL" in path or "F3_RETAIN" in path or "OBJ_FINAL" in path:
        return False
    return _oob_anchor_step(path) == flow_step


def _has_retain_then_continue(path: Sequence[str]) -> bool:
    return (
        "F3_RETAIN" in path
        and "F4" in path
        and "OBJ_FINAL" not in path
        and "FAQ_OOB" not in path
        and "FAQ_NORMAL" not in path
    )


def _has_faq_then_retain_continue(path: Sequence[str]) -> bool:
    return "FAQ_NORMAL" in path and "F3_RETAIN" in path and "F4" in path and "OBJ_FINAL" not in path


def _has_oob_then_retain_continue(path: Sequence[str]) -> bool:
    return "FAQ_OOB" in path and "F3_RETAIN" in path and "F4" in path and "OBJ_FINAL" not in path


def _retain_fail_flow_sig(path: Sequence[str]) -> tuple:
    if "OBJ_FINAL" not in path:
        return ()
    idx = path.index("OBJ_FINAL")
    return tuple(n for n in path[:idx] if n.startswith("F") or n in {"F3_RETAIN", "OBJECTION"})


def _pick(items: Sequence[PathItem], pred: Callable[[Sequence[str]], bool]) -> PathItem | None:
    hits = [x for x in items if pred(x[0])]
    if not hits:
        return None
    return min(hits, key=lambda x: (len(x[0]), tuple(x[0])))


def _insert_after(path: List[str], anchor: str, node: str) -> List[str] | None:
    if anchor not in path or node in path:
        return None
    i = path.index(anchor)
    return path[: i + 1] + [node] + path[i + 1 :]


def _path_item_key(item: PathItem) -> tuple:
    return (_path_key(item[0]), str(item[3] or ""))


def _path_target_k(item: PathItem) -> str:
    return faq_path_desc_tag(str(item[3] or ""))


def _supplement_from_mainline(mainline: Sequence[str], instruction: object | None = None) -> List[PathItem]:
    """Build pure FAQ/OOB paths; FAQ includes one path per K for linear tasks."""
    base = list(mainline)
    out: List[PathItem] = []
    km = infer_faq_step_knowledge(instruction, FAQ_ATTACH_STEPS) if instruction else {}
    seen_k: set[str] = set()
    for step in FAQ_ATTACH_STEPS:
        if step not in base:
            continue
        kids = km.get(step) or ()
        if kids:
            for kid in kids:
                faq = _insert_after(base, step, "FAQ_NORMAL")
                if faq and kid not in seen_k:
                    seen_k.add(kid)
                    out.append(_item_from_path(faq, f"faq_after_{step.lower()}@{kid}"))
        else:
            faq = _insert_after(base, step, "FAQ_NORMAL")
            if faq:
                out.append(_item_from_path(faq, f"faq_after_{step.lower()}"))
    for step in OOB_ATTACH_STEPS:
        if step not in base:
            continue
        oob = _insert_after(base, step, "FAQ_OOB")
        if oob:
            out.append(_item_from_path(oob, f"oob_after_{step.lower()}"))
    return out


def _has_obj_final_after_f4(path: Sequence[str]) -> bool:
    return (
        "OBJ_FINAL" in path
        and "F4" in path
        and path.index("F4") < path.index("OBJ_FINAL")
    )


def _item_from_path(path: List[str], desc: str = "supplemented") -> PathItem:
    return (path, [], 28, desc, 0.8)


def _pick_k_faq(items: Sequence[PathItem], flow_step: str, kid: str) -> PathItem | None:
    hits = [
        x
        for x in items
        if _has_pure_faq_after(x[0], flow_step) and _path_target_k(x) == kid
    ]
    if not hits:
        return None
    return min(hits, key=lambda x: (len(x[0]), tuple(x[0])))


def curate_retention_flow_paths(
    items: Sequence[PathItem],
    instruction: object | None = None,
) -> List[PathItem]:
    """
    instruction_1: retention path set with one FAQ path per knowledge node (K*).
    Also covers OOB, retain success/fail without FAQ×OOB×RETAIN combinatorial junk.
    """
    pool = list(items)
    mainline_item = _pick(pool, _is_mainline)
    if mainline_item:
        for extra in _supplement_from_mainline(mainline_item[0], instruction):
            key = _path_item_key(extra)
            if not any(_path_item_key(x) == key for x in pool):
                pool.append(extra)

    km = infer_faq_step_knowledge(instruction, FAQ_ATTACH_STEPS) if instruction else {}

    out: List[PathItem] = []
    seen: set[tuple] = set()

    mainline = _pick(pool, _is_mainline)
    if mainline:
        seen.add(_path_item_key(mainline))
        out.append(mainline)

    if km:
        for step in FAQ_ATTACH_STEPS:
            for kid in km.get(step, ()):
                item = _pick_k_faq(pool, step, kid)
                if not item:
                    continue
                key = _path_item_key(item)
                if key in seen:
                    continue
                seen.add(key)
                out.append(item)
    else:
        for step in FAQ_ATTACH_STEPS:
            item = _pick(pool, lambda p, s=step: _has_pure_faq_after(p, s))
            if not item:
                continue
            key = _path_key(item[0])
            if key in seen:
                continue
            seen.add(key)
            out.append(item)

    selectors: List[Callable[[Sequence[str]], bool]] = []
    for step in OOB_ATTACH_STEPS:
        selectors.append(lambda p, s=step: _has_pure_oob_after(p, s))
    selectors.extend(
        [
            _has_retain_then_continue,
            _has_faq_then_retain_continue,
            _has_oob_then_retain_continue,
            lambda p: "OBJECTION" in p and "OBJ_FINAL" not in p,
            _has_obj_final_after_f4,
        ]
    )

    for pred in selectors:
        item = _pick(pool, pred)
        if not item:
            continue
        key = _path_key(item[0])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)

    # Distinct retain-failure trajectories (early / mid / late).
    fail_candidates = [x for x in pool if "OBJ_FINAL" in x[0]]
    fail_sigs: set[tuple] = set()
    for item in sorted(fail_candidates, key=lambda x: (len(x[0]), x[0])):
        sig = _retain_fail_flow_sig(item[0])
        if not sig or sig in fail_sigs:
            continue
        fail_sigs.add(sig)
        key = _path_key(item[0])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(fail_sigs) >= 5:
            break

    return out if out else list(items)
