from __future__ import annotations

import random
import re
from typing import Dict, List

from eval1.config import settings
from eval1.layer2.action_detector import ActionDetector
from eval1.layer2.user_context_memory import UserContextMemory
from eval1.layer2.user_sim_instruction_context import UserSimScene, build_user_sim_scene
from eval1.layer2.user_role_guard import caller_role_leak_reason, stale_identity_ack_reason
from eval1.layer2.instruction_profile import build_instruction_profile
from eval1.layer2.user_simulator_prompt import (
    build_user_sim_system_prompt,
    build_user_sim_user_prompt,
    contains_unnatural_phrasing,
)
from eval1.layer2.path_user_driver import path_coverage_action
from eval1.layer1.faq_step_context import ask_seeds_for_faq_step, faq_interrupt_flow_step
from eval1.layer1.path_probe import PROBE_D10_DRIVE, PROBE_D9_BUSY, probe_user_line
from eval1.layer2.persona import PersonaCard, PersonaType
from eval1.layer2.persona_phrasing import (
    build_minimal_action_utterance,
    build_persona_contextual_tone_hint,
    enrich_path_utterance_hint,
    is_canned_minimal_utterance,
    is_disconnected_user_response,
    is_generic_persona_stub,
    is_questioning_hollow_confirm,
    is_resistant_overly_cooperative,
    is_hollow_user_response,
    is_instruction_label_leak,
    is_impatient_hollow_response,
    is_listen_only_ack,
    is_role_term_misuse,
    verify_persona_tone,
)
from eval1.layer2.robust_llm import RobustLLMCall
from eval1.layer2.utterance_diversity import check_utterance_variety

PERSONA_STYLE = {
    "cooperative": {"temperature": 0.62},
    "impatient": {"temperature": 0.86},
    "resistant": {"temperature": 0.82},
    "questioning": {"temperature": 0.72},
    "ignorant": {"temperature": 0.68},
    "off_topic": {"temperature": 0.85},
}

SAMPLED_TO_FSM = {
    "comply": "comply",
    "confirm": "confirm",
    "ask_question": "ask_question",
    "reject": "reject",
    "off_topic": "off_topic",
    "hangup": "hangup",
}


class UserSimulatorAgent:
    """Adaptive LLM user simulator: persona style + structured context memory."""

    def __init__(self) -> None:
        self._action_detector = ActionDetector()
        self._llm = RobustLLMCall(component="user_sim")

    async def generate(
        self,
        persona: PersonaCard,
        required_action: str,
        allowed_actions: List[str],
        retry: int = 0,
        api_retry: int = 0,
        *,
        messages: List[dict] | None = None,
        last_bot_utterance: str = "",
        turn_index: int = 1,
        slot_values: Dict[str, str] | None = None,
        has_prior_bot: bool = False,
        user_history: List[str] | None = None,
        user_memory: List[str] | None = None,
        questions_at_step: int = 0,
        planned_path_nodes: List[str] | None = None,
        current_state: str = "",
        path_user_action: str = "",
        path_next_node: str = "",
        path_utterance_hint: str = "",
        last_failed_utterance: str = "",
        last_fail_reason: str = "",
        instruction: object | None = None,
        target_knowledge_id: str = "",
    ) -> Dict[str, str | int]:
        planned = list(planned_path_nodes or [])
        probe_drive = PROBE_D10_DRIVE in planned
        probe_busy = PROBE_D9_BUSY in planned
        if probe_drive or probe_busy:
            from eval1.layer2.constraint_scenarios import is_driving_user

            probe_node = PROBE_D10_DRIVE if probe_drive else PROBE_D9_BUSY
            scenario_line = probe_user_line(probe_node)
            history = list(user_history or [])
            if not history and current_state in {"START", "F1"}:
                line = "是的，我是。" if probe_drive else "是的，我是负责人。"
                return {
                    "utterance": line,
                    "action": "comply",
                    "llm_connected": False,
                    "degraded": False,
                    "forced_retries": retry,
                    "utterance_source": "probe_script",
                }
            already_scenario = any(
                scenario_line in (u or "")
                or (probe_drive and is_driving_user(u or ""))
                or (probe_busy and "忙" in (u or ""))
                for u in history
            )
            if not already_scenario:
                return {
                    "utterance": scenario_line,
                    "action": "comply",
                    "llm_connected": False,
                    "degraded": False,
                    "forced_retries": retry,
                    "utterance_source": "probe_script",
                }

        style = PERSONA_STYLE.get(persona.persona_type.value, PERSONA_STYLE["cooperative"])
        context = UserContextMemory.from_dialogue(
            user_memory=user_memory,
            messages=messages,
            user_history=user_history,
        )
        sampled = self._sample_action(
            persona,
            required_action,
            allowed_actions,
            questions_at_step=questions_at_step,
            current_state=current_state,
            planned_path_nodes=planned_path_nodes or [],
            path_user_action=path_user_action,
        )
        path_driven = path_coverage_action(path_user_action, required_action, allowed_actions) is not None
        faq_step = ""
        if path_next_node == "FAQ_NORMAL" or (
            path_user_action == "ask_question" and "FAQ_NORMAL" in (planned_path_nodes or [])
        ):
            faq_step = faq_interrupt_flow_step(planned_path_nodes or [])
        faq_seeds = (
            ask_seeds_for_faq_step(
                instruction,
                faq_step,
                slot_values or {},
                target_knowledge_id=target_knowledge_id or "",
            )
            if faq_step
            else ()
        )
        path_hint = (
            enrich_path_utterance_hint(
                path_user_action or sampled,
                path_utterance_hint,
                next_node=path_next_node,
            )
            if path_driven
            else path_utterance_hint
        )
        if faq_step and path_user_action == "ask_question":
            seed_part = f"（可借鉴方向，勿照抄：{faq_seeds[0]}）" if faq_seeds else ""
            k_part = f"须覆盖知识点 {target_knowledge_id} 相关要点；" if target_knowledge_id else ""
            path_hint = (
                f"动作为 ask_question：结合 Bot 在 {faq_step} 刚说的内容、对话上下文和 Persona，"
                f"自主追问一句{k_part}{seed_part}"
            )
        tone_hint = build_persona_contextual_tone_hint(
            persona,
            action=path_user_action or sampled,
            current_state=current_state,
            last_bot_utterance=last_bot_utterance,
        )
        if tone_hint:
            path_hint = f"{path_hint}；{tone_hint}" if path_hint else tone_hint
        retry_feedback = ""
        if retry > 0 and last_fail_reason:
            retry_feedback = last_fail_reason
            if last_failed_utterance:
                retry_feedback += f"；勿重复：「{last_failed_utterance[:20]}」"

        llm_ret = await self._build_utterance_llm(
            persona,
            style,
            sampled,
            context=context,
            required_action=required_action,
            allowed_actions=allowed_actions,
            last_bot_utterance=last_bot_utterance,
            turn_index=turn_index,
            slot_values=slot_values or {},
            has_prior_bot=has_prior_bot,
            messages=messages or [],
            current_state=current_state,
            questions_at_step=questions_at_step,
            path_user_action=path_user_action,
            path_utterance_hint=path_hint,
            retry_feedback=retry_feedback,
            user_history=user_history or [],
            instruction=instruction,
        )
        scene = build_user_sim_scene(instruction, slot_values or {})
        utter = str(llm_ret.get("text", ""))
        llm_connected = bool(llm_ret.get("llm_connected", False))
        degraded = bool(llm_ret.get("degraded")) or not utter.strip()
        fsm_action = sampled
        max_validation_retry = self._validation_retry_limit(path_driven)

        if degraded:
            if api_retry < self._api_retry_limit():
                return await self.generate(
                    persona,
                    required_action,
                    allowed_actions,
                    retry=retry,
                    api_retry=api_retry + 1,
                    last_bot_utterance=last_bot_utterance,
                    turn_index=turn_index,
                    slot_values=slot_values,
                    has_prior_bot=has_prior_bot,
                    user_history=user_history,
                    user_memory=user_memory,
                    questions_at_step=questions_at_step,
                    current_state=current_state,
                    messages=messages,
                    planned_path_nodes=planned_path_nodes,
                    path_user_action=path_user_action,
                    path_next_node=path_next_node,
                    path_utterance_hint=path_hint,
                    last_failed_utterance=utter,
                    last_fail_reason="LLM未返回有效内容，请结合上下文与路径动作重新生成",
                    instruction=instruction,
                    target_knowledge_id=target_knowledge_id,
                )
            utter = self._shell_fallback(
                sampled,
                persona=persona,
                last_bot_utterance=last_bot_utterance,
                slot_values=slot_values or {},
                user_history=user_history or [],
                instruction=instruction,
            )
            return {
                "utterance": utter,
                "action": fsm_action,
                "forced_retries": retry,
                "llm_connected": False,
                "degraded": True,
                "utterance_source": "shell_fallback",
            }

        fail_reason = self._check_utterance(
            utter,
            required_action,
            sampled,
            persona=persona,
            user_history=user_history or [],
            last_bot=last_bot_utterance,
            scene=scene,
            path_driven=path_driven,
            current_state=current_state,
            messages=messages or [],
            instruction=instruction,
            slot_values=slot_values or {},
        )
        if fail_reason:
            if retry >= max_validation_retry:
                utter = self._shell_fallback(
                    sampled,
                    persona=persona,
                    last_bot_utterance=last_bot_utterance,
                    slot_values=slot_values or {},
                    user_history=user_history or [],
                    instruction=instruction,
                )
                return {
                    "utterance": utter,
                    "action": sampled,
                    "forced_retries": retry + 1,
                    "llm_connected": llm_connected,
                    "degraded": False,
                    "utterance_source": "shell_fallback",
                }
            return await self.generate(
                persona,
                required_action,
                allowed_actions,
                retry=retry + 1,
                api_retry=api_retry,
                last_bot_utterance=last_bot_utterance,
                turn_index=turn_index,
                slot_values=slot_values,
                has_prior_bot=has_prior_bot,
                user_history=user_history,
                user_memory=user_memory,
                questions_at_step=questions_at_step,
                current_state=current_state,
                messages=messages,
                planned_path_nodes=planned_path_nodes,
                path_user_action=path_user_action,
                path_next_node=path_next_node,
                path_utterance_hint=path_hint,
                last_failed_utterance=utter,
                last_fail_reason=fail_reason,
                instruction=instruction,
                target_knowledge_id=target_knowledge_id,
            )

        return {
            "utterance": utter,
            "action": fsm_action,
            "forced_retries": retry,
            "llm_connected": llm_connected,
            "degraded": False,
            "utterance_source": "llm",
        }

    def _validation_retry_limit(self, path_driven: bool) -> int:
        base = max(0, int(settings.action_verify_max_retry))
        if path_driven:
            return max(base, 4)
        return base

    def _api_retry_limit(self) -> int:
        return 2

    def _ensure_action_alignment(
        self,
        utterance: str,
        action: str,
        **_: object,
    ) -> str:
        """LLM 主路径：不在此处替换为模板句，校验失败则走 validation retry。"""
        return utterance

    def _check_utterance(
        self,
        utterance: str,
        required_action: str,
        sampled: str,
        *,
        persona: PersonaCard,
        user_history: List[str],
        last_bot: str,
        scene: UserSimScene | None = None,
        path_driven: bool = False,
        current_state: str = "",
        messages: List[dict] | None = None,
        instruction: object | None = None,
        slot_values: Dict[str, str] | None = None,
    ) -> str:
        bot_history = [
            str(m.get("content", ""))
            for m in (messages or [])
            if str(m.get("role", "")).lower() == "bot"
        ]
        leak = caller_role_leak_reason(
            utterance,
            last_bot=last_bot,
            bot_history=bot_history,
            current_state=current_state,
        )
        if leak:
            return leak
        stale = stale_identity_ack_reason(
            utterance,
            last_bot=last_bot,
            current_state=current_state,
        )
        if stale:
            return stale
        if scene and scene.forbidden_phrases:
            u = (utterance or "").strip()
            for fp in scene.forbidden_phrases:
                if fp in u:
                    return f"出现了与当前任务无关的「{fp}」"
        u = (utterance or "").strip()
        if re.search(r"\bXX\b|XX校区|XX培训", u):
            return "不要复读XX等占位符或编造校区名"
        if "哪个校区" in (last_bot or "") and re.search(r"XX|某校区", u):
            return "不要编造具体校区名，简单确认即可"
        if self._is_repeat(utterance, user_history, last_bot_utterance=last_bot):
            return "与之前说过的话或对方原话太像"
        if is_hollow_user_response(utterance, persona):
            return "回应过于敷衍，需用完整口语表达一个想法（禁止只回好/嗯/明白）"
        profile = build_instruction_profile(instruction, slot_values or {})
        if is_role_term_misuse(utterance, profile):
            return "勿把身份称呼（如骑手/负责人）当作话题回声，须针对对方刚说的业务内容回应"
        if is_instruction_label_leak(utterance):
            return "勿出现指令模块名（如 Role/Task/Call Flow），须用口语回应业务内容"
        if is_listen_only_ack(utterance, last_bot, action=sampled):
            return "对方已说明要点，须确认理解或表态，勿说「先听一下/您继续说」"
        if is_generic_persona_stub(utterance, last_bot, action=sampled):
            return "勿用 Persona 固定套话（如「说重点/还想确认一点」），须承接对方刚说的排名/拒单/天气等具体内容"
        if is_questioning_hollow_confirm(utterance, last_bot, persona, action=sampled):
            return "质疑型须针对排名/拒单/天气等具体词追问或确认，禁止空泛「还想确认一点/大体明白」"
        if is_impatient_hollow_response(utterance, last_bot, persona, action=sampled):
            return "急躁型须句短带催促感，且先点出对方刚说的关键词，禁止中性套话「还有别的吗」"
        if is_resistant_overly_cooperative(utterance, persona, action=sampled):
            return "抵触型可配合推进，但须带勉强/保留（行吧/但/得看情况），禁止热情「好的，明白了/会小心的」"
        if is_disconnected_user_response(utterance, last_bot):
            return "须先承接对方刚说的具体内容再表态，勿各说各话"
        if is_canned_minimal_utterance(utterance):
            return "勿使用通用模板句（如「这规则有点苛刻」），须结合Persona与对方刚说的话自主措辞"
        if contains_unnatural_phrasing(utterance):
            return "用了不自然的清单/系统用语"
        if not self._verify_action(
            utterance,
            required_action,
            sampled,
            persona=persona,
            strict=path_driven and sampled in {"comply", "confirm"},
        ):
            return f"未体现「{sampled}」动作语义"
        # 人格语气由 prompt 软引导；此处仅拦截系统用语与 reject/comply 矛盾
        if not verify_persona_tone(utterance, persona, sampled_action=sampled):
            return "动作与话术语义矛盾"
        phrase_reason = check_utterance_variety(utterance, user_history, persona=persona)
        if phrase_reason:
            return phrase_reason
        return ""

    async def _build_utterance_llm(
        self,
        persona: PersonaCard,
        style: Dict[str, str | float],
        action: str,
        *,
        context: UserContextMemory,
        required_action: str,
        allowed_actions: List[str],
        last_bot_utterance: str,
        turn_index: int,
        slot_values: Dict[str, str],
        has_prior_bot: bool,
        messages: List[dict],
        current_state: str,
        questions_at_step: int,
        path_user_action: str = "",
        path_utterance_hint: str = "",
        retry_feedback: str = "",
        user_history: List[str] | None = None,
        instruction: object | None = None,
    ) -> Dict[str, str | bool]:
        scene = build_user_sim_scene(instruction, slot_values)
        sys_prompt = build_user_sim_system_prompt(
            persona,
            scene=scene,
            context=context,
            current_state=current_state,
            allowed_actions=allowed_actions,
            required_action=required_action,
            questions_at_step=questions_at_step,
            messages=messages,
            sampled_action=action,
            path_user_action=path_user_action,
            path_utterance_hint=path_utterance_hint,
            instruction=instruction,
        )
        user_prompt = build_user_sim_user_prompt(
            persona=persona,
            scene=scene,
            context=context,
            sampled_action=action,
            turn_index=turn_index,
            last_bot_utterance=last_bot_utterance,
            has_prior_bot=has_prior_bot,
            current_state=current_state,
            path_user_action=path_user_action,
            path_utterance_hint=path_utterance_hint,
            retry_feedback=retry_feedback,
            user_history=user_history or [],
            instruction=instruction,
        )
        temp = float(style.get("temperature", settings.llm_temperature_sim))
        if retry_feedback:
            temp = min(0.95, temp + 0.08 * (1 + retry_feedback.count("勿重复")))

        dialogue_timeout = float(getattr(settings, "llm_dialogue_timeout_sec", 28.0))

        async def _primary() -> str:
            return await self._llm.chat(
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                model=settings.llm_model_fast,
                temperature=temp,
                attempts=3,
                timeout_s=dialogue_timeout,
            )

        text, status = await self._llm.call_with_fallback(
            primary_fn=_primary,
            fallback_value="",
            validator=lambda s: bool((s or "").strip()),
            max_retry=2,
            timeout=dialogue_timeout + 4.0,
            tag="user_sim",
        )
        text = str(text).strip()
        ok = status == "success" and bool(text)
        return {"text": text, "llm_connected": ok, "degraded": not ok}

    def _is_repeat(self, utterance: str, user_history: List[str], *, last_bot_utterance: str = "") -> bool:
        u = (utterance or "").strip()
        if not u:
            return True
        if user_history:
            if u == user_history[-1].strip():
                return True
            if user_history.count(u) >= 1:
                return True
            if len(u) >= 8 and any(u[:8] == h[:8] for h in user_history if len(h) >= 8):
                return True
        bot = (last_bot_utterance or "").strip()
        if bot and len(u) >= 6:
            if u in bot or bot in u:
                return True
            if len(bot) >= 8 and u[:8] == bot[:8]:
                return True
        return False

    def _verify_action(
        self,
        utterance: str,
        required_action: str,
        sampled: str,
        *,
        persona: PersonaCard,
        strict: bool = False,
    ) -> bool:
        return self._action_detector.verify_for_sampled(utterance, sampled, strict=strict)

    def _sample_action(
        self,
        persona: PersonaCard,
        required_action: str,
        allowed_actions: List[str],
        *,
        questions_at_step: int = 0,
        current_state: str = "",
        planned_path_nodes: List[str] | None = None,
        path_user_action: str = "",
    ) -> str:
        driven = path_coverage_action(path_user_action, required_action, allowed_actions)
        if driven:
            return driven

        path_has_reject = any(n in (planned_path_nodes or []) for n in {"OBJECTION", "F3_RETAIN"})
        if required_action == "advance_flow":
            p = persona.persona_type
            if questions_at_step >= 2:
                target = "comply"
            elif p == PersonaType.QUESTIONING and questions_at_step == 0 and any(
                n == "FAQ_NORMAL" for n in (planned_path_nodes or [])
            ):
                target = "ask_question"
            elif p == PersonaType.RESISTANT and current_state in {"START", "F1"} and path_has_reject:
                target = "reject" if random.random() < 0.5 else "comply"
            elif p == PersonaType.RESISTANT and current_state in {"F2", "F3", "F4"} and path_has_reject:
                target = "reject" if questions_at_step == 0 and random.random() < 0.35 else "comply"
            elif p == PersonaType.IGNORANT and questions_at_step == 0 and any(
                n == "FAQ_NORMAL" for n in (planned_path_nodes or [])
            ):
                target = "ask_question" if random.random() < 0.55 else "comply"
            elif p == PersonaType.OFF_TOPIC and any(n == "FAQ_OOB" for n in (planned_path_nodes or [])):
                target = "off_topic" if random.random() < 0.35 else "comply"
            else:
                target = "comply"
        elif required_action == "resolve_objection":
            target = "reject" if questions_at_step < 2 else "comply"
        elif required_action == "close_dialogue":
            target = "confirm"
        elif required_action == "terminate":
            target = "hangup"
        else:
            target = "comply"

        if target not in allowed_actions:
            target = allowed_actions[0] if allowed_actions else "comply"

        noise = random.random()
        if target == "comply" and "off_topic" in allowed_actions and noise < float(persona.off_topic_prob):
            return "off_topic"
        if target == "comply" and "reject" in allowed_actions and noise < float(persona.interruption_prob) * 0.5:
            return "reject"
        return target

    def _shell_fallback(
        self,
        sampled_action: str,
        *,
        persona: PersonaCard,
        last_bot_utterance: str,
        slot_values: Dict[str, str] | None = None,
        user_history: List[str] | None = None,
        instruction: object | None = None,
    ) -> str:
        """Last resort only: _PERSONA_SHELLS via build_minimal_action_utterance."""
        return self._minimal_fallback(
            sampled_action,
            persona=persona,
            last_bot_utterance=last_bot_utterance,
            context=UserContextMemory(),
            slot_values=slot_values,
            user_history=user_history,
            instruction=instruction,
        )

    def _minimal_fallback(
        self,
        sampled_action: str,
        *,
        persona: PersonaCard,
        last_bot_utterance: str,
        context: UserContextMemory,
        slot_values: Dict[str, str] | None = None,
        user_history: List[str] | None = None,
        instruction: object | None = None,
    ) -> str:
        """Last-resort stub when LLM + validation retries are exhausted."""
        scene = build_user_sim_scene(instruction, slot_values or {})
        user_name = scene.user_name
        history = list(user_history or [])
        turn = len(history)

        def _fresh(line: str) -> str:
            if line not in history and not check_utterance_variety(line, history, persona=persona):
                return line
            return f"{line[:-1]}…" if line.endswith("。") else line

        if sampled_action in {"reject", "ask_question", "off_topic", "hangup", "confirm"}:
            return _fresh(
                build_minimal_action_utterance(
                    sampled_action,
                    turn=turn,
                    user_history=history,
                    persona=persona,
                    last_bot_utterance=last_bot_utterance,
                    instruction=instruction,
                    slot_values=slot_values,
                    forbidden_phrases=scene.forbidden_phrases,
                )
            )

        if sampled_action == "comply":
            profile = build_instruction_profile(instruction, slot_values)
            bot = (last_bot_utterance or "").strip()
            if user_name and turn == 0:
                return _fresh(f"是我，{user_name}。")
            if turn == 0 and any(k in bot for k in ("负责人", "是您", "请问您")):
                for line in ("是的，我是。", "对，您说。", "嗯，我负责这块。"):
                    if line not in history:
                        return _fresh(line)
            return _fresh(
                build_minimal_action_utterance(
                    "comply",
                    turn=turn,
                    user_history=history,
                    persona=persona,
                    last_bot_utterance=last_bot_utterance,
                    instruction=instruction,
                    slot_values=slot_values,
                    forbidden_phrases=scene.forbidden_phrases,
                )
            )

        return _fresh("嗯。")
