# Eval1 系统说明：建图、路径、评测与数据存放

本文档描述**当前生产栈**（`eval1/` + `frontend/`）的内部机制，并说明各类评测/制品数据在仓库中的位置。旧版 `eval_system/` 仅作对照附录。

相关文档：

- [Eval1 运行手册](../README.md)
- [Layer1 节点类型说明](LAYER1_SCENE.md)（部分字段以 eval_system 命名为例，运行时以 eval1 为准）
- [架构说明](ARCHITECTURE.md)（历史文档，接口以 eval1 为准）

---

## 1. 系统组成与流水线

| 组件 | 路径 | 作用 |
|------|------|------|
| 后端 | `eval1/` | Layer1 解析与建图 → Layer2 对话仿真 → Layer3 评分 |
| 前端 | `frontend/` | Eval Studio（`/api/eval1/*`） |
| 配置 | `eval1/.env` | DashScope / DeepSeek Key、模型名、评分权重等 |

```mermaid
flowchart LR
  A[原始指令 eval1/data] --> B[InstructionParser]
  B --> C[RuleGraphBuilder]
  C --> D[PathEnumerator]
  D --> E[ExecutionPlanner]
  E --> F[SimulationGraph]
  F --> G[RuleJudge + LLMJudge]
  G --> H[Aggregator]
  H --> I[eval1/outputs/*.json]
```

**单次评测不必覆盖全部规则**；通过多条路径 × 全量 6 种 Persona 的笛卡尔积，在整体上覆盖流程分支、FAQ、挽留、边界等场景。

---

## 2. Layer1：规则知识图谱建图规则

实现：`eval1/layer1/rule_graph.py` → `RuleGraphBuilder`。

### 2.1 流程主干层

| 节点 ID | `node_type` | 含义 |
|---------|-------------|------|
| `START` / `END` | meta | 对话起止 |
| `F1` … `Fn` | flow_step | 解析得到的 Call Flow 有序步骤 |
| `CLOSING` | transition | 收尾话术 |
| `FAQ_NORMAL` / `FAQ_OOB` | transition | 合规 FAQ / 越界（跑题）FAQ |
| `OBJECTION` | transition | 用户拒绝、异议 |
| `F3_RETAIN` / `OBJ_FINAL` | transition | 仅当指令含挽留轨时（如 `instruction_1`） |

**顺序边：**

- `START → F1 → … → Fn → CLOSING → END`
- 若无流程步：`START → CLOSING → END`

**中断轨（每个 `Fi` 均可跳出）：**

- `Fi → OBJECTION`（`user_refusal`）
- `Fi → FAQ_NORMAL`（`user_asks_faq`）
- `Fi → FAQ_OOB`（`user_oob_question`）

**挽留轨（instruction_1 类）：**

- 可从 `START` 或任意 `Fi` 进入 `F3_RETAIN`，再 `goto` 回到某 `Fi` 或进入 `OBJ_FINAL → END`

**FAQ 回归：**

- `FAQ_NORMAL → Fi`（`resume_before:Fi`）
- `FAQ_OOB → CLOSING`（跑题后收束）

### 2.2 条件分支与操作链

从 **`raw_text` 确定性解析**（`parse_instruction_branches`、`extract_branches_from_block`）：

- 分支节点：`flow_branch`（如 `branch::4::1` 或结构化 branch_id）
- 操作链：`op_step`（`op::{step}::{branch_index}::{oi}`），可含 `pause_s`
- **某步存在分支时，删除** `Fi → F{i+1}` 直连，必须经分支节点再走
- 边类型：`branch` / `sequence` / `goto`，带 `guard_expr`

### 2.3 约束与知识挂载

| `ConstraintType` | 挂接到图 |
|------------------|----------|
| FLOW | 约束节点自环 `covers_step` |
| KNOWLEDGE | → `FAQ_NORMAL`（`on_user_ask`） |
| BOUNDARY | → `FAQ_OOB`（`applies_globally`） |
| DIALOGUE | → `CLOSING`（全程话术） |

另有 `GLOBAL_DIALOGUE` / `GLOBAL_BOUNDARY` 汇总 DIALOGUE、BOUNDARY 类约束。

`knowledge_nodes` 通过 `on_user_ask` 挂到 `FAQ_NORMAL` 等状态；`attachment` 记录状态 → 知识节点列表。

### 2.4 冲突检测

`detect_conflicts()` 为**确定性**检测，例如：

- 重复 DIALOGUE 约束文案
- 流程顺序边缺失（`flow_sequence_break`）

**不包含**旧版 `eval_system` 的 LLM 两两语义边（EXCLUDES / REQUIRES）与 LLM SAT 求解。

### 2.5 Layer1 API 输出

`eval1/analysis_service.py` 中 `build_layer1_analysis()` 返回：

- `parsed`：结构化指令
- `kg_viz`：图可视化 nodes/edges
- `paths`：枚举路径 + `fsm_projection`
- `goal_fsm`：FSM 元数据
- `conflicts`：冲突列表

前端通过 `GET /api/eval1/layer1/{dataset_id}` 获取（实时解析，非读 `docs/` 旧制品）。

---

## 3. 路径生成方法

实现：`eval1/layer1/path_enumerator.py`、`path_coverage_builder.py`、`path_coverage_planner.py`、`path_linear_curator.py`、`path_plan_config.py`。

### 3.1 任务模式 `infer_path_plan_config`

| 条件 | `mode` | 其他 |
|------|--------|------|
| 指令含流程分支（instruction_2） | `branched` | FAQ 附在 F2–F7 等；OOB 多在 F4 |
| 含挽留轨（instruction_1） | `linear` + `include_retention_variants` | FAQ/OOB 可附在 F2–F4 等 |
| 默认 | `linear` | 主干 + FAQ/OOB + 探针 |

统一上限：`max_paths`（默认 64）。

### 3.2 结构化覆盖 `build_minimal_coverage_paths`

在图上 **`walk_path`**：从 `START` 按每步 `branch_choices` 走到 `END`，处理 `branch::`、`op::` 链。

**分支任务（instruction_2）：**

1. **Tier 1**：F4 × F6 组合网格（约 8 条）
2. **Tier 2**：各步「替代分支」× F6
3. **Tier 3**：补齐尚未出现在任一路径中的 `branch::` / `op::` 节点

**线性任务：**

- 默认主干：`START → F* → CLOSING → END`

**叠加变体：**

- FAQ 路径：在基准路径上插入 `FAQ_NORMAL`
- OOB 路径：插入 `FAQ_OOB`
- 探针：`PROBE_D9_BUSY`、`PROBE_D10_DRIVE` 等（`include_probes=true`）

### 3.3 线性 + 挽留：DFS + 策展

仅 `linear` 且 `include_retention_variants` 时：

1. DFS 收集 FAQ / 挽留 / OOB 等中断组合候选
2. 与结构化路径合并去重
3. `curate_retention_flow_paths` 按模板筛选（纯 FAQ、纯 OOB、挽留后继续 F4 等）
4. 截断至 `max_paths`

分支任务**跳过** DFS 阶段，仅用结构化覆盖。

### 3.4 路径 → 执行计划（Path × Persona）

实现：`eval1/pipeline/plan_compat.py`。

当前实现为**全量笛卡尔积**（`build_cartesian_execution_plans`）：所有路径 × 6 种 Persona 均生成 `ExecutionPlan`，不过滤跳过。语义不匹配的组合（如配合型 + objection 路径）标注 `plan_group="potential_contradiction"` 仅作注记。`should_skip()` 规则和 `filter_compatible_plans()` 保留，可按需启用二次过滤。

每条 `ExecutionPlan` 含 `path.nodes`、`persona_type`、`variable_values`、`max_turns`（按路径节点成本 + Persona 附加动态计算），供 Layer2 使用。

---

## 4. Layer2：对话仿真

实现：`eval1/layer2/simulation_graph.py`（LangGraph）。

循环：**用户模拟 → Bot → DST / 终止判断**。

| 模块 | 作用 |
|------|------|
| **GoalFSM** | 按 Layer1 **路径节点序列**推进（`GoalFSM.from_path`），非按指令动态生成 STEP_n |
| **UserSimulator** | `path_user_driver` 推断动作（FAQ/拒绝/OOB/探针）；Persona 只影响措辞与语气 |
| **BotWrapper** | 完整指令 + 变量替换；F4 配送拆分等有专门 utterance 与 coverage 跟踪 |
| **DST** | 记录违规（硬边界、话术长度、流程等） |
| **TerminationChecker** | 硬违规、挂断、目标达成、拒绝上限、`max_turns` |

**路径覆盖率：**

- `flow_adherence_rate`：路径节点与 Bot 行为日志合并计算
- 低于 **85%**（`FLOW_COVERAGE_VIOLATION_THRESHOLD`）可追加 `flow_miss` 类违规

---

## 5. Layer3：评测方法

实现：`eval1/layer3/rule_judge.py`、`llm_judge.py`、`aggregator.py`、`rubrics.py`、`scoring_config.py`。

### 5.1 规则分 RuleJudge

依据对话中的 `violations` 及衍生检查扣分，例如：

| 检查项 | 说明 |
|--------|------|
| 违规条目 | `hard_boundary`、`dialogue_length`、`flow_miss`、`flow_incomplete` 等 |
| F4 配送要点 | 路径含 F4 且为配送拆分时，检查排名/拒单/天气是否说全 |
| 流程覆盖率 | `<60%` 加扣；`<85%` 轻度加扣 |
| Bot 重复 | 重复回复条数加权扣分 |
| 开场白 | 首条 Bot 是否与 `opening_line` 一致 |
| 硬违规次数 | `>2` 次 → `hard_fail`，总分置 0 |

### 5.2 LLM 评委 LLMJudge

六维 1–5 分（rubrics），加权合成 LLM 分：

| 维度 key | 中文 | 默认权重 |
|----------|------|----------|
| `flow_adherence` | 流程遵循 | 0.25 |
| `dialogue_compliance` | 话术合规 | 0.20 |
| `knowledge_accuracy` | 知识准确 | 0.20 |
| `retention_effectiveness` | 挽留效果 | 0.15 |
| `boundary_handling` | 边界处理 | 0.10 |
| `naturalness` | 自然度 | 0.10 |

每条评分需引用轮次证据（如 `[T3]`）。`retention_effectiveness` 在用户全程配合时可固定高分、不扣分。

### 5.3 总分 Aggregator

默认（`eval1/config.py` / `ScoringConfig`）：

```
总分 = 规则分 × 0.40 + LLM分 × 0.60
```

- 硬失败（`hard_fail`）：总分 0，等级 F
- 等级阈值：A≥90，B≥80，C≥70，D≥60，否则 F

`ConsistencyChecker` 仍计算 `kappa` / `major_inconsistency` 供报告展示，但 `consistency_penalty` 已硬编码为 `0.0`，**不实际扣分**。

---

## 6. 评测数据存放位置（按模型与类型）

### 6.1 核心原则：谁用哪个模型

| 角色 | 模型来源 | 配置项 | 是否随「被测 Bot」切换 |
|------|----------|--------|----------------------|
| **被测 Bot** | Qwen 或 DeepSeek | `--bot-provider` / API `bot_provider` | **是** → 报告分文件 |
| **用户模拟** | 通义千问 | `LLM_MODEL_FAST`（默认 `qwen-plus`） | 否 |
| **Layer3 评委** | 通义千问 | `LLM_MODEL_JUDGE`（默认 `qwen-turbo`） | 否 |
| **Layer1 解析** | 通义千问 | 解析 Agent | 否 |

因此：**切换 DeepSeek 只改变「被测 Bot」的对话与对应报告 JSON**；用户侧与评委侧始终是 Qwen（除非改 `.env`）。

### 6.2 Eval1 全流程评测报告（主要数据）

目录：**`eval1/outputs/`**

| 被测 Bot | 文件名规则 | 当前仓库示例 |
|----------|------------|--------------|
| Qwen（默认） | `eval1_reports_{dataset_id}.json` | `eval1_reports_instruction_1.json`、`eval1_reports_instruction_2.json` |
| DeepSeek | `eval1_reports_{dataset_id}_deepseek.json` | `eval1_reports_instruction_1_deepseek.json`、`eval1_reports_instruction_2_deepseek.json` |

路径由 `eval1/bot_provider.py` → `reports_output_path()` 生成。

**生成方式：**

```powershell
# Qwen 被测
python eval1/scripts/run_eval.py --dataset-id instruction_1 --progress

# DeepSeek 被测（用户模拟/评委仍为 Qwen）
python eval1/scripts/run_eval.py --dataset-id instruction_1 --progress --bot-provider deepseek
```

或通过 API / 前端：`bot_provider=qwen|deepseek`。

**报告 JSON 主要内容：**

- 顶层：`dataset_id`、`count`、`average_score`、`dimension_averages`、`grade_distribution`
- `reports[]`：每条路径×Persona 对话的 `total_score`、`rule_score`、`llm_score`、`violations`、`dimension_scores`、`messages` 等
- `layer2`：`dialogues`、计划元数据
- `meta`：`bot_provider`、`bot_model`、`llm_model_fast`、`llm_model_judge` 等

前端工作台通过 `GET /api/eval1/layer2/{dataset_id}?bot_provider=...` 读取；`GET /api/eval1/reports/{dataset_id}/providers` 查看各 Bot 报告文件是否存在。

> 建议将 `eval1/outputs/*.json` 加入 `.gitignore`（体积大）；本地评测后自行保留。

### 6.3 原始指令与上传数据

| 路径 | 内容 |
|------|------|
| `eval1/data/data.xlsx` | 内置数据集（`instruction_1`、`instruction_2` 等） |
| `eval1/data/uploads/` | API/前端上传的 xlsx、json、txt |

列表接口：`GET /api/eval1/datasets`。

### 6.4 旧版 / 辅助制品（非 Eval1 运行时依赖）

| 路径 | 来源 | 用途 |
|------|------|------|
| `docs/layer1_artifacts_{dataset_id}.json` | `scripts/export_layer1_docs_artifacts.py`（**eval_system** `build_scene`） | 含 LLM 语义边、SAT、修复建议的旧 Layer1 快照；**与 eval1 图结构不一致** |
| `docs/layer1_parse_report_{dataset_id}.json` | 解析检查脚本 | 解析摘要 |
| `docs/layer1_graph_{dataset_id}.mmd` | 导出 | Mermaid 图 |
| `docs/layer2/layer2_meta_{dataset_id}.json` | `scripts/export_layer2_meta.py`（**eval_system**） | Layer2 规划元数据（旧栈） |
| `outputs/instruction_1_path_persona_eval.json` | `scripts/run_path_persona_eval.py`（**eval_system** 管线） | 旧 Path×Persona 评测结果 |
| `eval_system.db`（仓库根，若存在） | eval_system SQLite | 旧 API 持久化任务/报告 |

**注意：** 你打开的 `docs/layer1_artifacts_instruction_2.json` 属于上表第一行，**不能**当作 Eval Studio 当前 Layer1 的权威数据源；在线 Layer1 以 `eval1` 实时解析为准。

### 6.5 配置与密钥

| 文件 | 说明 |
|------|------|
| `eval1/.env` | `DASHSCOPE_API_KEY`、`DEEPSEEK_API_KEY`、`LLM_MODEL_*`、`weight_rule` / `weight_llm` 等 |
| `eval1/.env.example` | 模板 |

勿将 `.env` 提交到 Git。

---

## 7. `eval_system` 是否仍需要？

| 场景 | 是否需要 eval_system |
|------|---------------------|
| CLI/API 全流程评测、Eval Studio | **不需要** |
| 维护 `eval1` 代码与测试 | **不需要** |
| 重导 `docs/layer1_artifacts_*.json`（旧可视化/冲突工作流） | 需要运行 export 脚本 |
| 跑 `run_path_persona_eval.py`、旧 pytest | 需要 |
| 与历史制品对比 | 可选保留 |

生产路径：**仅 `eval1` + `frontend`**。`eval_system` 为遗留参考栈。

### 7.1 eval1 与 eval_system 对照

| 能力 | eval1（现行） | eval_system（遗留） |
|------|---------------|---------------------|
| 流程节点 | `F1`, `F2`, … | `flow_0`, `flow_1`, … |
| 约束拓扑 | 挂 FAQ/OOB/CLOSING | `scope_dialogue` → 各 flow |
| 语义边 | 无 LLM 两两判别 | `add_semantic_edges` + SAT |
| 路径规划 | 结构化 walk + 分支网格 + DFS 策展 | test_plan + Path×Persona 笛卡尔积 |
| 仿真 FSM | **路径驱动** | **指令驱动** STEP_n |
| 评分权重 | 规则 40% + LLM 60% | 文档记载 40% + 50% − 10% 一致性 |
| HTTP | `eval1.main:app` `/api/eval1/*` | `eval_system.main:app` `:8000` 旧路由 |

---

## 8. 快速查阅索引

| 你想查… | 去看… |
|---------|--------|
| 建图代码 | `eval1/layer1/rule_graph.py` |
| 路径枚举 | `eval1/layer1/path_enumerator.py`、`path_coverage_builder.py` |
| Path×Persona | `eval1/pipeline/plan_compat.py` |
| 对话仿真 | `eval1/layer2/simulation_graph.py`、`goal_fsm.py` |
| 评分 | `eval1/layer3/rule_judge.py`、`llm_judge.py`、`aggregator.py` |
| Qwen Bot 报告 | `eval1/outputs/eval1_reports_{dataset_id}.json` |
| DeepSeek Bot 报告 | `eval1/outputs/eval1_reports_{dataset_id}_deepseek.json` |
| 旧 Layer1 制品 | `docs/layer1_artifacts_{dataset_id}.json` |

---

*文档版本：与仓库 eval1 栈对齐；如有接口变更以根目录 `README.md` 与 `eval1/api/routes.py` 为准。*
