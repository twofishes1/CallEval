from __future__ import annotations

from typing import Dict, List, Set, Tuple

from eval1.layer1.faq_step_context import faq_path_desc_tag
from eval1.layer1.models import EnumeratedPath
from eval1.layer1.path_plan_config import PathPlanConfig, infer_path_plan_config
from eval1.layer1.path_coverage_planner import plan_coverage_paths
from eval1.layer1.path_descriptions import enrich_path_dict, path_category_tag
from eval1.layer1.path_probe import (
    PROBE_D10_DRIVE,
    PROBE_D9_BUSY,
    build_constraint_probe_paths,
    build_faq_paths,
    is_probe_node,
    pick_mainline_template,
    probe_constraint_for_path,
    scenario_path_desc_tag,
)
from eval1.layer1.rule_graph import RuleGraphBuilder


class PathEnumerator:
    """Unified coverage planner: same pipeline for all tasks; mode-specific candidate generation."""

    def __init__(self, graph_builder: RuleGraphBuilder, max_depth: int | None = None, max_paths: int = 64) -> None:
        self.gb = graph_builder
        self.max_paths = max_paths
        flow_len = len(graph_builder.flow_nodes or [])
        self.max_depth = max_depth if max_depth is not None else max(24, flow_len * 4 + 12)
        self._plan_config = infer_path_plan_config(graph_builder, max_paths=max_paths)

    def enumerate_paths(self) -> List[EnumeratedPath]:
        config = self._plan_config
        dfs_pool: List[Tuple[List[str], List[str], int, str, float]] = []
        if config.is_linear and config.include_retention_variants:
            dfs_pool = self._collect_dfs_pool()
        merged = plan_coverage_paths(self.gb, config, linear_dfs_pool=dfs_pool)
        return self._to_enumerated(merged)

    def _collect_dfs_pool(self) -> List[Tuple[List[str], List[str], int, str, float]]:
        """Linear tasks: DFS generates interrupt-combination candidates for curator."""
        return self._enumerate_dfs_paths(raw_pool_only=True)

    def _estimate_turn_cost(self, path: List[str]) -> int:
        node_turn_cost: Dict[str, int] = {
            "flow_step": 2,
            "flow_branch": 1,
            "op_step": 1,
            "transition": 3,
            "meta": 1,
            "knowledge": 1,
        }
        cost = 0
        g = self.gb.g
        for n in path:
            if n not in g:
                cost += 1
                continue
            ntype = str(g.nodes[n].get("node_type", "meta"))
            cost += node_turn_cost.get(ntype, 1)
        return cost

    def _to_enumerated(
        self, merged: List[Tuple[List[str], List[str], int, str, float]]
    ) -> List[EnumeratedPath]:
        out: List[EnumeratedPath] = []
        slots = self._variable_slots()
        for i, (path, activated, turns, desc, _conf) in enumerate(merged, start=1):
            target_k = faq_path_desc_tag(str(desc or ""))
            target_scenario = scenario_path_desc_tag(str(desc or "")) or probe_constraint_for_path(path)
            item = EnumeratedPath(
                path_id=f"P{i}",
                nodes=path,
                activated_rules=activated,
                base_max_turns=turns,
                description=path_category_tag(path),
                target_knowledge_id=target_k,
                target_scenario_id=target_scenario,
            )
            enriched = enrich_path_dict(item.model_dump(), self.gb.instruction, slots)
            out.append(EnumeratedPath.model_validate(enriched))
        return out

    def _enumerate_dfs_paths(self, *, raw_pool_only: bool = False) -> List[EnumeratedPath] | List[Tuple[List[str], List[str], int, str, float]]:
        g = self.gb.g
        out_raw: List[Tuple[List[str], List[str], int, str, float]] = []
        seen_exact: Set[str] = set()
        flow_nodes = [n for n in self.gb.flow_nodes]
        node_turn_cost: Dict[str, int] = {
            "flow_step": 2,
            "flow_branch": 1,
            "op_step": 1,
            "transition": 3,
            "meta": 1,
            "constraint": 0,
            "knowledge": 1,
        }

        def _branch_successors(node: str) -> List[str]:
            return [
                s
                for s in g.successors(node)
                if str(s).startswith("branch::") or str(s).startswith("op::")
            ]

        def _next_flow_successors(node: str) -> List[str]:
            if not node.startswith("F") or not node[1:].isdigit():
                return []
            try:
                n = int(node[1:])
            except ValueError:
                return []
            nxt = f"F{n + 1}"
            return [nxt] if nxt in g.successors(node) else []

        def _successor_order(node: str, candidates: List[str]) -> List[str]:
            """Explore branch/main flow before FAQ interrupts so mainline paths exist."""

            def rank(nxt: str) -> tuple:
                if str(nxt).startswith("branch::"):
                    return (0, nxt)
                if str(nxt).startswith("op::"):
                    return (1, nxt)
                if nxt.startswith("F") or nxt == "CLOSING":
                    return (2, nxt)
                if nxt == "END":
                    return (3, nxt)
                if nxt in {"FAQ_NORMAL", "OBJECTION", "FAQ_OOB", "F3_RETAIN", "OBJ_FINAL"}:
                    return (9, nxt)
                return (5, nxt)

            return sorted(candidates, key=lambda n: rank(n))

        def dfs(node: str, path: List[str], interrupts: int) -> None:
            if len(out_raw) >= self.max_paths * 12:
                return
            if len(path) > self.max_depth:
                return
            if node == "END":
                sig = "->".join(path)
                if sig in seen_exact:
                    return
                seen_exact.add(sig)
                activated = self._activated_rules(path)
                cost = 0
                for n in path:
                    ntype = str(g.nodes[n].get("node_type", "meta"))
                    cost += node_turn_cost.get(ntype, 1)
                desc = self._describe(path)
                conf = self._path_confidence(path)
                out_raw.append((path, activated, max(28, cost + len(flow_nodes) * 2), desc, conf))
                return

            successors = _successor_order(node, list(g.successors(node)))
            branch_children = _branch_successors(node)
            flow_next = _next_flow_successors(node)

            for nxt in successors:
                if nxt in {"GLOBAL_DIALOGUE", "GLOBAL_BOUNDARY"}:
                    continue
                etype = str(g.edges[node, nxt].get("edge_type", ""))

                if node == "START" and nxt.startswith("F") and nxt != "F1" and nxt != "F3_RETAIN":
                    continue
                if nxt == "FAQ_OOB" and not any(p in flow_nodes for p in path):
                    continue
                if etype == "goto" and node in {"F3_RETAIN", "FAQ_NORMAL"} and nxt in flow_nodes:
                    first_unexecuted = next((f for f in flow_nodes if f not in path), None)
                    if first_unexecuted and nxt != first_unexecuted:
                        continue

                # Branched Call Flow: cannot skip branch choice via F→F sequence
                if (
                    self._plan_config.is_branched
                    and node.startswith("F")
                    and branch_children
                    and nxt in flow_next
                    and etype == "sequence"
                ):
                    continue

                new_interrupts = interrupts + (1 if nxt in {"OBJECTION", "FAQ_OOB"} else 0)
                if new_interrupts > 1:
                    continue

                if nxt in path and nxt not in {"F3_RETAIN"}:
                    if not (str(nxt).startswith("branch::") or str(nxt).startswith("op::")):
                        continue
                    if path.count(nxt) >= 1:
                        continue
                dfs(nxt, path + [nxt], new_interrupts)

        dfs("START", ["START"], 0)

        bucket: Dict[str, Tuple[List[str], List[str], int, str, float]] = {}
        for item in out_raw:
            path, activated, turns, desc, conf = item
            sig = self._coverage_signature(path)
            old = bucket.get(sig)
            if old is None:
                bucket[sig] = item
                continue
            old_cov = len(old[1])
            new_cov = len(activated)
            if (conf, new_cov, -len(path)) > (old[4], old_cov, -len(old[0])):
                bucket[sig] = item

        merged = list(bucket.values())
        merged.sort(
            key=lambda x: (
                self._interrupt_penalty(x[0]),
                -self._branch_richness(x[0]),
                -x[4],
                -len(x[1]),
                len(x[0]),
            )
        )
        if raw_pool_only:
            return merged

        merged = merged[: self.max_paths]
        return self._to_enumerated(merged)

    def _rebuild_path_item(self, path: List[str]) -> Tuple[List[str], List[str], int, str, float]:
        flow_len = len(self.gb.flow_nodes or [])
        cost = self._estimate_turn_cost(path)
        return (
            path,
            self._activated_rules(path),
            max(28, cost + flow_len * 2),
            self._describe(path),
            self._path_confidence(path),
        )

    def _branch_richness(self, path: List[str]) -> int:
        return sum(1 for n in path if str(n).startswith("branch::") or str(n).startswith("op::"))

    def _interrupt_penalty(self, path: List[str]) -> int:
        """Lower = preferred. Cooperative/mainline paths should rank before FAQ/OOB."""
        score = 0
        if "FAQ_NORMAL" in path:
            score += 10
        if "FAQ_OOB" in path:
            score += 20
        if any(is_probe_node(n) for n in path):
            score += 15
        if any(n in path for n in ("OBJECTION", "F3_RETAIN", "OBJ_FINAL")):
            score += 30
        return score

    def _append_mandatory_paths(
        self,
        merged: List[Tuple[List[str], List[str], int, str, float]],
    ) -> List[Tuple[List[str], List[str], int, str, float]]:
        """Ensure FAQ + constraint probe coverage without branch-combo explosion."""
        existing = {self._coverage_signature(p) for p, *_ in merged}
        branch_paths = [p for p, *_ in merged]
        template = pick_mainline_template(branch_paths)

        extras: List[Tuple[List[str], List[str], int, str, float]] = []
        for nodes, desc in (
            *build_faq_paths(template),
            *build_constraint_probe_paths(template),
        ):
            sig = self._coverage_signature(nodes)
            if sig in existing:
                continue
            existing.add(sig)
            activated = self._activated_rules(nodes)
            cost = 0
            for n in nodes:
                if n not in self.gb.g:
                    cost += 1
                    continue
                ntype = str(self.gb.g.nodes[n].get("node_type", "meta"))
                cost += {"flow_step": 2, "flow_branch": 1, "op_step": 1, "transition": 3, "meta": 1, "knowledge": 1}.get(
                    ntype, 1
                )
            flow_len = len(self.gb.flow_nodes or [])
            extras.append(
                (
                    nodes,
                    activated,
                    max(28, cost + flow_len * 2),
                    desc,
                    self._path_confidence(nodes),
                )
            )

        if not extras:
            return merged

        mainline = [x for x in merged if self._interrupt_penalty(x[0]) == 0]
        reserve = len(extras)
        cap = max(0, self.max_paths - reserve)
        trimmed = mainline[:cap] + extras
        seen_sig: set[str] = set()
        out: List[Tuple[List[str], List[str], int, str, float]] = []
        for item in trimmed:
            sig = self._coverage_signature(item[0])
            if sig in seen_sig:
                continue
            seen_sig.add(sig)
            out.append(item)
        out.sort(
            key=lambda x: (
                self._interrupt_penalty(x[0]),
                -self._branch_richness(x[0]),
                -x[4],
                -len(x[1]),
                len(x[0]),
            )
        )
        return out

    def _variable_slots(self) -> Dict[str, str]:
        slots: Dict[str, str] = {}
        for name, vnode in dict(getattr(self.gb.instruction, "variables", {}) or {}).items():
            val = str(getattr(vnode, "value", "") or "").strip()
            if val:
                slots[str(name)] = val
        return slots

    def _activated_rules(self, path: List[str]) -> List[str]:
        ids: List[str] = []
        flow_set = set(path)
        for c in self.gb.instruction.constraints:
            cid = c.id
            if cid.startswith("D") or cid.startswith("B"):
                ids.append(cid)
                continue
            if cid.startswith("F") and cid in flow_set:
                ids.append(cid)
                continue
            if cid.startswith("K") and ("FAQ_NORMAL" in flow_set or "FAQ_OOB" in flow_set):
                ids.append(cid)
        for n in path:
            if str(n).startswith("branch::"):
                ids.append(str(n))
        return sorted(set(ids))

    def _describe(self, path: List[str]) -> str:
        if "OBJ_FINAL" in path:
            return "retention failed, terminate with objection"
        if PROBE_D10_DRIVE in path:
            return "probe driving (D10) early hangup"
        if PROBE_D9_BUSY in path:
            return "probe busy (D9) then continue"
        if "FAQ_OOB" in path:
            return "contains out-of-bound question handling"
        if "FAQ_NORMAL" in path:
            return "contains faq interruption and resume"
        if "F3_RETAIN" in path:
            return "contains retention jump"
        branch_nodes = [n for n in path if str(n).startswith("branch::")]
        if branch_nodes:
            return "branch_flow_completion"
        return "standard flow completion"

    def _path_confidence(self, path: List[str]) -> float:
        vals: List[float] = []
        for a, b in zip(path[:-1], path[1:]):
            if self.gb.g.has_edge(a, b):
                vals.append(float(self.gb.g.edges[a, b].get("edge_confidence", 0.6)))
        if not vals:
            return 0.0
        return sum(vals) / len(vals)

    def _normalize_branch_key(self, branch_id: str) -> str:
        """Collapse cooperative main variants at the same step (keep F6 wechat choices)."""
        parts = str(branch_id).split("::")
        if len(parts) >= 4 and parts[2] == "main" and parts[1] not in {"6"}:
            return f"branch::{parts[1]}::main"
        return str(branch_id)

    def _coverage_signature(self, path: List[str]) -> str:
        """Coarse dedup key: F4/F6 branch choices + FAQ/probe flags, not F3/F5 permutations."""
        out: List[str] = []
        flow_seen: List[str] = []
        branch_seen: List[str] = []
        op_flags: Set[str] = set()
        flags: Set[str] = set()
        for n in path:
            if n.startswith("F") and n[1:].isdigit():
                if n not in flow_seen:
                    flow_seen.append(n)
                continue
            if str(n).startswith("branch::"):
                branch_seen.append(self._normalize_branch_key(str(n)))
                continue
            if str(n).startswith("op::"):
                parts = str(n).split("::")
                if len(parts) >= 2:
                    op_flags.add(f"op::{parts[1]}::guided")
                continue
            if n in {"FAQ_NORMAL", "FAQ_OOB", "OBJECTION", "F3_RETAIN", "OBJ_FINAL"}:
                flags.add(n)
            if is_probe_node(n):
                flags.add(str(n))
            if n in {"START", "CLOSING", "END"}:
                out.append(n)
        out.extend(flow_seen)
        out.extend(branch_seen)
        out.extend(sorted(op_flags))
        out.extend(sorted(flags))
        return "->".join(out)

    def _semantic_signature(self, path: List[str]) -> str:
        return self._coverage_signature(path)
