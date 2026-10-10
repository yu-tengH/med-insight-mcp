"""自動評估：讓 Claude 透過 MCP 工具回答題庫，每次回答存一行 JSONL。

用法：
    uv run python eval/run_eval.py --limit 2 --runs 1     # 測試
    uv run python eval/run_eval.py                        # 20 題 × 3 次
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import anthropic
import anyio
from dotenv import load_dotenv
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = ROOT / "eval" / "questions.json"
SYSTEM_PROMPT_PATH = ROOT / "prompts" / "system.md"
SERVER_PATH = ROOT / "server" / "fhir_server.py"
RESULTS_DIR = ROOT / "eval" / "results"

MAX_TOOL_ROUNDS = 10  # 每題最多幾輪工具呼叫
MAX_TOKENS = 16000


def mcp_tools_to_anthropic(tools) -> list[dict]:
    """把 MCP 的工具定義轉成 Anthropic API 的 tools 格式。"""
    return [
        {
            "name": t.name,
            "description": t.description or "",
            "input_schema": t.input_schema,
        }
        for t in tools
    ]


def tool_result_text(result) -> str:
    """把 MCP 的 CallToolResult 轉成給 Claude 讀的文字。

    回傳 list 的工具，structured_content 是 {"result": [...]}，一次序列化最完整；
    回傳 dict 的工具沒有 structured_content，就把 content 裡的文字串起來。
    """
    if result.structured_content is not None:
        return json.dumps(result.structured_content, ensure_ascii=False)
    texts = [b.text for b in result.content if isinstance(b, TextContent)]
    return "\n".join(texts)


async def call_mcp_tool(client: Client, name: str, args: dict) -> tuple[str, bool]:
    """執行一個 MCP 工具，回傳 (結果文字, 是否出錯)。任何例外都轉成錯誤結果，不讓程式中斷。"""
    try:
        result = await client.call_tool(name, args)
    except Exception as e:  # MCPError、連線問題等
        return f"工具執行失敗：{type(e).__name__}: {e}", True
    return tool_result_text(result), bool(result.is_error)


async def run_one(
    claude: anthropic.AsyncAnthropic,
    mcp_client: Client,
    tools: list[dict],
    system_prompt: str,
    model: str,
    question: dict,
    run: int,
) -> dict:
    """用一個全新的對話回答一題，跑完整個工具迴圈。"""
    messages = [{"role": "user", "content": question["question"]}]
    tool_calls = []
    usage = {"input_tokens": 0, "output_tokens": 0,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    final_answer = ""
    stop_reason = None
    hit_tool_limit = False
    error = None
    rounds = 0
    start = time.perf_counter()

    try:
        while True:
            response = await claude.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                tools=tools,
                messages=messages,
                cache_control={"type": "ephemeral"},
            )
            for key in usage:
                usage[key] += getattr(response.usage, key, 0) or 0
            stop_reason = response.stop_reason

            if response.stop_reason != "tool_use":
                final_answer = "".join(b.text for b in response.content if b.type == "text")
                break

            if rounds >= MAX_TOOL_ROUNDS:
                hit_tool_limit = True
                final_answer = "".join(b.text for b in response.content if b.type == "text")
                break
            rounds += 1

            # 整段 content 原樣放回對話（含 thinking 區塊），工具結果全部放在同一則 user 訊息
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                text, is_error = await call_mcp_tool(mcp_client, block.name, block.input)
                tool_calls.append({
                    "round": rounds,
                    "name": block.name,
                    "input": block.input,
                    "is_error": is_error,
                })
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": text,
                    "is_error": is_error,
                })
            messages.append({"role": "user", "content": results})
    except anthropic.APIError as e:
        error = f"{type(e).__name__}: {e}"

    return {
        "id": question["id"],
        "run": run,
        "model": model,
        "patient_id": question["patient_id"],
        "category": question["category"],
        "question": question["question"],
        "final_answer": final_answer,
        "stop_reason": stop_reason,
        "tool_calls": tool_calls,
        "tool_rounds": rounds,
        "hit_tool_limit": hit_tool_limit,
        "usage": usage,
        "elapsed_seconds": round(time.perf_counter() - start, 2),
        "error": error,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="MCP + FHIR 自動評估")
    parser.add_argument("--model", default="claude-sonnet-5-5")
    parser.add_argument("--runs", type=int, default=3, help="每題跑幾次")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 題（測試用）")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    claude = anthropic.AsyncAnthropic()

    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    if args.limit:
        questions = questions[: args.limit]
    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"{stamp}_{args.model}.jsonl"
    server_log_path = RESULTS_DIR / f"{stamp}_{args.model}_server.log"

    # 用目前的 Python（uv 的虛擬環境）以 stdio 啟動 MCP server；server 的 log 另存檔案，不洗版
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_PATH)], cwd=str(ROOT))
    total = len(questions) * args.runs
    done = 0

    with open(server_log_path, "w", encoding="utf-8") as server_log, \
            open(out_path, "w", encoding="utf-8") as out:
        async with Client(stdio_client(params, errlog=server_log)) as mcp_client:
            mcp_tools = (await mcp_client.list_tools()).tools
            tools = mcp_tools_to_anthropic(mcp_tools)
            print(f"MCP 工具：{[t['name'] for t in tools]}")
            print(f"模型：{args.model}，{len(questions)} 題 × {args.runs} 次 = {total} 次")

            for q in questions:
                for run in range(1, args.runs + 1):
                    record = await run_one(claude, mcp_client, tools, system_prompt,
                                           args.model, q, run)
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    out.flush()
                    done += 1
                    flag = " ⚠️超過工具上限" if record["hit_tool_limit"] else ""
                    flag += f" ❌{record['error']}" if record["error"] else ""
                    print(f"[{done}/{total}] {q['id']} run{run}："
                          f"{len(record['tool_calls'])} 次工具，"
                          f"{record['elapsed_seconds']}s{flag}")

    print(f"結果已存到 {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    anyio.run(main)
