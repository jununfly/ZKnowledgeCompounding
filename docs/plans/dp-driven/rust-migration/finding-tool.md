# Finding · rust-anything 工具事实（2026-11-27 实跑）

- 安装：`npm install -g rust-anything` 成功；`rust-anything --version` = **5.0.0**（官方文档按 5.0.1 生成）。二进制在托管 Node 22.22.2 的 global bin 下，已在 PATH。
- `doctor --json`：MCP server ok（24 tools）；**cargo 1.95.0 不满足 1.97+ 要求**（required，退出码 1）→ 已启动 `rustup update stable`。Python 3.13.12 / Node 22.22.2 / clang 21 / Go 1.27.2 均 ok。Claude/Codex/OpenCode 的 MCP+skill 均缺失，但本会话用 CLI，不依赖它们。
- 官方 workflow：Record → Port → Check → Lift。`record` 运行原实现、`app record` 每个 case 跑两遍；在有 DB / 网络 / 文件写入的项目上必须在副本 + test DB 上跑，不得带生产凭据。
- Python unit bridge = PyO3 (abi3)，unit 可为 package/module；`record --from-tests -- pytest` 可把原测试套件的调用录成 case；Python 3.9+。
- gate 的语义 = 录制 case 全匹配 + 无拷贝答案/unsafe/缺测试；**只证明录制覆盖到的行为**。`recorded-from.json` 记录源文件指纹，原实现变动后必须重录。
- 官方 limits 明确不比较：未录制输入、时序/内存/并发、未显式录制的副作用（HTTP/SMTP/DB 需 `app record --effects` / `--db-reset`/`--db-dump`）。
- `analyze . --whole-app --json` 成功，产物 89,992 bytes → `tmp/rust-analyze-whole-app.json`（tmp/ gitignored）。
