"""Render a CodegenBundle into the text handed to the generating agent.

Per [TDD]-codegen_brief: the sub-agent's isolated window holds only this text,
so it must carry the task statement, the target file, the file status and the
authority order by itself — and the spec must survive verbatim (no escaping).
Pure function module: no IO, no global state, deterministic output.
"""

from __future__ import annotations

# (title, selection_reasons) — the tuple order IS the authority order, descending.
#   None → take bundle.chunks (the TDD body itself, highest authority)
#   ()   → rendered from target_file_content (the trailing "current state" section)
# The five middle entries cover all seven selection_reason values exactly once.
SECTIONS: tuple[tuple[str, tuple[str, ...] | None], ...] = (
    ("实现规格（权威 · 必须完整实现）", None),
    ("直接开发依据 · 父 FSD 能力契约", ("parent_split",)),
    ("依赖的对外接口（按此调用，不要重新实现）", ("depends_on_contract",)),
    ("所属域约束（边界，不得越界）", ("fsd_ancestor", "test_covered_sibling")),
    ("相关实现参考", ("test_implementation_tdd",)),
    ("产品意图（仅供理解，不要据此扩范围）", ("prd_root", "prd_requirement")),
    ("目标文件现状", ()),
)

STATUS_TEXT: dict[str, str] = {
    "loaded": "现有源码见文末〈目标文件现状〉，请做**增量修改**，不要重写无关部分。",
    "absent": "该文件**尚不存在**，需新建。",
    "unreadable": (
        "⚠ 该文件**存在但无法读取**（编码、权限或其他 IO 原因）。"
        "**禁止生成代码**，请直接报错退出——否则既有实现会被当作空文件而被整体覆盖。"
    ),
}

EMPTY_MARK = "（无）"


def _spec_block(item: dict) -> str:
    """Wrap one spec chunk in id/file-tagged boundaries, content byte-for-byte.

    XML-style markers rather than a markdown fence: chunk content itself holds
    ``##`` headings and ``` fences, which would close an outer fence early.
    """
    return '<spec id="%s" file="%s">\n%s\n</spec>' % (
        item.get("id", ""),
        item.get("file", ""),
        (item.get("content") or "").rstrip(),
    )


def _code_block(path: str, content: str) -> str:
    return '<current_code path="%s">\n%s\n</current_code>' % (path, content.rstrip())


def render(bundle) -> str:
    """CodegenBundle → the markdown text injected into the generating agent."""
    # Unknown status falls back to `unreadable`: refusing to generate is always
    # safer than mistaking an unreadable file for a new one and overwriting it.
    status = bundle.target_file_status if bundle.target_file_status in STATUS_TEXT else "unreadable"

    pool: dict[str, dict] = {}
    for item in list(bundle.upstream) + list(bundle.dependencies):
        pool.setdefault(item["id"], item)

    lines: list[str] = [
        "# Codegen Task — `%s`" % bundle.tdd_root,
        "",
        "| 项 | 值 |",
        "|---|---|",
        "| 目标文件（唯一可改） | `%s` |" % bundle.target_file,
        "| 文件状态 | `%s` |" % status,
        "| 规格来源 | `%s` @ `%s` |" % (bundle.source_file, bundle.version),
        "",
        STATUS_TEXT[status],
        "",
        "**任务**：按下方〈实现规格〉生成或修改 `%s` 这一个文件，不要动其他文件。" % bundle.target_file,
        "**权威顺序**：章节序即优先级，从上到下递减；规格与现有代码冲突时以规格为准。",
        "**边界**：FSD 的「反向要求」与 TDD 的「本文件不负责」是硬约束，不得越界实现。",
        "",
    ]

    for index, (title, reasons) in enumerate(SECTIONS, 1):
        if reasons == ():
            heading = "## %d. %s — `%s`" % (index, title, bundle.target_file)
        else:
            heading = "## %d. %s" % (index, title)
        lines += ["---", "", heading, ""]

        if reasons is None:
            blocks = [_spec_block(chunk) for chunk in bundle.chunks]
        elif reasons == ():
            content = bundle.target_file_content
            blocks = [_code_block(bundle.target_file, content)] if content is not None else []
        else:
            items = sorted(
                (item for item in pool.values() if item.get("selection_reason") in reasons),
                key=lambda item: item["id"],
            )
            blocks = [_spec_block(item) for item in items]

        # An empty section is still information ("no external dependency"),
        # so it is marked explicitly rather than omitted.
        for block in blocks or [EMPTY_MARK]:
            lines += [block, ""]

    return "\n".join(lines).rstrip() + "\n"
