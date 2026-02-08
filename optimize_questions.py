#!/usr/bin/env python3
"""
CIPP/E 题库深度优化脚本
========================
利用 DeepSeek API 为每道题生成：
  - legalReference : 精准的 GDPR / ePrivacy / ECHR 条文原文
  - analysis       : "微型学术论文"级别的考点深度解析

用法：
  1. 设置环境变量  export DEEPSEEK_API_KEY="sk-xxxxxxxx"
  2. 运行脚本      python3 optimize_questions.py

技术特性：
  - asyncio + Semaphore 并发 20
  - DeepSeek Context Caching（自动触发，GDPR 全文作为 system 前缀）
  - 断点续传：analysis 字段 > 500 字符的题目自动跳过
  - 每 5 题实时回写 questions.json
"""

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import openai
except ImportError:
    print("=" * 60)
    print("错误：缺少 openai 库，请运行：")
    print("  pip install openai")
    print("=" * 60)
    sys.exit(1)

# ──────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-chat"                 # DeepSeek-V3；如需 R1 改为 deepseek-reasoner
CONCURRENCY = 20                        # 最大并发请求数
SAVE_EVERY = 5                          # 每处理 N 题回写一次
SKIP_THRESHOLD = 500                    # analysis 字段超过此字符数视为已完成
MAX_RETRIES = 3                         # 单题最大重试次数

QUESTIONS_PATH = Path(__file__).parent / "references" / "questions.json"
GDPR_PATH = Path(__file__).parent / "GDPR.md"


# ──────────────────────────────────────────────
# 构建 System Prompt（含 GDPR 全文 → 触发缓存）
# ──────────────────────────────────────────────
def build_system_prompt(gdpr_text: str) -> str:
    """
    将 GDPR 全文嵌入 system prompt 的开头，
    DeepSeek 会自动对前缀做"硬盘缓存"(Context Caching)，
    后续请求命中缓存后按 0.1 元 / 百万 token 计费（仅原价 1/10）。
    """
    return f"""你是一位资深的欧盟数据保护法律学者和 CIPP/E 考试培训专家。

以下是《通用数据保护条例》(GDPR) 的完整法律文本，供你在分析中精确引用：

<gdpr_full_text>
{gdpr_text}
</gdpr_full_text>

你的任务是为 CIPP/E 考试题目生成两部分内容：

═══ 第一部分：legalReference（法条原文）═══
- 找出与该题目最直接相关的 GDPR 条款（通常 1-3 条）
- 从上面的 GDPR 全文中逐字摘录对应条款的原文
- 格式："GDPR Article N - 标题\\n\\n条文正文"
- 如涉及多条，用 "\\n\\n---\\n\\n" 分隔
- 如果题目涉及非 GDPR 法源（如 ECHR, ePrivacy Directive, Convention 108），
  请标明来源并提供条文原文
- 清理 Markdown 格式符号（#, *, 等），只保留干净的法律文本

═══ 第二部分：analysis（考点深度解析）═══
请用中文撰写一篇"微型学术论文"级别的解析（800-1500字），使用自然段落，
不使用 Markdown 标题。必须包含以下 4 个模块，每个模块作为独立段落：

1.【考点定位】明确本题考查的欧盟数据保护法律知识点和法律概念，
   指出对应的 CIPP/E 考试 Domain：
   - Domain I: European Context (Institutions, History, Human Rights)
   - Domain II: GDPR Principles, Rights, Controllers/Processors, Transfers
   - Domain III: Compliance, Security, Accountability, Internet Technology

2.【法理深度】引用 GDPR 具体条款和 Recital 编号，解释立法逻辑和背景。

3.【判例与场景】引用真实的欧盟法院判例（如 Schrems II, Google Spain,
   Planet 49, Fashion ID 等）或监管机构罚款案例。如无直接判例，
   构建一个贴近实务的业务场景进行类比分析。

4.【知识图谱】串联相关知识点，展示本题考点与其他 GDPR 主题的关联。
   例如：提到"同意"时，一并梳理同意的定义(Art.4)、有效条件(Art.7)、
   儿童同意(Art.8)、特殊类别数据的明确同意(Art.9)等。

═══ 输出格式 ═══
请严格输出一个 JSON 对象，不要包含任何其他文字：
{{
  "legalReference": "...",
  "analysis": "..."
}}
"""


# ──────────────────────────────────────────────
# 构建单题的 User Prompt
# ──────────────────────────────────────────────
def build_user_prompt(q: dict) -> str:
    options_text = "\n".join(
        f"  {'ABCD'[i]}. {opt}" for i, opt in enumerate(q["options"])
    )
    correct_letter = 'ABCD'[q["correctAnswer"]]

    scenario_part = ""
    if q.get("scenario", "").strip():
        scenario_part = f"\n【背景场景】\n{q['scenario']}\n"

    return f"""请分析以下 CIPP/E 考试题目：
{scenario_part}
【题目】{q['question']}

【选项】
{options_text}

【正确答案】{correct_letter}

【现有解释】{q.get('explanation', '')}

请根据 system prompt 中的指令，输出包含 legalReference 和 analysis 的 JSON 对象。"""


# ──────────────────────────────────────────────
# JSON 清洗：去除 ```json 等标记
# ──────────────────────────────────────────────
def clean_json_response(raw: str) -> dict:
    """从 API 返回文本中提取干净的 JSON 对象。"""
    text = raw.strip()

    # 去除 ```json ... ``` 包裹
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    text = text.strip()

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 退而求其次：提取第一个 { ... } 块
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法从 API 返回中解析 JSON:\n{raw[:500]}")


# ──────────────────────────────────────────────
# 单题处理
# ──────────────────────────────────────────────
async def process_one(
    client: openai.AsyncOpenAI,
    system_prompt: str,
    question: dict,
    semaphore: asyncio.Semaphore,
) -> tuple[int, dict | None]:
    """
    调用 DeepSeek API 处理单道题。
    返回 (question_id, {legalReference, analysis}) 或 (question_id, None)。
    """
    qid = question["id"]

    async with semaphore:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": build_user_prompt(question)},
                    ],
                    temperature=0.3,
                    max_tokens=4096,
                )
                raw = response.choices[0].message.content
                result = clean_json_response(raw)

                # 校验必要字段
                if "legalReference" not in result or "analysis" not in result:
                    raise ValueError(f"返回缺少必要字段: {list(result.keys())}")

                print(f"  ✓ Q{qid} 完成 (attempt {attempt})")
                return (qid, result)

            except Exception as e:
                wait = 2 ** attempt
                print(f"  ✗ Q{qid} 第 {attempt} 次失败: {e}")
                if attempt < MAX_RETRIES:
                    print(f"    等待 {wait}s 后重试...")
                    await asyncio.sleep(wait)
                else:
                    print(f"  ✗ Q{qid} 已达最大重试次数，跳过")
                    return (qid, None)


# ──────────────────────────────────────────────
# 实时回写
# ──────────────────────────────────────────────
def save_questions(questions: list, path: Path):
    """原子写入 questions.json（先写临时文件再重命名）。"""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────
async def main():
    # ── 检查 API Key ──
    if not DEEPSEEK_API_KEY:
        print("=" * 60)
        print("错误：未设置 DEEPSEEK_API_KEY 环境变量")
        print()
        print("请执行以下命令（替换为你的真实 key）：")
        print('  export DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"')
        print()
        print("然后重新运行：")
        print("  python3 optimize_questions.py")
        print("=" * 60)
        sys.exit(1)

    # ── 加载数据 ──
    print("正在加载数据...")
    if not QUESTIONS_PATH.exists():
        print(f"错误：找不到 {QUESTIONS_PATH}")
        sys.exit(1)
    if not GDPR_PATH.exists():
        print(f"错误：找不到 {GDPR_PATH}")
        sys.exit(1)

    with open(QUESTIONS_PATH, "r", encoding="utf-8") as f:
        questions = json.load(f)
    with open(GDPR_PATH, "r", encoding="utf-8") as f:
        gdpr_text = f.read()

    print(f"  题目总数: {len(questions)}")
    print(f"  GDPR 文本: {len(gdpr_text):,} 字符")

    # ── 断点续传：筛选需要处理的题目 ──
    to_process = []
    skipped = 0
    for q in questions:
        existing = q.get("analysis", "")
        if len(existing) > SKIP_THRESHOLD:
            skipped += 1
        else:
            to_process.append(q)

    print(f"  已完成(跳过): {skipped}")
    print(f"  待处理: {len(to_process)}")

    if not to_process:
        print("\n所有题目已完成，无需处理。")
        return

    # ── 构建 system prompt（包含 GDPR 全文，触发缓存） ──
    system_prompt = build_system_prompt(gdpr_text)
    print(f"  System Prompt: ~{len(system_prompt):,} 字符 (含 GDPR 全文，将触发缓存)")

    # ── 初始化客户端 ──
    client = openai.AsyncOpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
    )
    semaphore = asyncio.Semaphore(CONCURRENCY)

    # ── 建立 id → index 映射 ──
    id_to_idx = {q["id"]: i for i, q in enumerate(questions)}

    # ── 并发处理 ──
    print(f"\n开始处理（并发={CONCURRENCY}）...\n")
    completed_since_save = 0
    total_done = 0
    failed = 0
    start_time = time.time()

    # 创建所有任务
    tasks = [
        asyncio.create_task(
            process_one(client, system_prompt, q, semaphore)
        )
        for q in to_process
    ]

    for future in asyncio.as_completed(tasks):
        qid, result = await future

        if result:
            idx = id_to_idx[qid]
            questions[idx]["legalReference"] = result["legalReference"]
            questions[idx]["analysis"] = result["analysis"]
            completed_since_save += 1
            total_done += 1

            # 每 SAVE_EVERY 题回写一次
            if completed_since_save >= SAVE_EVERY:
                save_questions(questions, QUESTIONS_PATH)
                elapsed = time.time() - start_time
                rate = total_done / elapsed * 60 if elapsed > 0 else 0
                print(f"  >> 已保存 ({total_done}/{len(to_process)} 完成, "
                      f"{rate:.1f} 题/分钟)")
                completed_since_save = 0
        else:
            failed += 1

    # ── 最终保存 ──
    save_questions(questions, QUESTIONS_PATH)
    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"全部完成！")
    print(f"  成功: {total_done}/{len(to_process)}")
    print(f"  失败: {failed}")
    print(f"  总耗时: {elapsed:.1f} 秒")
    print(f"  结果已保存到: {QUESTIONS_PATH}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
