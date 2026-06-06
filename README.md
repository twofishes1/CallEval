# Eval1 · 复杂指令多轮对话评测系统

从业务指令出发，自动完成 **Layer1 解析 → Layer2 对话仿真 → Layer3 评分**，结果写入 JSON 报告，并通过 **Eval Studio** 前端查看。

**完整系统 = `eval1/`（后端）+ `frontend/`（工作台）**

| 组件 | 目录 | 说明 |
|------|------|------|
| 后端 | [`eval1/`](eval1/) | Layer1–3、CLI、FastAPI（`/api/eval1/*`） |
| 前端 | [`frontend/`](frontend/) | Eval Studio 可视化 |
| 配置 | `eval1/.env` | DashScope Key、模型（默认用户模拟 **qwen-plus**） |

---

## 1. 目录结构

```
contest2/
├── README.md                 # 本文档
├── requirements.txt          # Python 依赖
├── pytest.ini
├── .gitignore
├── eval1/                    # 评测引擎
│   ├── main.py               # FastAPI 入口，/api/eval1
│   ├── config.py             # 读取 eval1/.env
│   ├── api/routes.py         # REST 接口
│   ├── layer1/               # 指令解析、路径枚举、FSM 图谱
│   ├── layer2/               # 多轮对话仿真（Bot + 用户模拟）
│   ├── layer3/               # 规则分 + LLM 评委 + 聚合
│   ├── pipeline/             # 主编排、断点续跑、报告合并
│   ├── report/               # 报告分析与覆盖率工具
│   ├── scripts/
│   │   ├── run_eval.py       # CLI 跑评测（常用）
│   │   ├── run_server.py     # 启动 API
│   │   └── restore_report_backup.py
│   ├── data/
│   │   ├── data.xlsx         # 内置数据集（instruction_1、instruction_2 …）
│   │   └── uploads/
│   ├── outputs/
│   │   ├── eval1_reports_{dataset_id}.json
│   │   ├── eval1_reports_{dataset_id}_deepseek.json
│   │   └── backups/
│   ├── tests/
│   └── .env.example
├── frontend/                 # Eval Studio 工作台
│   ├── package.json
│   └── src/
└── docs/                     # 技术设计文档（可选阅读）
```

**数据流**：`eval1/data/` 读指令 → `pipeline/` 跑 plan → 写入 `eval1/outputs/*.json` → 前端通过 `/api/eval1/layer2/{dataset_id}` 展示。

---

## 2. 环境准备

| 项 | 要求 |
|----|------|
| Python | 3.11+ |
| Node.js | 18+（仅前端） |
| API Key | `DASHSCOPE_API_KEY`（必填）；DeepSeek 被测 Bot 时需 `DEEPSEEK_API_KEY` |

在**仓库根目录**执行：

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

copy eval1\.env.example eval1\.env
# 编辑 eval1\.env，填入 DASHSCOPE_API_KEY
```

`eval1/.env` 常用项：

| 变量 | 说明 |
|------|------|
| `DASHSCOPE_API_KEY` | 必填 |
| `LLM_MODEL_FAST` | 用户模拟，默认 `qwen-plus` |
| `LLM_MODEL_MAIN` | Qwen 被测 Bot，默认 `qwen-plus` |
| `LLM_MODEL_JUDGE` | LLM 评委，默认 `qwen-turbo` |
| `DEEPSEEK_API_KEY` | `--bot-provider deepseek` 时使用 |

---

## 3. 怎么运行

### 3.1 启动后端 API

```powershell
python eval1/scripts/run_server.py --reload
```

- 健康检查：`http://127.0.0.1:8000/health`
- API 文档：`http://127.0.0.1:8000/docs`
- 接口前缀：`/api/eval1`

### 3.2 启动前端 Eval Studio

```powershell
cd frontend
npm install
npm run dev
```

浏览器打开 **http://localhost:5173**（Vite 将 `/api` 代理到 `127.0.0.1:8000`）。

### 3.3 命令行跑评测

所有命令在**仓库根目录**执行。

**正式全量（断点续跑，中断后可继续）：**

```powershell
python eval1/scripts/run_eval.py --dataset-id instruction_2 --no-fast --progress --concurrency 2
```

**查看进度（不调用 LLM）：**

```powershell
python eval1/scripts/run_eval.py --dataset-id instruction_2 --status
```

**从零全量重跑（旧报告会先备份到 `eval1/outputs/backups/`）：**

```powershell
python eval1/scripts/run_eval.py --dataset-id instruction_2 --fresh --no-fast --progress
```

**部分重跑（合并进已有报告，不清空其他 plan）：**

```powershell
python eval1/scripts/run_eval.py --dataset-id instruction_2 --scenario D10 --progress
python eval1/scripts/run_eval.py --dataset-id instruction_2 --plan-id P36:impatient --progress
```

**调试 / 省成本：**

```powershell
python eval1/scripts/run_eval.py --dataset-id instruction_2 --max-plans 12 --progress
python eval1/scripts/run_eval.py --dataset-id instruction_2 --skip-judge --progress
python eval1/scripts/run_eval.py --dataset-id instruction_2 --fast --max-plans 8 --progress
```

**被测 Bot 切换：**

```powershell
python eval1/scripts/run_eval.py --dataset-id instruction_2 --progress --bot-provider deepseek
```

### 3.4 报告输出

| 被测 Bot | 文件 |
|----------|------|
| Qwen（默认） | `eval1/outputs/eval1_reports_{dataset_id}.json` |
| DeepSeek | `eval1/outputs/eval1_reports_{dataset_id}_deepseek.json` |

恢复备份：

```powershell
python eval1/scripts/restore_report_backup.py --dataset-id instruction_2 --restore
```

### 3.5 常用 CLI 参数

| 参数 | 说明 |
|------|------|
| `--dataset-id` | 数据集，如 `instruction_1`、`instruction_2` |
| `--no-fast` / `--fast` | 正式用 plus / 调试用 turbo |
| `--progress` | 终端显示进度 |
| `--concurrency N` | 并行 plan 数 |
| `--status` | 只看进度，不跑评测 |
| `--fresh` | 全量重跑 |
| `--plan-id` | 只跑指定 plan（可重复） |
| `--scenario` | 只跑 D9 / D10 等场景 |
| `--skip-judge` | 跳过 LLM 评委 |
| `--max-plans N` | 只跑前 N 条（冒烟） |
| `--bot-provider` | `qwen` \| `deepseek` |

---

## 4. 典型流程

1. 配置 `eval1/.env`
2. `python eval1/scripts/run_server.py --reload` 启动后端
3. `cd frontend && npm run dev` 启动前端
4. CLI 跑评测：`run_eval.py --dataset-id instruction_2 --no-fast --progress`
5. 前端打开对应数据集查看 Layer1/2/3 结果

**instruction_2 规模**：约 36 条路径 × 6 种人设 = **216** 条 plan。默认断点续跑，每完成 1 条即写入报告。

---

## 5. 测试

```powershell
pytest eval1/tests -q
```

---

## 6. 参考文档

- [技术设计：图谱建模 / 路径生成 / 评分方法](docs/TECHNICAL_DESIGN.md)
- [系统说明：建图 / 路径 / 评测 / 数据存放](docs/EVAL1_SYSTEM_GUIDE.md)
- [Layer1 节点类型说明](docs/LAYER1_SCENE.md)
