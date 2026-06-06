from __future__ import annotations

from typing import List, Optional

from eval1.layer2.call_state import get_state_topic
from eval1.layer2.path_user_driver import path_action_label
from eval1.layer2.persona import PersonaCard, PersonaType
from eval1.layer2.persona_phrasing import (
    build_persona_contextual_tone_hint,
    build_persona_interest_hint,
    get_persona_tone_for_action,
    get_persona_voice_guide,
    is_f4_bot_context,
    is_hollow_user_response,
)
from eval1.layer2.user_context_memory import UserContextMemory
from eval1.layer2.utterance_diversity import build_diversity_prompt_block
from eval1.layer2.user_directive import (
    build_persona_card_block,
    format_dialogue_history,
    get_user_directive,
)
from eval1.layer2.user_sim_instruction_context import UserSimScene, _DEFAULT_SCENE

_ACTION_SEMANTICS = {
    "comply": "口头表示同意、接受或愿意照做（具体措辞由Persona与上下文决定）",
    "confirm": "确认听明白了，准备结束通话",
    "ask_question": "就Bot刚说的内容追问依据、后果或含义",
    "reject": "表示不想配合、规则太苛刻、或暂时拒绝（措辞须符合Persona，勿套「这规则有点苛刻」）",
    "off_topic": "夹带一句与当前规则无关的话，但仍在业务场景内",
    "hangup": "表示要挂电话或结束",
}

_UNNATURAL_PHRASES = (
    "下一项", "下一节点", "Call Flow", "流程节点", "FSM", "配合推进", "触发节点", "路径测试",
    "Role", "Task", "CallFlow", "Knowledge Points",
)


def build_user_sim_system_prompt(
    persona: PersonaCard,
    *,
    scene: UserSimScene | None = None,
    context: UserContextMemory,
    current_state: str,
    allowed_actions: List[str],
    required_action: str,
    questions_at_step: int,
    messages: List[dict],
    sampled_action: str,
    path_user_action: str = "",
    path_utterance_hint: str = "",
    instruction: Optional[object] = None,
) -> str:
    scene = scene or _DEFAULT_SCENE
    persona_block = build_persona_card_block(
        persona,
        user_name=scene.user_name,
        user_role=scene.user_role,
    )
    memory_block = context.format_for_prompt(persona, caller_label=scene.caller_label)
    fsm_directive = get_user_directive(
        current_state=current_state,
        persona=persona,
        allowed_actions=allowed_actions,
        required_action=required_action,
        questions_at_step=questions_at_step,
        planned_path_nodes=None,
        path_user_action=path_user_action,
        path_next_node="",
        path_utterance_hint=path_utterance_hint,
        instruction=instruction,
        scene=scene,
    )
    history_block = format_dialogue_history(messages, limit=6)
    action = path_user_action or sampled_action or "comply"
    topic = get_state_topic(current_state, instruction=instruction)
    tone = get_persona_tone_for_action(persona, action)
    last_bot = ""
    for m in reversed(messages or []):
        if str(m.get("role", "")).lower() == "bot":
            last_bot = str(m.get("content", ""))
            break
    interest = build_persona_interest_hint(
        persona,
        action=action,
        current_state=current_state,
        last_bot_utterance=last_bot,
    )
    user_max = min(int(scene.max_chars), 20)
    unnatural = "、".join(f"「{p}」" for p in _UNNATURAL_PHRASES[:8])
    off_topic = _ACTION_SEMANTICS["off_topic"].replace("业务场景", scene.off_topic_scope)

    f4_ctx = is_f4_bot_context(last_bot)
    f4_confirm = action == "confirm" and (current_state == "F4" or f4_ctx)
    _persona_expr_default = {
        PersonaType.QUESTIONING: "每轮尽量体现追问、核实或质疑，不要无思考地全盘接受。",
        PersonaType.RESISTANT: "可以配合推进，但须带勉强/保留（行吧/但/得看情况），禁止热情配合腔。",
        PersonaType.IMPATIENT: "句短、直、显催促，禁止长篇客套。",
        PersonaType.IGNORANT: "听不懂就直说，追问含义或怎么算。",
        PersonaType.OFF_TOPIC: "可夹带弱相关岔话，但仍在业务场景内。",
        PersonaType.COOPERATIVE: "友好干脆，但仍需完整表达一个想法，勿机械复读。",
    }
    _persona_expr_f4_confirm = {
        PersonaType.QUESTIONING: (
            "须针对对方刚说的排名/拒单/天气/超时等具体词追问或确认；"
            "禁止空泛「还想确认一点/大体明白」而不点关键词。"
        ),
        PersonaType.IMPATIENT: (
            "句短、可催促，但必须点到排名/拒单/天气/超时之一；"
            "禁止在规则已讲完后仍空泛说「说重点」。"
        ),
    }
    if f4_confirm and persona.persona_type in _persona_expr_f4_confirm:
        persona_expr = _persona_expr_f4_confirm[persona.persona_type]
    else:
        persona_expr = _persona_expr_default.get(persona.persona_type, "体现 Persona 情绪与态度。")
    tone_ctx = build_persona_contextual_tone_hint(
        persona,
        action=action,
        current_state=current_state,
        last_bot_utterance=last_bot,
    )

    principles = (
        f"- 只输出{scene.user_role}本轮说的话，1-2句，最多{user_max}字，中文口语。\n"
        f"- **性格表达（必达）**：{persona_expr}\n"
        "- **禁止敷衍单字/双字**：不要只回「好」「嗯」「行」「明白」；至少说出一句完整想法或态度。\n"
        f"- **硬约束（动作）**：本轮必须体现指定动作（同意/拒绝/追问/跑题/确认），由路径节点决定；"
        f"不得因自由发挥而跳过路径要求的动作或提前挂断。\n"
        f"- **软约束（语气）**：Persona 只决定怎么说，不得改变动作；措辞每轮自主变化，禁止套固定句式。\n"
        f"- 须先点出{scene.caller_label}上一句中的具体信息（关键词/数字/选项），再表达态度；禁止空泛敷衍。\n"
        f"- 根据Persona、记忆与{scene.caller_label}刚说的话**自主措辞**，不要照抄 prompt、知识库种子或任何示例句。\n"
        "- **主路径**：每轮必须由你当场生成；系统不会在正常流程中插入固定模板句。\n"
        "- **每轮说法要有变化**：勿复读最近轮次的开头、结尾或整句。\n"
        "- **兴趣点**：若对方刚说的规则/数字/后果你觉得需要确认，可以追问一句；配合型则快速带过。\n"
        "- 若本轮需拒绝/追问/跑题，话术语义必须与动作一致（禁止口是心非）。\n"
        f"- 禁止复述{scene.caller_label}原话；禁止"
        f"{unnatural}；禁止节点编号与系统术语。\n"
        f"- 你只知道通话中{scene.caller_label}已告知的内容。"
    )
    if current_state in {"START", "F1"}:
        principles += (
            "\n- 身份确认：若对方问是否负责人，答「是的/对/嗯，我是」即可；"
            "禁止编造或复读XX、某校区等占位名；不要主动报未在对话中出现的校区名。"
            "\n- 对方尚未说明的产品升级/直播选项等细节，你此时不知道，禁止主动提起或替对方宣告。"
        )

    return (
        f"{scene.scene_block}\n\n"
        "【一、身份与Persona角色设计】\n"
        f"{persona_block}\n"
        f"{get_persona_voice_guide(persona)}\n"
        f"本轮语气方向：{tone}\n\n"
        "【二、你的上下文记忆（随对话更新，请保持一致）】\n"
        f"{memory_block}\n\n"
        "【三、当前通话任务】\n"
        f"通话阶段：{topic}\n"
        f"本轮核心动作：{path_action_label(action)} — {_ACTION_SEMANTICS.get(action, off_topic if action == 'off_topic' else '自然回应')}\n"
        f"{fsm_directive}\n\n"
        f"{(tone_ctx + chr(10) + chr(10)) if tone_ctx else ''}"
        f"{interest + chr(10) + chr(10) if interest else ''}"
        "【四、最近对话（请接着聊，不要重头复述）】\n"
        f"{history_block}\n\n"
        "【五、生成原则】\n"
        f"{principles}"
    )


def build_user_sim_user_prompt(
    *,
    persona: PersonaCard,
    scene: UserSimScene | None = None,
    context: UserContextMemory,
    sampled_action: str,
    turn_index: int,
    last_bot_utterance: str,
    has_prior_bot: bool,
    current_state: str,
    path_user_action: str = "",
    path_utterance_hint: str = "",
    retry_feedback: str = "",
    user_history: List[str] | None = None,
    instruction: Optional[object] = None,
) -> str:
    scene = scene or _DEFAULT_SCENE
    action = path_user_action or sampled_action
    topic = get_state_topic(current_state, instruction=instruction)
    tone = get_persona_tone_for_action(persona, action)
    position = context.dialogue_position(
        last_bot=last_bot_utterance if has_prior_bot else "",
        current_topic=topic,
        caller_label=scene.caller_label,
    )

    parts: List[str] = []
    if retry_feedback:
        parts.append(f"【上轮不合格】{retry_feedback}")

    if has_prior_bot and last_bot_utterance:
        parts.append(f"{scene.caller_label}刚说：「{last_bot_utterance}」")
        parts.append("请针对这句话，结合你的记忆与Persona，生成下一句。")

    if path_utterance_hint:
        parts.append(f"路径动作说明：{path_utterance_hint}")

    interest = build_persona_interest_hint(
        persona,
        action=action,
        current_state=current_state,
        last_bot_utterance=last_bot_utterance if has_prior_bot else "",
    )
    tone_ctx = build_persona_contextual_tone_hint(
        persona,
        action=action,
        current_state=current_state,
        last_bot_utterance=last_bot_utterance if has_prior_bot else "",
    )
    if tone_ctx:
        parts.append(tone_ctx)
    if interest:
        parts.append(interest)

    parts.extend([
        f"对话位置：{position}",
        f"本轮动作（硬约束）：{path_action_label(action)}",
        f"Persona（软约束）={persona.persona_type.value}，语气：{tone}",
    ])

    diversity = build_diversity_prompt_block(user_history or [], persona=persona, turn_index=turn_index)
    if diversity:
        parts.append(diversity)

    parts.extend([
        f"轮次：{turn_index}",
        "直接输出要说的话，不要解释。",
    ])
    return "\n".join(parts)


def contains_unnatural_phrasing(utterance: str) -> bool:
    u = (utterance or "").strip()
    return any(p in u for p in _UNNATURAL_PHRASES)
