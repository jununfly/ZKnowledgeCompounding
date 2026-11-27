# Finding · 迁移不可降级约束

1. **行为等价由录制 case 定义**：任何 port 只有在 `diff` 全匹配且 `gate` 通过后才可接线；不得靠「看起来一样」放行。
2. **DB side effects 必须显式录制**：ZKC 主链写 PG（含双时态列、tombstone、归档）；`app record` 需带 `--db-reset` / `--db-dump`，且只用 test DB（zkc-spike-pg :55433 或独立实例）。
3. **外生锚不可伪造**：verdict / 标注 / 完成数只能来自 zj 真实输入；Rust 迁移不得借机批量灌入测试标注。
4. **参数语义锁定**：CALIBRATED 六参数保持数值与来源标记；corpus-derived 永不写回 REGISTRY。
5. **Ollama 调用协议锁定**：原生 `/api/chat` + `format:json`；`/v1` + `response_format` 会永久挂死（qwen3.5-mlx）。
6. **时间语义锁定**：tombstone sweep 使用 aware UTC；naive UTC+8 永远扫不到（ADR-0013）。
7. **过程态边界**：本 carrier 与 `.md` 在 `docs/plans/`，不进长期文档引用；closeout 时删 carrier，只保留治理后的 md。
8. **提交纪律**：feat / chore 分离；未显式触发不 commit/push；临时产物放 `tmp/`（已 gitignore）。
9. **本地 uncommitted 变更**：`docs/architecture/ta-data-flow.md` 有 11-27 文档校订未提交；迁移工作不得覆盖或混同该变更。
