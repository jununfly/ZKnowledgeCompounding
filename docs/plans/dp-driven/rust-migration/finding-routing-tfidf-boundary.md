# Finding 12 · routing 词法 TF-IDF 的可证边界

> 过程态观察，结论须提炼到 durable 文档后才算长期事实。

## 观察

`src/zkc/routing.py` 的双轨分流第二信号（LexicalRouter，embedding-free）底层有 3 个
全标量/字符串/字符串列表/字符串-浮点字典入参的纯函数：

- `_tokenize(text) -> list[str]`
- `_tfidf_vector(tokens, idf) -> dict[str, float]`
- `_cosine(a, b) -> float`

三者无 Storage、LLM、dataclass、callable、datetime；适合 PyO3 JSON bridge，录制期
Python 原实现可作唯一 oracle。

## 边界与风险

- `route_text` / `LexicalRouter.fit|predict` / `DecisionRouter` / `ChatClient` /
  `OllamaClient` 吃 LLM、Storage、tuning gate、`lexical_corpus` 文件，留 Python。
- `_tfidf_vector` 的返回 dict 按 token **首次出现顺序**插入；JSON 字节级对齐需
  保序 Map（`serde_json` `preserve_order`），否则 key 排序会产生伪差异。
- `_cosine` 用 `set(a) & set(b)` 求交集后 `sum(...)`；3 项以上共同键时，Python 的
  set 迭代顺序会影响浮点加法舍入。录制与 oracle 是不同进程，须显式覆盖该情形，
  不能靠"通常顺序一样"蒙混。
- `_TOKEN_RE = [a-z0-9]+|[\u4e00-\u9fff]` 先 `text.lower()`：英文/数字成串、中文
  逐字；`lower()` 的 Unicode 完整映射（如 `İ`、`ß`）与 Rust `to_lowercase()` 需逐例对齐。
- gate 推导的阈值属 `corpus-derived`，与 tuning 的 `CALIBRATED` 不等价，绝不写回
  REGISTRY；本切片不触碰阈值。

## 处置

新增 ticket 25（parent 8，blocks `25→8`）：以 process-only alias 暴露这 3 个函数，
定向录制后 port 到 Rust；只证明字面数值行为，不构成路由放行或安全判定保证。
