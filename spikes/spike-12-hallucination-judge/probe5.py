"""Probe5: raw OpenAI completion (NO instructor) + manual JSON extraction, timed.

If this returns in seconds, the judge should use manual JSON parsing instead of
instructor.Mode.JSON (which hangs on qwen3.5's reasoning stream via Ollama)."""
import os
import re
import time
from openai import OpenAI

import judge

os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama", timeout=120)
prompt = judge.build_prompt(judge.GOLDEN[6]["claim"], judge.corpus.SOURCES)  # g7 contradicted


def extract_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.S)
    s, e = text.find("{"), text.rfind("}")
    if s >= 0 and e > s:
        text = text[s:e + 1]
    return judge.Judgment.model_validate_json(text).model_dump()


t = time.time()
resp = client.chat.completions.create(
    model="qwen3.5:4b-mlx",
    messages=[{"role": "system", "content": judge.SYSTEM},
              {"role": "user", "content": prompt}],
    temperature=0.2, stream=False, timeout=120,
    extra_body={"think": False, "options": {"num_ctx": 8192}},
)
content = resp.choices[0].message.content or ""
print("raw took", round(time.time() - t, 1), "s; content_len=", len(content))
print("---content---")
print(content[:600])
try:
    d = extract_json(content)
    print("---parsed overall=", d["overall"], "atomic=", len(d["atomic_facts"]))
except Exception as e:  # noqa: BLE001
    print("PARSE ERR", type(e).__name__, str(e)[:200])
