from __future__ import annotations

import re
from typing import Any, Dict, List


class InstructionPreprocessor:
    """Deterministic preprocessing without LLM calls."""

    _hdr_re = re.compile(r"^\s*#{1,2}\s*(.+?)\s*$")
    _num_re = re.compile(r"^\s*\d+\.\s*(.+?)\s*$")
    _dash_re = re.compile(r"^\s*-\s*(.+?)\s*$")
    _explicit_var_re = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
    _bold_var_re = re.compile(r"\*\*([A-Z])\s*\S*?\*\*")
    _branch_re = re.compile(r"(若|如果|when)(.+?)(→|则|:)")

    @staticmethod
    def _split_inline_section(header: str) -> tuple[str, str]:
        h = (header or "").strip()
        low = h.lower()
        for key, prefixes in (
            ("role", ("role",)),
            ("task", ("task",)),
            ("opening_line", ("opening line", "opening")),
        ):
            for prefix in prefixes:
                if low.startswith(prefix):
                    sep = re.search(r"[:：]", h)
                    if sep:
                        return key, h[sep.end() :].strip()
                    return key, ""
        return "", ""

    def preprocess(self, raw_text: str) -> Dict[str, Any]:
        sections: Dict[str, Any] = {
            "role": "",
            "task": "",
            "opening_line": "",
            "call_flow": [],
            "knowledge": [],
            "constraints": [],
        }
        variables: Dict[str, Dict[str, str]] = {}
        var_locations: Dict[str, List[str]] = {}
        conditional_branches: List[Dict[str, Any]] = []

        lines = (raw_text or "").splitlines()
        current = ""
        for idx, ln in enumerate(lines):
            m = self._hdr_re.match(ln)
            if m:
                hdr = m.group(1).strip()
                hdr_lower = hdr.lower()
                inline_key, inline_body = self._split_inline_section(hdr)
                if inline_key == "role":
                    current = "role"
                    if inline_body:
                        sections["role"] = (sections["role"] + "\n" + inline_body).strip()
                    continue
                if inline_key == "task":
                    current = "task"
                    if inline_body:
                        sections["task"] = (sections["task"] + "\n" + inline_body).strip()
                    continue
                if inline_key == "opening_line":
                    current = "opening_line"
                    if inline_body:
                        sections["opening_line"] = (sections["opening_line"] + "\n" + inline_body).strip()
                    continue
                # Sub-step headers inside Call Flow stay in call_flow collection.
                if current == "call_flow" and re.match(r"step\s*\d+", hdr_lower):
                    sections["call_flow"].append(hdr.strip())
                    continue
                if "role" in hdr_lower:
                    current = "role"
                elif "task" in hdr_lower:
                    current = "task"
                elif "opening" in hdr_lower:
                    current = "opening_line"
                elif "flow" in hdr_lower:
                    current = "call_flow"
                elif "knowledge" in hdr_lower or "faq" in hdr_lower:
                    current = "knowledge"
                elif "constraint" in hdr_lower:
                    current = "constraints"
                continue

            text = ln.strip()
            if not text:
                continue

            if current in {"role", "task", "opening_line"}:
                sections[current] = (sections[current] + "\n" + text).strip()
            elif current in {"call_flow", "knowledge"}:
                nm = self._num_re.match(ln)
                dm = self._dash_re.match(ln)
                item = nm.group(1).strip() if nm else dm.group(1).strip() if dm else text
                sections[current].append(item)
            elif current == "constraints":
                dm = self._dash_re.match(ln)
                item = dm.group(1).strip() if dm else text
                sections[current].append(item)

            # variable extraction
            for v in self._explicit_var_re.findall(text):
                variables.setdefault(v, {"raw": f"${{{v}}}", "type": "explicit"})
                var_locations.setdefault(v, []).append(f"{current}[{idx}]")
            for v in self._bold_var_re.findall(text):
                variables.setdefault(v, {"raw": f"**{v}**", "type": "bold"})
                var_locations.setdefault(v, []).append(f"{current}[{idx}]")

            if current == "call_flow":
                bm = self._branch_re.search(text)
                if bm:
                    conditional_branches.append(
                        {
                            "step_index": len(sections["call_flow"]),
                            "condition": bm.group(2).strip(),
                            "action": text,
                        }
                    )

        return {
            "sections": sections,
            "variables": variables,
            "variable_locations": var_locations,
            "conditional_branches": conditional_branches,
        }
