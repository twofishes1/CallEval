# Eval1 数据目录

- `data.xlsx`：内置多行数据集（与历史竞赛表一致）
- `uploads/`：前端/API 上传的文件（`.xlsx` / `.json` / `.txt`）

上传后通过 `GET /api/eval1/datasets` 可见；全流程评测：`POST /api/eval1/pipeline/{dataset_id}/run`。
