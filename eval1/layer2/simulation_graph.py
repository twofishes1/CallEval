from __future__ import annotations

from time import perf_counter
from typing import Any, Dict, List

from eval1.layer2.action_detector import ActionDetector, is_retain_success, looks_like_acknowledgment
from eval1.layer2.bot_repeat_guard import (
    is_busy_or_refuse_user,
    is_semantically_repetitive,
    pick_non_repeating,
)
from eval1.layer2.dialogue_trace import DialogueTrace, TurnTrace
from eval1.layer2.instruction_grounding import (
    build_closing_reply_alts,
    build_hangup_reply_alts,
    build_step_utterance_alts,
    infer_closing_tone,
    is_bad_closing_response,
)
from eval1.layer2.action_detector import is_oob_scope_question
from eval1.layer2.constraint_scenarios import (
    build_driving_hangup_alts,
    is_driving_user,
    resolve_scenario_reply,
)
from eval1.layer2.instruction_injection import (
    advance_f4_speech_index,
    compress_step_to_utterance,
    f4_coverage_summary,
    instruction_f4_is_delivery_split,
    pick_f4_next_utterance,
    pick_f4_post_ack,
    sync_f4_completion,
    update_f4_delivery,
    pick_flow_step_utterance,
    sanitize_bot_output,
)
from eval1.layer2.robust_llm import RobustLLMCall
from eval1.layer2.user_context_memory import UserContextMemory, merge_user_turn
from eval1.layer2.user_knowledge import extract_new_knowledge
from langgraph.graph import END, StateGraph
from eval1.layer1.models import ExecutionPlan
from eval1.layer2.bot_wrapper import BotWrapper
from eval1.layer2.context_builder import ContextBuilder
from eval1.layer2.dst import DST
from eval1.layer2.goal_fsm import GoalFSM
from eval1.layer2.mandatory_scripts import (
    get_mandatory_bot_utterance,
    is_mandatory_script_exempt,
)
from eval1.layer1.path_probe import is_probe_node
from eval1.layer2.path_user_driver import PATH_COVERAGE_ACTIONS, infer_path_user_action, next_path_node
from eval1.layer2.persona import PERSONA_REGISTRY, PersonaCard, PersonaType
from eval1.layer2.state import DialogueState, make_initial_state
from eval1.layer2.termination import TerminationChecker
from eval1.layer2.user_simulator import UserSimulatorAgent


class SimulationGraph:
    """Layer2 main graph implemented with LangGraph StateGraph."""

    def __init__(self) -> None:
        self.user_sim = UserSimulatorAgent()
        self.bot = BotWrapper()
        self.ctx = ContextBuilder()
        self.dst = DST()
        self.term = TerminationChecker()
        self.action_detector = ActionDetector()
        self.robust_llm = RobustLLMCall(component="simulation")
        self.graph = self._build_simulation_graph()
    async def run_dialogue(
        self,
        plan: ExecutionPlan,
        persona: PersonaCard,
        instruction=None,
    ) -> Dict[str, Any]:
        path_nodes = list(plan.path.nodes or [])
        fsm = GoalFSM.from_path(path_nodes)
        state = make_initial_state(
            instruction=instruction,
            plan=plan,
            fsm=fsm,
            persona_type=persona.persona_type.value,
            tone_modifier=plan.tone_modifier,
        )
        state = await self.graph.ainvoke(
            state,
            config={"recursion_limit": max(120, int(plan.max_turns) * 6)},
        )
        covered_nodes = list(state.get("covered_nodes") or [])
        bot_action_log = list((state.get("bot_state") or {}).get("bot_action_log") or [])
        state["path_covered"] = self.verify_path_coverage(path_nodes, covered_nodes)
        state["flow_adherence_rate"] = fsm.get_flow_adherence_rate(
            covered_nodes,
            bot_action_log=bot_action_log,
        )
        bot_msgs = [str(m.get("content", "")) for m in (state.get("messages") or []) if str(m.get("role", "")) == "bot"]
        opening_line = str(getattr(instruction, "opening_line", "") or "").strip() if instruction else ""
        opening_line_match = bool(opening_line and bot_msgs and bot_msgs[0].strip() == opening_line)
        repetitive_bot_count = max(0, len(bot_msgs) - len(set(bot_msgs)))
        return {
            "messages": state["messages"],
            "covered_nodes": covered_nodes,
            "flow_adherence_rate": float(state.get("flow_adherence_rate", 0.0)),
            "termination_reason": str(state.get("termination_reason") or "max_turns"),
            "path_covered": bool(state.get("path_covered")),
            "hard_violation": bool(state.get("hard_violation")),
            "forced_action_retry_count": int(state.get("forced_action_retry_count", 0)),
            "user_llm_connected": bool(state.get("user_llm_connected", False)),
            "bot_llm_connected": bool(state.get("bot_llm_connected", False)),
            "violations": list(state.get("violations") or []),
            "fsm_log": [*state.get("fsm_log", []), *covered_nodes],
            "opening_line_match": opening_line_match,
            "repetitive_bot_count": repetitive_bot_count,
            "bot_state": dict(state.get("bot_state") or {}),
            "bot_state_log": list(state.get("bot_state_log") or []),
            "trace": (state.get("dialogue_trace") or DialogueTrace()).to_dict(),
            "unknown_action_count": int(getattr(state.get("dialogue_trace"), "unknown_action_count", 0)),
            "degraded_call_count": len(list(state.get("degraded_calls") or [])),
            "pending_review": bool(state.get("pending_review")),
        }
    def _build_simulation_graph(self):
        graph = StateGraph(DialogueState)
        graph.add_node("init_turn", self._init_turn_node)
        graph.add_node("user_sim", self._user_sim_node)
        graph.add_node("bot", self._bot_node)
        graph.set_entry_point("init_turn")
        graph.add_conditional_edges(
            "init_turn",
            self._route_init,
            {"user_sim": "user_sim", "bot": "bot", "end": END},
        )
        graph.add_edge("user_sim", "bot")
        graph.add_conditional_edges(
            "bot",
            self._route_after_bot,
            {"continue": "init_turn", "end": END},
        )
        return graph.compile()

    async def _init_turn_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        should_stop, reason = self.term.check(state)
        if should_stop:
            return {"should_terminate": True, "termination_reason": reason or "max_turns"}
        return {"should_terminate": False}

    def _route_init(self, state: Dict[str, Any]) -> str:
        if bool(state.get("should_terminate")):
            return "end"
        # Outbound call: Bot speaks opening line before user first reply.
        if not (state.get("messages") or []):
            return "bot"
        return "user_sim"

    async def _user_sim_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        turn_started = perf_counter()
        fsm = state["goal_fsm"]
        plan = state["plan"]
        turn = int(state.get("turn_count", 0)) + 1
        covered_nodes = list(state.get("covered_nodes") or [fsm.current_state])
        persona = PERSONA_REGISTRY[PersonaType(str(state.get("persona_type", "cooperative")))]
        messages = list(state.get("messages") or [])
        trace: DialogueTrace = state.get("dialogue_trace") or DialogueTrace()
        turn_trace = TurnTrace(
            turn_index=turn,
            fsm_state_before=fsm.current_state,
            fsm_state_after=fsm.current_state,
        )
        last_bot = ""
        for m in reversed(messages):
            if str(m.get("role", "")) == "bot":
                last_bot = str(m.get("content", ""))
                break
        user_history = [
            str(m.get("content", ""))
            for m in messages
            if str(m.get("role", "")) == "user"
        ]
        bot_state = dict(state.get("bot_state") or {})
        slot_values = dict(bot_state.get("slot_values") or {})
        if plan.variable_values:
            for k, v in (plan.variable_values or {}).items():
                slot_values[str(k)] = str(v)
        step_question_state = str(state.get("step_question_state") or "")
        questions_at_step = int(state.get("step_questions", 0))
        if step_question_state != fsm.current_state:
            questions_at_step = 0

        required = fsm.get_required_action_for_path()
        allowed = fsm.get_allowed_user_actions()
        path_user_action, path_next_node, path_utterance_hint = infer_path_user_action(fsm)
        if (
            persona.persona_type == PersonaType.QUESTIONING
            and fsm.current_state.startswith("F")
            and questions_at_step == 0
            and "ask_question" in allowed
            and path_user_action == "comply"
            and path_next_node not in {"FAQ_NORMAL", "FAQ_OOB"}
        ):
            path_user_action = "ask_question"
            path_utterance_hint = "就Bot刚说的规则追问一句依据、后果或怎么算"
        instruction = state.get("instruction")
        path_nodes = list(plan.path.nodes or fsm.path_nodes or [])
        target_k = str(getattr(plan.path, "target_knowledge_id", "") or "")
        gen = await self.user_sim.generate(
            persona,
            required,
            allowed_actions=allowed,
            messages=messages,
            last_bot_utterance=last_bot,
            turn_index=turn,
            slot_values=slot_values,
            has_prior_bot=bool(last_bot),
            user_history=user_history,
            user_memory=list(state.get("user_memory") or []),
            questions_at_step=questions_at_step,
            current_state=fsm.current_state,
            planned_path_nodes=path_nodes,
            path_user_action=path_user_action,
            path_next_node=path_next_node,
            path_utterance_hint=path_utterance_hint,
            instruction=instruction,
            target_knowledge_id=target_k,
        )
        user_utter = str(gen.get("utterance", ""))

        path_default = (
            path_user_action
            if path_user_action in allowed and path_user_action in PATH_COVERAGE_ACTIONS
            else ""
        )
        action_result = await self.action_detector.detect(
            user_utter,
            context={
                "fsm_state": fsm.current_state,
                "allowed_actions": allowed,
                "path_hint": path_user_action,
            },
            default="",
        )
        user_action = action_result.to_fsm_action()
        turn_trace.user_utterance = user_utter
        turn_trace.detected_action = user_action
        turn_trace.action_confidence = float(action_result.confidence)
        turn_trace.action_source = str(action_result.source)
        turn_trace.action_needs_review = bool(action_result.needs_review)
        turn_trace.retain_success = bool(action_result.retain_success)

        user_memory = merge_user_turn(
            UserContextMemory.from_legacy(list(state.get("user_memory") or [])),
            user_utter,
            user_action if user_action != "unknown" else "comply",
        )
        if user_action in {"ask_question", "off_topic"}:
            questions_at_step += 1
            step_question_state = fsm.current_state
        elif user_action in {"comply", "confirm"}:
            questions_at_step = 0
            step_question_state = ""
        messages.append({"turn": len(messages) + 1, "role": "user", "content": user_utter})
        turn_trace.duration_ms = int((perf_counter() - turn_started) * 1000)
        trace.append(turn_trace)
        return {
            "messages": messages,
            "user_memory": user_memory,
            "last_user_action": user_action,
            "last_action_confidence": float(action_result.confidence),
            "last_action_source": str(action_result.source),
            "last_action_needs_review": bool(action_result.needs_review),
            "pending_review": bool(action_result.needs_review),
            "step_questions": questions_at_step,
            "step_question_state": step_question_state,
            "forced_action_retry_count": int(state.get("forced_action_retry_count", 0)) + int(gen.get("forced_retries", 0)),
            "user_llm_connected": bool(state.get("user_llm_connected", True)) and bool(gen.get("llm_connected", False)),
            "dialogue_trace": trace,
            "_current_turn_trace": turn_trace,
        }

    async def _bot_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        bot_started = perf_counter()
        fsm = state["goal_fsm"]
        plan = state["plan"]
        instruction = state.get("instruction")
        turn = int(state.get("turn_count", 0)) + 1
        user_action = str(state.get("last_user_action") or "unknown")
        action_confidence = float(state.get("last_action_confidence") or 0.0)
        retain_ok = bool(getattr(state.get("_current_turn_trace"), "retain_success", False))
        covered_nodes = list(state.get("covered_nodes") or [fsm.current_state])
        persona = PERSONA_REGISTRY[PersonaType(str(state.get("persona_type", "cooperative")))]
        consecutive_reject = int(state.get("consecutive_reject", 0))
        stalled_rounds = int(state.get("stalled_rounds", 0))
        prev_pointer = int(fsm.pointer)
        user_memory = list(state.get("user_memory") or [])
        trace: DialogueTrace = state.get("dialogue_trace") or DialogueTrace()
        turn_trace: TurnTrace | None = state.get("_current_turn_trace")
        degraded = list(state.get("degraded_calls") or [])
        bot_history = [
            str(m.get("content", ""))
            for m in (state.get("messages") or [])
            if str(m.get("role", "")) == "bot"
        ]
        is_first_bot_turn = len(bot_history) == 0
        is_opening_only = is_first_bot_turn and not any(
            str(m.get("role", "")) == "user" for m in (state.get("messages") or [])
        )
        last_user_utterance = ""
        for m in reversed(state.get("messages") or []):
            if str(m.get("role", "")) == "user":
                last_user_utterance = str(m.get("content", ""))
                break

        fsm_state_before_user = str(fsm.current_state)
        fsm_moved = False
        fsm_reason = "no_user_turn" if is_opening_only else "unknown_action_hold"
        effective_action = user_action
        if (
            not is_opening_only
            and last_user_utterance
            and user_action == "unknown"
            and looks_like_acknowledgment(last_user_utterance)
        ):
            effective_action = "comply"
            fsm_reason = "acknowledgment_as_comply"

        path_user_action, path_next_node, _ = infer_path_user_action(fsm)
        if (
            path_next_node == "FAQ_OOB"
            and last_user_utterance
            and effective_action in {"ask_question", "unknown", "comply"}
            and (path_user_action == "off_topic" or is_oob_scope_question(last_user_utterance))
        ):
            effective_action = "off_topic"
            fsm_reason = "path_oob_reroute"

        if not is_opening_only and last_user_utterance and effective_action != "unknown":
            reject_count = consecutive_reject + (1 if effective_action == "reject" else 0)
            tr = fsm.try_transition(
                effective_action,
                retain_success=retain_ok or is_retain_success(last_user_utterance),
                consecutive_reject=reject_count,
                reject_limit=int(persona.consecutive_reject_limit),
            )
            fsm_moved = bool(tr.moved)
            fsm_reason = str(tr.reason or fsm_reason)
            if tr.moved and tr.to_state not in covered_nodes:
                covered_nodes.append(tr.to_state)
            if effective_action == "reject":
                consecutive_reject += 1
            elif effective_action in {"comply", "confirm"} or retain_ok or is_retain_success(last_user_utterance):
                consecutive_reject = 0
        elif (
            not is_opening_only
            and last_user_utterance
            and not fsm_moved
            and stalled_rounds >= 2
            and effective_action not in {"reject", "ask_question", "off_topic"}
        ):
            tr = fsm.try_transition(
                "comply",
                retain_success=True,
                consecutive_reject=consecutive_reject,
                reject_limit=int(persona.consecutive_reject_limit),
            )
            if tr.moved:
                fsm_moved = True
                fsm_reason = "stall_recovery"
                if tr.to_state not in covered_nodes:
                    covered_nodes.append(tr.to_state)
                consecutive_reject = 0
        elif (
            not is_opening_only
            and not fsm.is_terminal()
            and stalled_rounds >= 4
            and int(fsm.pointer) == prev_pointer
        ):
            path_has_probe = any(is_probe_node(n) for n in fsm.path_nodes)
            if path_has_probe:
                nxt_i = int(fsm.pointer) + 1
                if nxt_i < len(fsm.path_nodes):
                    fsm.pointer = nxt_i
                    fsm.current_state = fsm.path_nodes[nxt_i]
                    fsm_moved = True
                    fsm_reason = "stall_advance_probe_path"
                    if fsm.current_state not in covered_nodes:
                        covered_nodes.append(fsm.current_state)
                    stalled_rounds = 0
            else:
                idx = fsm._next_main_flow_index()  # noqa: SLF001
                if idx is not None and idx > int(fsm.pointer):
                    fsm.pointer = idx
                    fsm.current_state = fsm.path_nodes[idx]
                    fsm_moved = True
                    fsm_reason = "stall_skip_to_flow"
                    if fsm.current_state not in covered_nodes:
                        covered_nodes.append(fsm.current_state)
                    stalled_rounds = 0
                elif fsm.current_state not in {"CLOSING", "END"}:
                    fsm.go_to_final()
                    fsm_moved = True
                    fsm_reason = "stall_force_close"
                    if "END" not in covered_nodes:
                        covered_nodes.append("END")
                    stalled_rounds = 0
        elif user_action == "unknown" and turn_trace:
            fsm_reason = "unknown_action_hold"
        # Opening delivered at START → jump to first flow step on path.
        if fsm.current_state == "START" and bot_history:
            idx = fsm._next_main_flow_index(0)  # noqa: SLF001
            if idx is not None:
                fsm.pointer = idx
                fsm.current_state = fsm.path_nodes[idx]
                if fsm.current_state not in covered_nodes:
                    covered_nodes.append(fsm.current_state)

        bot_state = dict(state.get("bot_state") or {})
        sync_f4_completion(bot_state, bot_history)
        slot_values = dict(bot_state.get("slot_values") or {})
        if plan.variable_values:
            for k, v in (plan.variable_values or {}).items():
                slot_values[str(k)] = str(v)
        bot_state["slot_values"] = slot_values

        scenario_force_end = False
        scenario_reply = None
        if last_user_utterance.strip() and not is_opening_only:
            scenario_reply = resolve_scenario_reply(
                instruction,
                last_user_utterance=last_user_utterance,
                bot_state=bot_state,
                current_state=fsm.current_state,
                path_nodes=fsm.path_nodes,
            )

        current_step_text = self._get_current_step_text(
            fsm.current_state, instruction, last_user_utterance=last_user_utterance, slot_values=slot_values
        )
        if fsm.current_state == "F4" and "f4_speech_index" not in bot_state:
            bot_state["f4_speech_index"] = 0
        bot_state["current_step_id"] = str(fsm.current_state)
        bot_state["current_step_text"] = str(current_step_text)
        from eval1.layer2.instruction_injection import substitute_variables

        opening_line = substitute_variables(
            str(getattr(instruction, "opening_line", "") or "").strip(),
            slot_values,
        )
        used_llm = True
        used_mandatory = False
        if scenario_reply:
            bot_utter = scenario_reply.text
            bot_llm_connected = bool(state.get("bot_llm_connected", True))
            used_llm = False
            used_mandatory = True
            bot_action = "constraint_scenario"
            if scenario_reply.mark_busy_briefed:
                bot_state["busy_briefed"] = True
            if scenario_reply.force_end:
                scenario_force_end = True
                for probe in fsm.path_nodes:
                    if is_probe_node(probe) and probe not in covered_nodes:
                        covered_nodes.append(probe)
                if fsm.current_state not in {n for n in fsm.path_nodes if is_probe_node(n)}:
                    for probe in fsm.path_nodes:
                        if is_probe_node(probe):
                            tr_probe = fsm.go_to_node(probe, reason="scenario_probe_visit")
                            if tr_probe.moved and probe not in covered_nodes:
                                covered_nodes.append(probe)
                            break
                if "CLOSING" in fsm.path_nodes and fsm.current_state not in {"CLOSING", "END"}:
                    tr_close = fsm.go_to_node("CLOSING", reason="scenario_hangup_closing")
                    if tr_close.moved and "CLOSING" not in covered_nodes:
                        covered_nodes.append("CLOSING")
                fsm.go_to_final()
                if "END" not in covered_nodes:
                    covered_nodes.append("END")
        elif is_first_bot_turn and opening_line:
            bot_utter = opening_line
            bot_llm_connected = bool(state.get("bot_llm_connected", True))
            used_llm = False
            rider_name = str(slot_values.get("rider_name", "")).strip()
            if rider_name and rider_name in opening_line:
                bot_state["name_used"] = True
        elif str(fsm.current_state).startswith("op::") and current_step_text:
            bot_utter = current_step_text
            bot_llm_connected = bool(state.get("bot_llm_connected", True))
            used_llm = False
            used_mandatory = True
            bot_action = "op_guide"
        elif any(is_probe_node(n) for n in fsm.path_nodes) and (
            fsm.current_state == "F1" or str(fsm.current_state).startswith("branch::")
        ) and any(is_probe_node(n) for n in fsm.planned_next_nodes(limit=6)):
            bot_utter = "好的，您请说。"
            bot_llm_connected = bool(state.get("bot_llm_connected", True))
            used_llm = False
            used_mandatory = True
            bot_action = "probe_pace"
        elif fsm.current_state == "F4" and instruction_f4_is_delivery_split(
            instruction, current_step_text, slot_values
        ):
            bot_state["f4_entered"] = True
            f4_cov = f4_coverage_summary(bot_state, bot_history)
            if not f4_cov.get("complete"):
                bot_utter = pick_f4_next_utterance(
                    bot_state, current_step_text, slots=slot_values, instruction=instruction
                )
            else:
                bot_utter = pick_f4_post_ack(bot_history, attempt=stalled_rounds)
            bot_llm_connected = bool(state.get("bot_llm_connected", True))
            used_llm = False
        elif fsm.current_state == "CLOSING":
            closing_action = effective_action if effective_action != "unknown" else user_action
            closing_tone = infer_closing_tone(
                last_user_utterance=last_user_utterance,
                user_action=closing_action,
                consecutive_reject=consecutive_reject,
                dialogue_history=list(state.get("messages") or []),
                covered_nodes=covered_nodes,
            )
            closing_alts = build_closing_reply_alts(
                instruction, closing_tone, last_user_utterance=last_user_utterance
            )
            bot_ret = await self.bot.reply(
                instruction=instruction,
                instruction_summary=plan.path.description,
                current_step_text=current_step_text,
                bot_state=bot_state,
                dialogue_history=list(state.get("messages") or []),
                current_state=fsm.current_state,
                last_user_utterance=last_user_utterance,
                user_action=closing_action,
                stalled_rounds=stalled_rounds,
                closing_tone=closing_tone,
            )
            bot_utter = str(bot_ret.get("text", ""))
            if hasattr(self.bot, "normalize_utterance"):
                bot_utter = self.bot.normalize_utterance(bot_utter, bot_state)
            else:
                bot_utter = sanitize_bot_output(bot_utter)
            bot_llm_connected = bool(state.get("bot_llm_connected", True)) and bool(
                bot_ret.get("llm_connected", False)
            )
            if bot_ret.get("degraded"):
                degraded.append("bot_reply")
            if is_bad_closing_response(bot_utter, closing_tone):
                bot_utter = pick_non_repeating(closing_alts, bot_history, attempt=stalled_rounds)
                used_llm = False
            elif self._is_repetitive(bot_utter, bot_history, current_state=fsm.current_state):
                bot_utter = pick_non_repeating(closing_alts, bot_history, attempt=stalled_rounds)
                used_llm = False
            else:
                used_llm = True
        elif fsm.current_state == "OBJ_FINAL":
            closing_alts = build_closing_reply_alts(
                instruction, "refused", last_user_utterance=last_user_utterance
            )
            bot_utter = pick_non_repeating(closing_alts, bot_history, attempt=stalled_rounds)
            bot_llm_connected = bool(state.get("bot_llm_connected", True))
            used_llm = False
        elif fsm.current_state == "FAQ_OOB":
            from eval1.layer2.instruction_grounding import build_instruction_grounding

            boundary = build_instruction_grounding(instruction, slot_values).boundary_phrase
            bot_utter = pick_non_repeating(
                [boundary, *build_hangup_reply_alts(instruction)],
                bot_history,
                attempt=stalled_rounds,
            )
            bot_llm_connected = bool(state.get("bot_llm_connected", True))
            used_llm = False
        elif fsm.is_terminal():
            bot_utter = ""
            bot_llm_connected = bool(state.get("bot_llm_connected", True))
            used_llm = False
        else:
            used_mandatory = False
            mandatory_line = get_mandatory_bot_utterance(
                instruction,
                fsm.current_state,
                bot_state,
                planned_nodes=list(plan.path.nodes or []),
                slots=slot_values,
            )
            if mandatory_line:
                bot_utter = mandatory_line
                bot_llm_connected = bool(state.get("bot_llm_connected", True))
                used_llm = False
                used_mandatory = True
            else:
                bot_ret = await self.bot.reply(
                    instruction=instruction,
                    instruction_summary=plan.path.description,
                    current_step_text=current_step_text,
                    bot_state=bot_state,
                    dialogue_history=list(state.get("messages") or []),
                    current_state=fsm.current_state,
                    last_user_utterance=last_user_utterance,
                    user_action=effective_action if effective_action != "unknown" else user_action,
                    stalled_rounds=stalled_rounds,
                )
                bot_utter = str(
                    bot_ret.get(
                        "text",
                        pick_flow_step_utterance(
                            fsm.current_state, current_step_text, bot_state, slots=slot_values
                        ),
                    )
                )
                if hasattr(self.bot, "normalize_utterance"):
                    bot_utter = self.bot.normalize_utterance(bot_utter, bot_state)
                else:
                    bot_utter = sanitize_bot_output(bot_utter)
                bot_llm_connected = bool(state.get("bot_llm_connected", True)) and bool(bot_ret.get("llm_connected", False))
                if bot_ret.get("degraded"):
                    degraded.append("bot_reply")
                if self._is_repetitive(bot_utter, bot_history, current_state=fsm.current_state):
                    if is_driving_user(last_user_utterance):
                        bot_utter = pick_non_repeating(
                            build_driving_hangup_alts(instruction),
                            bot_history,
                            attempt=stalled_rounds,
                        )
                    elif is_busy_or_refuse_user(last_user_utterance):
                        bot_utter = pick_non_repeating(
                            build_hangup_reply_alts(instruction, last_user_utterance=last_user_utterance),
                            bot_history,
                            attempt=stalled_rounds,
                        )
                    else:
                        bot_utter = self._fallback_step_utterance(
                            instruction,
                            current_step_text,
                            fsm.current_state,
                            slot_values,
                            bot_history=bot_history,
                            bot_state=bot_state,
                            attempt=stalled_rounds,
                        )
                    used_llm = False
                busy_streak = int(bot_state.get("user_busy_streak") or 0)
                if is_busy_or_refuse_user(last_user_utterance):
                    busy_streak += 1
                elif user_action in {"comply", "confirm"}:
                    busy_streak = 0
                bot_state["user_busy_streak"] = busy_streak
                if busy_streak >= 2 and is_busy_or_refuse_user(last_user_utterance):
                    bot_utter = pick_non_repeating(
                        ["好的，不打扰您了，再见。", *build_hangup_reply_alts(instruction)],
                        bot_history,
                        attempt=busy_streak,
                    )
        bot_action = "opening_line" if is_first_bot_turn and opening_line else "step_response"
        if used_mandatory:
            bot_action = "mandatory_script"
        if fsm.current_state == "F4" and not used_llm and instruction_f4_is_delivery_split(
            instruction, current_step_text, slot_values
        ):
            bot_action = (
                "f4_part"
                if not f4_coverage_summary(bot_state, bot_history).get("complete")
                else "f4_ack"
            )
        if fsm.current_state == "F4" and bot_utter and bot_action == "f4_part" and instruction_f4_is_delivery_split(
            instruction, current_step_text, slot_values
        ):
            update_f4_delivery(bot_state, bot_utter)
            advance_f4_speech_index(bot_state)
        elif (
            not used_llm
            and not (is_first_bot_turn and opening_line)
            and bot_action not in {"f4_part", "f4_ack"}
        ):
            bot_action = "dedupe_fallback"
        bot_state["last_bot_utterance"] = bot_utter
        guard = [str(x) for x in list(bot_state.get("repeat_guard_window") or [])]
        guard.append(bot_utter)
        bot_state["repeat_guard_window"] = guard[-4:]
        action_log = [str(x) for x in list(bot_state.get("bot_action_log") or [])]
        action_log.append(f"T{turn}:{bot_action}:{fsm.current_state}")
        bot_state["bot_action_log"] = action_log[-20:]
        used_knowledge = [str(x) for x in list(bot_state.get("used_knowledge_ids") or [])]
        if fsm.current_state in {"FAQ_NORMAL", "FAQ_OOB"}:
            used_knowledge.append(fsm.current_state)
        bot_state["used_knowledge_ids"] = used_knowledge[-10:]
        bot_state_log = list(state.get("bot_state_log") or [])
        bot_state_log.append(dict(bot_state))
        bot_state_log = bot_state_log[-30:]
        messages = list(state.get("messages") or [])
        bot_message_turn = len(messages) + 1 if bot_utter else len(messages)
        if bot_utter:
            messages.append({"turn": bot_message_turn, "role": "bot", "content": bot_utter})

        user_memory = await extract_new_knowledge(bot_utter, user_memory)

        violations = list(state.get("violations") or [])
        is_opening_utterance = bool(is_first_bot_turn and opening_line)
        is_f4_delivery = bool(fsm.current_state == "F4" and bot_action == "f4_part")
        is_mandatory_script = bool(bot_action == "mandatory_script") or is_mandatory_script_exempt(bot_utter)
        new_violations = self.dst.check_constraints(
            bot_utter,
            turn_index=bot_message_turn,
            instruction=instruction,
            fsm=fsm,
            is_opening_line=is_opening_utterance,
            is_f4_delivery=is_f4_delivery,
            is_mandatory_script=is_mandatory_script,
        )
        if new_violations:
            violations.extend(new_violations)

        required = fsm.get_required_action_for_path()
        closing_action = effective_action if effective_action != "unknown" else user_action
        if fsm.current_state == "CLOSING" and bot_utter:
            if fsm_state_before_user == "CLOSING" and closing_action in {"confirm", "comply"}:
                fsm.go_to_final()
            elif fsm_state_before_user != "CLOSING":
                fsm.go_to_final()
            if fsm.is_terminal() and "END" not in covered_nodes:
                covered_nodes.append("END")
            stalled_rounds = 0
        elif fsm.is_terminal():
            if "END" not in covered_nodes:
                covered_nodes.append("END")
            stalled_rounds = 0
        elif int(fsm.pointer) == prev_pointer:
            stalled_rounds += 1
        else:
            stalled_rounds = 0

        obj_final_closed = False
        if fsm.current_state == "OBJ_FINAL" and bot_utter:
            if "OBJ_FINAL" not in covered_nodes:
                covered_nodes.append("OBJ_FINAL")
            fsm.go_to_final()
            if "END" not in covered_nodes:
                covered_nodes.append("END")
            obj_final_closed = True
            stalled_rounds = 0

        path_covered = self.verify_path_coverage(list(plan.path.nodes or []), covered_nodes)
        flow_rate = fsm.get_flow_adherence_rate(
            covered_nodes,
            bot_action_log=list(bot_state.get("bot_action_log") or []),
        )
        hard_violation = bool(state.get("hard_violation")) or any(
            v.get("violation_type") == "hard_boundary" for v in new_violations
        )
        if obj_final_closed:
            termination_reason = "user_refused"
            should_stop = True
        elif scenario_force_end:
            termination_reason = "hangup"
            should_stop = True
        else:
            termination_reason = self._termination_priority(
                hard_violation=hard_violation,
                user_action=user_action if user_action != "unknown" else "comply",
                goal_achieved=fsm.is_goal_achieved(),
                user_refused=str(state.get("termination_reason") or "") == "user_refused",
                max_turns=(turn >= int(state.get("max_turns", turn))),
            )
            should_stop = termination_reason != "continue"
        if turn_trace:
            turn_trace.fsm_state_after = fsm.current_state
            turn_trace.fsm_moved = fsm_moved or int(fsm.pointer) != prev_pointer
            turn_trace.fsm_transition_reason = fsm_reason
            turn_trace.bot_utterance = bot_utter
            turn_trace.bot_action = bot_action
            turn_trace.violations_this_turn = list(new_violations)
            turn_trace.degraded_calls = list(degraded)
            turn_trace.duration_ms += int((perf_counter() - bot_started) * 1000)
        return {
            "messages": messages,
            "turn_count": turn,
            "bot_llm_connected": bot_llm_connected if used_llm else bool(state.get("bot_llm_connected", True)),
            "covered_nodes": covered_nodes,
            "bot_state": bot_state,
            "bot_state_log": bot_state_log,
            "consecutive_reject": consecutive_reject,
            "stalled_rounds": stalled_rounds if int(fsm.pointer) == prev_pointer else 0,
            "user_memory": user_memory,
            "violations": violations,
            "hard_violation": hard_violation,
            "path_covered": path_covered,
            "flow_adherence_rate": flow_rate,
            "termination_reason": termination_reason if should_stop else state.get("termination_reason"),
            "should_terminate": should_stop,
            "dialogue_trace": trace,
            "degraded_calls": degraded,
            "_current_turn_trace": None,
        }
    def _route_after_bot(self, state: Dict[str, Any]) -> str:
        should_stop, reason = self.term.check(state)
        if should_stop:
            if reason and not state.get("termination_reason"):
                state["termination_reason"] = reason
            return "end"
        return "continue"

    _STEP_THEME_KEYWORDS = {
        "F1": ("合同", "配送", "生效", "上线"),
        "F2": ("连续", "三天", "3天", "派单"),
        "F3": ("安全", "尽量", "拒单", "接单", "顺利"),
        "F4": ("排名", "拒单", "取消", "超时", "恶劣天气", "资格", "站长"),
        "CLOSING": ("确认", "谢谢", "结束", "配合"),
    }

    _F2_THEME = ("连续", "三天", "3天", "合同", "配送", "派单")

    def _is_repetitive(self, candidate: str, bot_history: List[str], *, current_state: str = "") -> bool:
        c = (candidate or "").strip()
        if not c:
            return True
        if is_semantically_repetitive(c, bot_history):
            return True
        if not bot_history:
            return False
        if c == bot_history[-1].strip():
            return True
        if bot_history.count(c) >= 2:
            return True
        if len(c) >= 10 and any(c[:10] == h[:10] for h in bot_history if len(h) >= 10):
            return True
        fee_theme = ("低延迟", "费用", "适用")
        if sum(1 for k in fee_theme if k in c) >= 2:
            for h in bot_history[-2:]:
                if sum(1 for k in fee_theme if k in h) >= 2:
                    return True
        recent = bot_history[-3:]
        if current_state == "F3" and any(k in c for k in self._F2_THEME):
            if any(sum(1 for k in self._F2_THEME if k in h) >= 2 for h in recent):
                return True
        if current_state == "F4" and any(k in c for k in ("连续", "三天", "3天")):
            if any("连续" in h for h in recent):
                return True
        theme_keys = self._STEP_THEME_KEYWORDS.get(current_state, ())
        if theme_keys:
            c_hits = sum(1 for k in theme_keys if k in c)
            if c_hits >= 2:
                for h in bot_history[-3:]:
                    h_hits = sum(1 for k in theme_keys if k in h)
                    if h_hits >= 2:
                        return True
        closings = ("顺利", "注意安全", "祝你")
        if sum(1 for cl in closings if cl in c) >= 2:
            for h in bot_history[-3:]:
                if sum(1 for cl in closings if cl in h) >= 1 and any(k in c and k in h for k in theme_keys or closings):
                    return True
        return False

    def _fallback_step_utterance(
        self,
        instruction,
        step_text: str,
        current_state: str,
        slot_values: Dict[str, str] | None = None,
        *,
        bot_history: List[str] | None = None,
        bot_state: Dict[str, Any] | None = None,
        attempt: int = 0,
    ) -> str:
        history = bot_history or []
        if instruction is not None:
            options = build_step_utterance_alts(
                instruction, current_state, step_text, slot_values
            )
            options = [o for o in options if "请确认当前步骤" not in o]
            if options:
                picked = pick_non_repeating(options, history, attempt=attempt)
                if picked and not is_semantically_repetitive(picked, history):
                    return picked
        if (
            current_state == "F4"
            and bot_state is not None
            and instruction_f4_is_delivery_split(instruction, step_text, slot_values)
        ):
            sync_f4_completion(bot_state, history)
            if f4_coverage_summary(bot_state, history).get("complete"):
                return pick_f4_post_ack(history, attempt=attempt)
            return pick_flow_step_utterance(
                current_state, step_text, bot_state, slots=slot_values, instruction=instruction
            )
        base = compress_step_to_utterance(
            step_text, slots=slot_values, current_state=current_state
        )
        if current_state == "CLOSING":
            base = compress_step_to_utterance(
                "完成收口，确认结论并礼貌结束对话。",
                slots=slot_values,
                current_state="CLOSING",
            )
        return pick_non_repeating([base], history, attempt=attempt) if base else "好的，再见。"

    def _get_current_step_text(
        self,
        current_state: str,
        instruction,
        *,
        last_user_utterance: str = "",
        slot_values: Dict[str, str] | None = None,
    ) -> str:
        if not instruction:
            return ""
        flow_steps = list(getattr(instruction, "flow_steps", []) or [])
        if current_state.startswith("F"):
            try:
                idx = int(current_state[1:]) - 1
                if 0 <= idx < len(flow_steps):
                    return str(flow_steps[idx])
            except ValueError:
                return ""
        if str(current_state).startswith("branch::"):
            from eval1.layer2.step_speakable import resolve_branch_speakable

            line = resolve_branch_speakable(instruction, current_state, slot_values)
            if line:
                return line
            return "按分支条件继续说明。"
        if str(current_state).startswith("op::"):
            from eval1.layer2.step_speakable import resolve_op_speakable

            line = resolve_op_speakable(instruction, current_state, slot_values)
            if line:
                return line
            return "按操作步骤继续引导配置。"
        if current_state == "CLOSING":
            return "完成收口，确认结论并礼貌结束对话。"
        if is_probe_node(current_state):
            return "等待对方说明是否在开车或是否方便继续通话。"
        if current_state in {"FAQ_NORMAL", "FAQ_OOB"}:
            from eval1.layer2.instruction_grounding import build_instruction_grounding, match_instruction_snippets

            grounding = build_instruction_grounding(instruction, slot_values)
            matched = match_instruction_snippets(last_user_utterance, grounding)
            if matched:
                return matched[0]
            nodes = list(getattr(instruction, "knowledge_nodes", []) or [])
            if nodes:
                return str(getattr(nodes[0], "text", nodes[0]))
            return "针对用户问题给出与任务相关的解释。"
        if current_state in {"OBJECTION", "F3_RETAIN", "OBJ_FINAL"}:
            return "理解用户顾虑，简短鼓励并提醒安全，勿念流程元指令。"
        return ""

    def verify_path_coverage(self, path_nodes: List[str], covered_nodes: List[str]) -> bool:
        if not path_nodes:
            return True
        covered = set(covered_nodes)
        return all(n in covered for n in path_nodes if n not in {"START"})

    def _termination_priority(
        self,
        *,
        hard_violation: bool,
        user_action: str,
        goal_achieved: bool,
        user_refused: bool,
        max_turns: bool,
    ) -> str:
        # spec 4.6: hard_violation > hangup > goal_achieved > user_refused > max_turns
        if hard_violation:
            return "hard_violation"
        if user_action == "hangup":
            return "hangup"
        if goal_achieved:
            return "goal_achieved"
        if user_refused:
            return "user_refused"
        if max_turns:
            return "max_turns"
        return "continue"
