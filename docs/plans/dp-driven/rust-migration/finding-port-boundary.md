# Finding · decay 首切片的录制覆盖边界（2026-11-27 实证）

- `rust-anything bridge . src/zkc/decay.py --out rust/decay-rs --name zkc-decay-rs` 成功，导出 8 个函数；bridge 未改原 Python 源码（git status 只有 rust/ 与 docs/plans/ 新增）。
- `rust-anything record rust/decay-rs --count 60` 得到 **544 cases（108 threw）**：decay_linear 77 / decay_exponential 77 / decay_step 78 / elapsed_days 63 / compute_decay_score 63 / surface 60 / review_reset 63 / refresh_decay 63。
- 关键限制：Python `datetime` 无法穿过 JSON bridge。recorder 生成的 `now`/`node`/`repo` 参数全是标量/列表/字典，因此 `elapsed_days` 的 datetime 分支在录制中**不可达**，输出恒 0.0；`refresh_decay` 全部录制为 `AttributeError: ... has no attribute 'list_by_track'`。
- 结论：首个 port 的 `diff/gate` 只能证明「录制到的退化输入」等价；真实 datetime 语义由从 `tests/test_decay.py` 翻译的 Rust 单测覆盖（Q3 修正口径：录制期 Python 为 oracle，日常回归用 Rust 测试）。**不得把这条 gate 通过表述为整个 decay 模块的生产等价。**
- 录制期未安装 pytest，故未用 `--from-tests`；输入为标准库生成器 + 语义陷阱，未掺入伪造标注或外生锚。
