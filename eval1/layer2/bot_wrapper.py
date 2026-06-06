from __future__ import annotations

import re
from typing import Any, Dict, List

from eval1.bot_provider import get_bot_llm_profile
from eval1.config import settings
from eval1.layer2.constraint_scenarios import build_driving_hangup_alts, is_driving_user
from eval1.layer2.instruction_grounding import (
    build_closing_reply_alts,
    build_closing_reply_hint,
    build_deterministic_grounded_reply,
    build_grounded_reply_hint,
    build_hangup_reply_alts,
    build_instruction_grounding,
    build_objection_reply_hint,
    build_step_utterance_alts,
    find_constraint_lines,
    is_faq_leak_on_flow_step,
    is_grounded_in_instruction,
)
from eval1.layer1.instruction_capabilities import instruction_has_retention_rails
from eval1.layer2.instruction_injection import (
    build_bot_system_prompt,
    build_f4_single_utterance,
    compress_step_to_utterance,
    f4_parts_remaining,
    instruction_f4_is_delivery_split,
    pick_f4_next_utterance,
    pick_flow_step_fallback,
    pick_flow_step_utterance,
    _is_meta_step_line,
    sanitize_bot_output,
    _strip_step_label,
)
from eval1.layer2.instruction_profile import build_instruction_profile
from eval1.layer2.prompt_cache import GLOBAL_BOT_PROMPT_CACHE
from eval1.layer2.bot_repeat_guard import (
    format_repeat_guard_hint,
    is_busy_or_refuse_user,
    is_semantically_repetitive,
    pick_non_repeating,
)
from eval1.layer2.robust_llm import RobustLLMCall

GENERIC_BOT_PATTERNS = (
    "收到，我们继续",
    "我们继续下一步",
    "好的，继续",
    "请确认当前步骤",
)

META_READOUT_PATTERNS = (
    "进入下一步",
    "进入第",
    "请转达",
    "参考话术",
    "然后进入",
    "说明飞毛腿",
    "说明单日",
    "完成收口",
    "并非站长干预",
)


class BotWrapper:
    """Qwen-backed bot under test with full business instruction injection."""

    def __init__(self) -> None:
        self._llm = RobustLLMCall(component="bot")

    async def reply(
        self,
        *,
        instruction: Any,
        instruction_summary: str,
        current_step_text: str,
        bot_state: Dict[str, object] | None,
        dialogue_history: List[Dict[str, str]],
        current_state: str,
        last_user_utterance: str = "",
        user_action: str = "comply",
        stalled_rounds: int = 0,
        closing_tone: str = "",
    ) -> Dict[str, str | bool]:
        slots = dict((bot_state or {}).get("slot_values") or {})
        inst_id = str(getattr(instruction, "instruction_id", "") or "default")
        sys_prompt, completeness_warnings = GLOBAL_BOT_PROMPT_CACHE.get_system_prompt(
            instruction_id=inst_id,
            slots=slots,
            builder=lambda: build_bot_system_prompt(instruction, slots, eval_mode=True),
        )
        if completeness_warnings and bot_state is not None:
            bot_state["instruction_warnings"] = completeness_warnings
        name_used = bool((bot_state or {}).get("name_used"))
        user_asked = user_action in {"ask_question", "off_topic"} or self._looks_like_question(last_user_utterance)
        user_objected = (
            user_action == "reject"
            or is_busy_or_refuse_user(last_user_utterance)
            or is_driving_user(last_user_utterance)
        )
        bot_history = [
            str(m.get("content", ""))
            for m in dialogue_history
            if str(m.get("role", "")).lower() == "bot"
        ]

        grounding = build_instruction_grounding(instruction, slots)
        hist = "\n".join(
            [f"{m.get('role','').upper()}: {m.get('content','')}" for m in dialogue_history[-6:]]
        )
        answer_hint = ""
        no_repeat_rule = find_constraint_lines(instruction, "重复", "重申")
        profile = build_instruction_profile(instruction, slots)
        if no_repeat_rule:
            answer_hint = f"【Constraints】{no_repeat_rule[0]}\n"
        if current_state == "CLOSING":
            tone = str(closing_tone or "neutral")
            answer_hint += build_closing_reply_hint(
                closing_tone=tone,
                last_user_utterance=last_user_utterance,
                instruction=instruction,
            )
        elif user_objected and last_user_utterance:
            if is_driving_user(last_user_utterance):
                drive_rule = find_constraint_lines(instruction, "开车", "驾驶", "稍后再打")
                alts = build_driving_hangup_alts(instruction)
                answer_hint += (
                    f"用户表示正在开车：「{last_user_utterance}」\n"
                    + (f"【Constraints】{drive_rule[0]}\n" if drive_rule else "")
                    + f"必须礼貌收口并挂断（≤20字），参考：{alts[0]}；"
                    "禁止继续推销、加微信或展开业务说明。"
                )
            elif is_busy_or_refuse_user(last_user_utterance):
                hangup_rule = find_constraint_lines(instruction, "挂断", "无法配送")
                answer_hint += (
                    f"用户表示没空/不想聊：「{last_user_utterance}」\n"
                    + (f"【Constraints】{hangup_rule[0]}\n" if hangup_rule else "")
                    + "简短表示理解并礼貌收口（≤30字），可说再见、不打扰；"
                    "不要继续催接单或重复安全提醒。"
                )
            else:
                answer_hint += build_objection_reply_hint(
                    instruction=instruction,
                    grounding=grounding,
                    question=last_user_utterance,
                    current_state=current_state,
                    current_step_text=current_step_text,
                )
                if current_state in {"F3_RETAIN", "F3", "OBJECTION"} and instruction_has_retention_rails(
                    instruction
                ):
                    answer_hint += (
                        "\n【挽留任务】骑手犹豫或不想继续。必须在一句话内完成："
                        "①简短理解；②点出继续配送的好处（名额/排名/多接单）；"
                        "③鼓励试试并提醒注意安全。"
                        "禁止只说「方便听我说一句吗」而无实质挽留；"
                        "禁止复读上一轮；总字数≤30字。"
                    )
        elif user_asked and last_user_utterance:
            answer_hint = build_grounded_reply_hint(
                question=last_user_utterance,
                grounding=grounding,
                current_step_text=current_step_text,
                current_state=current_state,
            )
        elif user_action in {"comply", "confirm"} and stalled_rounds >= 1:
            answer_hint = (
                "用户已确认本步骤，禁止再重复叮嘱/祝福/安全提醒。"
                "必须推进当前步骤的新信息或下一步要点，不要再说「注意安全」「祝你顺利」类收尾。"
            )
        elif user_action in {"comply", "confirm"} and current_state == "F3":
            answer_hint = (
                "【F3任务】鼓励骑手继续配送并提醒注意安全（如路上注意安全、辛苦了）。"
                "禁止主动引用 FAQ/Knowledge（如「许多骑手正在申请」「名额被占用」「单日/多日合同」）；"
                "该类内容仅在 FAQ 节点或用户追问时再答。"
            )
            if (
                "delivery" in profile.active_domains
                and any("连续" in h and ("天" in h or "3" in h) for h in bot_history[-4:])
            ):
                answer_hint += (
                    "\n【步骤衔接】F2 已说明连续配送/天数要求，用户也已确认。"
                    "禁止再提「连续3天/连续配送/合同天数/保住资格」。"
                )
        elif current_state == "F3" and not user_asked and not user_objected:
            answer_hint = (
                "【F3任务】鼓励配送+安全提醒。"
                "禁止引用 FAQ 知识库（许多骑手申请、名额占用等）。"
            )
        elif (
            user_action in {"comply", "confirm"}
            and current_state == "F4"
            and instruction_f4_is_delivery_split(instruction, current_step_text, slots)
        ):
            if any("连续" in h for h in bot_history[-4:]):
                answer_hint = (
                    "【步骤衔接】连续配送已在前面讲过；本步(F4)只讲排名/拒单/天气三要点，勿重复天数要求。"
                )
        if (
            current_state == "F4"
            and current_step_text
            and instruction_f4_is_delivery_split(instruction, current_step_text, slots)
        ):
            full_line = build_f4_single_utterance(
                current_step_text, slots=slots, instruction=instruction
            )
            remaining = f4_parts_remaining(bot_state)
            answer_hint += (
                f"\n【Call Flow 第4步原文】{current_step_text}\n"
                f"F4 须一次性说清三个要点（排名非站长 / 少拒单取消超时 / 坏天气保资格），"
                f"参考话术（勿照读标签）：{full_line}\n"
                f"{'已讲过 F4，勿复读，简短回应或推进收口。' if remaining == 0 else '本轮首次说明 F4，说完即可。'}"
            )
        if bot_history:
            answer_hint += "\n" + format_repeat_guard_hint(bot_history)
        if (last_user_utterance or "").strip():
            answer_hint += (
                f"\n【承接用户】用户刚说：「{last_user_utterance.strip()}」\n"
                "须先简短回应其态度或问题，再推进本步；禁止无视用户、照读步骤标题或参考话术原句。"
            )
        user_prompt = (
            f"当前FSM步骤：{current_state}\n"
            f"当前步骤要点（语义参考，勿照读）：{_strip_step_label(current_step_text)}\n"
            f"{answer_hint}\n"
            f"Bot内部状态：{self._bot_state_brief(bot_state)}\n"
            f"是否已用过姓名：{'是' if name_used else '否'}\n"
            f"最近对话：\n{hist}\n\n"
            "请直接输出本轮Bot要说的话（结合上下文自主措辞，勿固定模板）。"
            "若用户已确认上一步，必须推进新内容，不要重复已说过的要求。"
        )
        inst_alts = build_step_utterance_alts(
            instruction, current_state, current_step_text, slots
        )
        fallback_text = inst_alts[0] if inst_alts else pick_flow_step_utterance(
            current_state, current_step_text, bot_state, slots=slots, instruction=instruction
        )
        if (
            current_state == "F4"
            and current_step_text
            and instruction_f4_is_delivery_split(instruction, current_step_text, slots)
        ):
            fallback_text = pick_f4_next_utterance(
                bot_state, current_step_text, slots=slots, instruction=instruction
            )
        if current_state == "CLOSING":
            tone = str(closing_tone or "neutral")
            fallback_text = pick_non_repeating(
                build_closing_reply_alts(instruction, tone, last_user_utterance=last_user_utterance),
                bot_history,
                attempt=stalled_rounds,
            )
        elif user_asked and last_user_utterance:
            fallback_text = build_deterministic_grounded_reply(
                question=last_user_utterance,
                grounding=grounding,
                current_step_text=current_step_text,
            )
        elif user_objected and last_user_utterance:
            pool = list(inst_alts) + build_hangup_reply_alts(instruction)
            fallback_text = pick_non_repeating(pool, bot_history, attempt=stalled_rounds)

        dialogue_timeout = float(getattr(settings, "llm_dialogue_timeout_sec", 28.0))
        bot_llm = get_bot_llm_profile()

        async def _primary() -> str:
            text = await self._llm.chat(
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                model=bot_llm["model"],
                temperature=0.38,
                attempts=3,
                timeout_s=dialogue_timeout,
                api_key=bot_llm["api_key"],
                api_base=bot_llm["api_base"],
                provider_label=bot_llm["bot_provider"],
            )
            text = self.normalize_utterance(text, bot_state)
            if (
                self._is_bad_response(text)
                or is_faq_leak_on_flow_step(current_state, text)
                or not is_grounded_in_instruction(text, grounding)
            ):
                if user_asked and last_user_utterance:
                    return build_deterministic_grounded_reply(
                        question=last_user_utterance,
                        grounding=grounding,
                        current_step_text=current_step_text,
                    )
                return pick_non_repeating(
                    inst_alts or [pick_flow_step_utterance(
                        current_state, current_step_text, bot_state, slots=slots
                    )],
                    bot_history,
                    attempt=stalled_rounds,
                )
            return text

        if user_objected and is_busy_or_refuse_user(last_user_utterance):
            fallback_text = pick_non_repeating(
                build_hangup_reply_alts(instruction), bot_history, attempt=stalled_rounds
            )

        text, status = await self._llm.call_with_fallback(
            primary_fn=_primary,
            fallback_value=fallback_text,
            validator=lambda s: bool((s or "").strip()),
            max_retry=1,
            timeout=dialogue_timeout + 4.0,
            tag="bot_reply",
        )
        text = str(text).strip()
        if is_semantically_repetitive(text, bot_history):
            pool = list(inst_alts) + build_hangup_reply_alts(instruction)
            text = pick_non_repeating(pool, bot_history, attempt=stalled_rounds)
        return {
            "text": text,
            "llm_connected": status == "success",
            "degraded": status == "degraded",
        }

    def _looks_like_question(self, text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        return any(k in t for k in ["？", "?", "吗", "什么", "为什么", "依据", "怎么", "哪"])

    def _is_step_title_leak(self, text: str, bot_state: Dict[str, object] | None) -> bool:
        t = (text or "").strip().rstrip("。.")
        if not t or "？" in t or "?" in t or "吗" in t:
            return False
        step_text = str((bot_state or {}).get("current_step_text") or "").strip()
        step_id = str((bot_state or {}).get("current_step_id") or "")
        if not step_text:
            return False
        title = _strip_step_label(step_text).strip().rstrip("。.")
        if t == title or t in title or title in t:
            return True
        leaks = ("前端是否可见", "确认是否知情", "检查学员端费用", "企业微信添加", "10秒；适合大班")
        if any(k in t for k in leaks):
            return True
        return step_id == "F4" and "前端" in t and len(t) <= 12

    def normalize_utterance(self, utterance: str, bot_state: Dict[str, object] | None) -> str:
        text = sanitize_bot_output((utterance or "").strip())
        if not text or not bot_state:
            return text
        slots = dict(bot_state.get("slot_values") or {})
        if "参考话术" in text or "询问：" in text or text.startswith("**"):
            state_id = str(bot_state.get("current_step_id") or "F3")
            step_text = str(bot_state.get("current_step_text") or "")
            text = pick_flow_step_utterance(
                state_id,
                step_text,
                bot_state,
                slots=slots,
                instruction=bot_state.get("_instruction"),
            )
        elif _is_meta_step_line(text) or "挽留不想配送的骑手" in text:
            state_id = str(bot_state.get("current_step_id") or "F3")
            step_text = str(bot_state.get("current_step_text") or "")
            text = pick_flow_step_utterance(
                state_id,
                step_text,
                bot_state,
                slots=slots,
                instruction=bot_state.get("_instruction"),
            )
        elif self._is_step_title_leak(text, bot_state):
            state_id = str(bot_state.get("current_step_id") or "F3")
            step_text = str(bot_state.get("current_step_text") or "")
            text = pick_flow_step_utterance(
                state_id,
                step_text,
                bot_state,
                slots=slots,
                instruction=bot_state.get("_instruction"),
            )
        branch_m = re.match(r"^(?:若|如果).+?[→\-]{1,2}\s*(.+?)[。]?$", text)
        if branch_m:
            from eval1.layer2.step_speakable import naturalize_branch_action

            natural = naturalize_branch_action(branch_m.group(1).strip())
            if natural:
                text = natural
        name = str(slots.get("rider_name", "")).strip()
        if not name:
            return text
        name_used = bool(bot_state.get("name_used"))
        patterns = [
            rf"^\*\*{re.escape(name)}\*\*[，,：:]?\s*",
            rf"^{re.escape(name)}[，,：:]?\s*",
        ]
        if name_used:
            for pat in patterns:
                text = re.sub(pat, "", text, count=1)
        if name in text and not name_used:
            bot_state["name_used"] = True
        elif name_used:
            bot_state["name_used"] = True
        return text.strip()

    def _is_bad_response(self, text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return True
        if re.search(r"step\s*\d+", t, re.I):
            return True
        if any(p in t for p in GENERIC_BOT_PATTERNS):
            return True
        if any(p in t for p in META_READOUT_PATTERNS):
            return True
        if t.startswith(("说明", "确认", "完成收口", "告知")):
            return True
        return False

    def _bot_state_brief(self, bot_state: Dict[str, object] | None) -> str:
        if not bot_state:
            return "none"
        step = str(bot_state.get("current_step_id", ""))
        last = str(bot_state.get("last_bot_utterance", ""))
        slots = bot_state.get("slot_values") or {}
        used = bot_state.get("used_knowledge_ids") or []
        return (
            f"step={step}; last_bot={last}; name_used={bool(bot_state.get('name_used'))}; "
            f"slot_keys={','.join(list(slots)[:5])}; "
            f"used_knowledge={','.join([str(x) for x in list(used)[:5]])}"
        )
