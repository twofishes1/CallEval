# 场景构建层（Layer 1）说明：节点类型与知识要点解析

本文说明 **数据结构里有哪些“节点类型”**，以及数据中 **「问到某名词要能答」这类知识要点** 在本系统中如何建模、解析、进图。

---

## 一、两份“数据”的分工

| 层级 | 数据形态 | 作用 |
|------|----------|------|
| **原始指令** | `raw_instruction` 文本（或 Excel/JSON） | 人写的 Role / Task / Call Flow / Constraints / FAQ 等 |
| **解析产物** | `ParsedInstruction` + `RuleKnowledgeGraph` | 机器可用的步骤、约束、变量、FAQ、冲突与图谱节点 |

Pipeline：**解析 → 建图 → 冲突检测 → 用例生成**。可视化里的“知识图谱节点”主要来自 **图谱**（NetworkX），不是 Excel 里的每一行都叫节点。

---

## 二、`ParsedInstruction` 里的结构化字段（解析结果）

解析器（首选 **LLM 结构化输出**，无 Key 时 **启发式回退**）目标是把原文拆成：

| 字段 | 含义 |
|------|------|
| `role_description` | 角色 |
| `task_description` | 任务目标 |
| `opening_line` | 开场话术（可选） |
| **`flow_steps`** | Call Flow **有序步骤**（每步一个字符串，常为可检查的谓词描述） |
| **`faq_items`** | **知识问答 / 名词解释**：列表，每项形如 `{"q": "...", "a": "..."}`，可选 `"terms"` 填触发词 |
| **`constraints`** | **约束列表**，每条对应 `Constraint` |
| **`variables`** | `${name}`、`**X**` 等占位符及取值 |
| `metadata` | 解析元信息等 |

---

## 三、约束条目 `Constraint` 与枚举 `ConstraintType`

每条约束是一条 **话术/流程/边界** 层面的规则：

| `ConstraintType` | 典型含义 | 与本项目图谱的关系 |
|------------------|---------|---------------------|
| **ROLE** | 身份与立场 | 可进图谱为约束节点，用于冲突与语义边 |
| **FLOW** | 与流程顺序/跳转相关 | 同左 |
| **DIALOGUE** | 话术形式：字数、禁用词、不能说某话等 | 常带 **`detection_rule`**（对 `utterance` 可自动检测） |
| **KNOWLEDGE** | **知识义务**：须在某种用户提问下交代某事实、解释某名词 |多为 **不可自动穷尽检测**（`measurable=False`），依赖 **LLM Judge** 或与 **faq_items** 对照 |
| **BOUNDARY** | 职责边界（不越权承诺、不谈敏感话题） | 常 `is_hard=True`，检测视表述而定 |

设计意图：

- **“问到名词要回答”** 可同时落在：
  - **`faq_items`**：标准 Q&A 颗粒度，图谱里可出现 **FAQ 节点**；
  - **`Constraint(type=KNOWLEDGE)`**：抽象成一条“在满足触发条件时需覆盖的要点”（适合评分 rubric）。
- LLM 解析时需在 System Prompt 中 **显式要求**抽出 FAQ / KNOWLEDGE，否则容易只抽到 DIALOGUE。

---

## 四、规则知识图谱 NetworkX：`node_type`（图的节点）

**图是给机器和可视化用的**。当前实现中出现的节点类别如下：

| `node_type` | 含义 | 典型数据来源 |
|-------------|------|--------------|
| **`flow_step`** | 第 `i` 步外呼流程 | `ParsedInstruction.flow_steps` → `flow_0`,`flow_1`,… |
| **`constraint`** | 一条结构化约束 | `ParsedInstruction.constraints` |
| **`variable`** | 占位符变量 | `ParsedInstruction.variables` 的键 → `var::name` |
| **`faq_item`** | **一条知识与问答要点**（用户可能问 `q`，要点答 `a`） | **`ParsedInstruction.faq_items`**（解析自 FAQ/知识要点等板块） |
| **`dialogue_scope`** | **整通对话约束域**（`scope_dialogue`）：语义上约束对**全程每一轮**生效，而非只挂在第一步 | 有流程步时自动添加 |

**边 `edge_type`（部分）**

| `edge_type` | 含义 |
|-------------|------|
| `sequence` | 流程步之间的顺序：`flow_{i}` → `flow_{i+1}` |
| `applies_globally` | 约束 → `scope_dialogue`：该约束归入**整通对话**生效范围 |
| `covers_step` | `scope_dialogue` → 各 `flow_i`：约束域**覆盖**每一步外呼流程（可视化与下游推理用） |
| `excludes` / `requires` | 约束之间互斥或依赖（启发式 + LLM 语义边） |
| `on_user_ask` | **FAQ 与对话域**：`faq_item` → `scope_dialogue`，表示用户插问时可援引该要点（不限定仅第一步） |

---

## 五、“问到某个名词要能答”——建议怎么写在数据里、怎么解析

### 推荐写法（便于抽取）

```markdown
# FAQ / 名词解释 / 常见问答（任选小节标题）

- 骑手问什么是「飞毛腿」：答曰：飞毛腿是……（一句话要点）
- 若用户问起「生效」时间节点：答曰：合同中约定……
```

或使用表格/编号 Q&A（需在 Excel 中用换行或大段文本传给解析器）。

### 解析产物

| 去向 | 内容 |
|------|------|
| `faq_items` | `[{"q": "骑手问什么是「飞毛腿」", "a": "答曰：飞毛腿是……", "terms": "飞毛腿"}]`（`terms` 可选） |
| 图谱 | 每个条目一个 **`faq_item` 节点**；与 **`scope_dialogue`** 用 **`on_user_ask`** 连接（整通对话范围内有效） |
| （可选）`constraints` | 增加 `KNOWLEDGE`：**“当被问及「飞毛腿」定义时须准确说明下列要点且不编造”**，`measurable=False` |

### 运行时如何用到

| 阶段 | 作用 |
|------|------|
| **Layer 2 对话** | 用户模拟器可依据 FAQ **概率插问**，考察 Bot |
| **Layer 3 Judge** | `knowledge_accuracy` 维度对照 **FAQ 与 KNOWLEDGE 约束**，判断是否捏造、遗漏 |

---

## 六、是否真的调用 LLM？(场景构建）

- **`build_scene` / `/api/datasets/{id}/build-scene`**：**必须配置** `DASHSCOPE_API_KEY`。固定依次执行：**LLM 语义边推断**、`LLM + 推理 prompt` 可满足性检查、对每个冲突生成 **LLM 修复建议**（并结合图上的确定性冲突检测）。缺 Key 返回 **HTTP 503**（`MissingQwenApiKeyError`）。
- **`InstructionParserAgent.parse` 单机调用**：仍可走「有 Key→LLM 结构化 / 无 Key→启发式」；左侧「批量解析摘要」`/api/datasets/parse-batch` 也不要求 Key。

---

## 七、与设计文档的差距（可演进点）

后续可增强：

1. KNOWLEDGE 约束与 `faq_item` 的自动对齐（同名 term 连线）；  
2. `detection_rule` 对部分知识做弱检测（例如答案必含关键字，易误判，需谨慎）；  
3. Excel **多列**导出 `faq_q`/`faq_a`/`terms` → 直接进入 `faq_items`。

当前版本：**知识要点请以 `FAQ/知识要点` 段落 + LLM 解析为主**，图谱侧已预留 **`faq_item` 节点** 及文档约定。
