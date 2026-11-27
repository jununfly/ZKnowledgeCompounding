# Evidence · routing 词法 TF-IDF 纯函数切片（ticket 25）

> 过程态证据，非持久权威。ticket 8 仍在进行；本片是它的下一个子切片。

## 结论

`rust/routing-tfidf-rs` 复刻了 `src/zkc/routing.py` 的 3 个字面 TF-IDF 纯函数。
DP：finding 12 + ticket 25（parent 8，blocks `25→8`）已完成，租约释放，`validate` 0 errors。
录制期 Python 原实现仍是唯一 oracle。

## 切片范围

`tokenize`（原 `_tokenize`）/ `tfidf_vector`（原 `_tfidf_vector`）/ `cosine`（原 `_cosine`）。
入参只有字符串、字符串列表、`dict[str, float]`；无 Storage、LLM、dataclass、
callable、datetime。process-only 别名 `spikes/spike-15-routing-tfidf/pure_bridge.py`
只提供公开名字，决策逐字委托原实现。

## 关键语义

- **分词**：先 `lower()`，再匹配 `[a-z0-9]+|[\u4e00-\u9fff]`。英文/数字成串，
  中文逐字输出；标点、emoji、下划线等丢弃。录制覆盖 `İstanbul STRASSE ß`
  → `["i","stanbul","strasse"]`：Python/Rust 的 Unicode 小写映射把 `İ` 拆成
  `i` + 组合点，组合点随后被正则丢弃，`ß` 不在 `[a-z]` 内也被丢弃。
- **TF-IDF 保序**：返回 map 的 key 顺序是 token **首次出现顺序**（如
  `["b","a","b","c"]` → `b,a,c`），不是字母序。bridge 生成的 Cargo.toml 自带
  `serde_json` `preserve_order` feature，Rust 侧用 `Map` 直接保序，逐字对齐。
  缺失 idf 键贡献 0.0；空 token 列表返回空 map。
- **余弦**：`common = set(a) & set(b)` 为空返回 0.0，零范数返回 0.0；范数按
  dict 插入序求和。Python 的 set 迭代受字符串 hash salt 影响，3 项以上共同键
  时浮点加法末位可能跨进程不稳；Rust 侧对 common **排序**取确定性口径。
  录制含 4 键交集与负数权重 case，**25/25 逐字匹配**（无 float tolerance）。
- **阈值边界**：`LexicalRouter` 的 corpus-derived gate 与 tuning 的 CALIBRATED
  不是一回事；本片不触碰任何阈值，也不写回 REGISTRY。

## 机械验证

| 检查 | 结果 |
|---|---|
| `rust-anything diff` | **25/25** recorded cases match（0 threw；10 tokenize / 7 tfidf / 8 cosine） |
| `rust-anything gate` | **Gate passed**（fmt/clippy/cargo test/unsafe/lockfile/ported/size **1.4x**/literals/tests/errors/panics/build/api/behavior 全绿） |
| `app replay --build` 既有 11 case | **11/11 passed**，fallback **0.0%**（本片未接线，零回退） |
| `make test` | **671 OK** |
| mcp-gate / invariant / authority | **6/6** / **0 violations** / **0 leaks**（1048 sources） |

## 边界与风险

- **不是路由放行**：只证 3 个字面数值函数；`route_text` / `LexicalRouter.fit|predict` /
  `DecisionRouter` / `ChatClient` / `OllamaClient`、tuning gate 与 `lexical_corpus`
  持久化留 Python。R16 的 embedding 禁用约束本片未触碰。
- **未 wire 进 `rust/app`**；25 case 是人工定向输入，不是全输入空间证明。
  `_cosine` 的 set 迭代顺序只在录制口径上对齐，不能外推为跨进程 hash 顺序稳定。
- 3 个 Rust 常量均标 `recorded-literal`，未 promote；`src/zkc/**` 零改动，
  `zkc` CLI 未加命令。
