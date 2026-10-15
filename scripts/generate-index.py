#!/usr/bin/env python3
"""
generate-index.py — 自动生成 skills/index.json
遍历所有 SKILL.md 文件，提取 frontmatter 元数据，生成统一索引。

Usage:
    python3 scripts/generate-index.py
    python3 scripts/generate-index.py --output skills/index.json
    python3 scripts/generate-index.py --stats  # 仅输出统计
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime

SKILLS_DIR = Path(__file__).parent.parent / "skills"
DEFAULT_OUTPUT = Path(__file__).parent.parent / "skills" / "index.json"


def parse_frontmatter(content: str) -> dict:
    """解析 SKILL.md 的 YAML frontmatter"""
    if not content.startswith("---"):
        return {}

    end = content.find("---", 3)
    if end == -1:
        return {}

    frontmatter = content[3:end].strip()
    result = {}

    # 简易 YAML 解析（不依赖外部库）
    current_key = None
    current_value = ""
    in_metadata = False
    pending_sub_key = None

    for line in frontmatter.split("\n"):
        # 顶级字段
        match = re.match(r'^(\w+):\s*(.*)$', line)
        if match:
            # 保存前一个键
            if current_key and current_key != "metadata":
                result[current_key] = current_value.strip().strip('"')
            current_key = match.group(1)
            current_value = match.group(2)
            in_metadata = (current_key == "metadata")
            if in_metadata:
                result["metadata"] = {}
                pending_sub_key = None
        # metadata 子字段（缩进），值可以是标量、行内列表，或后续的块状列表项
        elif in_metadata and re.match(r'^\s+\w[\w_]*:', line):
            sub_match = re.match(r'^\s+(\w[\w_]*):\s*(.*)$', line)
            if sub_match:
                key, value = sub_match.group(1), sub_match.group(2).strip()
                result["metadata"][key] = _parse_scalar(value)
                pending_sub_key = key if value == "" else None
        # 块状列表项，续在 key: 之后
        elif in_metadata and pending_sub_key and re.match(r'^\s+-\s', line):
            item = _parse_scalar(re.sub(r'^\s+-\s*', '', line))
            current = result["metadata"][pending_sub_key]
            result["metadata"][pending_sub_key] = current + [item]
        elif current_key and current_key != "metadata" and line.startswith("  "):
            current_value += " " + line.strip()

    if current_key and current_key != "metadata":
        result[current_key] = current_value.strip().strip('"')

    return result


def _parse_scalar(value: str):
    """把 YAML 标量还原成字面值（剥引号），"" 变成空列表以待块状列表项续接。

    行内列表 [a, b] 拆成 ["a", "b"]；引用型字符串（含逗号、方括号）整体保留。
    """
    text = str(value).strip()
    if text == "":
        return []
    if text[0] in "\"'" and len(text) >= 2 and text[-1] == text[0]:
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(x) for x in inner.split(",")]
    return text


def split_tag_list(value) -> list:
    """归一化标签字段：YAML 列表和逗号分隔字符串都接受。"""
    if isinstance(value, list):
        return [str(t).strip() for t in value if str(t).strip()]
    return [t.strip() for t in str(value).split(",") if t.strip()]


def extract_skill_info(skill_path: Path) -> dict:
    """从 SKILL.md 提取技能信息"""
    content = skill_path.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(content)

    # 确定分类（从路径）
    parts = skill_path.relative_to(SKILLS_DIR).parts
    category = parts[0] if len(parts) > 2 else "general"
    skill_name = parts[-2]  # 目录名

    # 提取第一个 # 标题
    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    title = title_match.group(1) if title_match else skill_name

    # 检查 references 目录
    refs_dir = skill_path.parent / "references"
    references = []
    if refs_dir.exists():
        references = [f.name for f in refs_dir.glob("*.md")]

    # 构建技能信息
    info = {
        "name": frontmatter.get("name", skill_name),
        "title": title,
        "category": category,
        "path": str(skill_path.relative_to(SKILLS_DIR.parent)),
        "description": frontmatter.get("description", ""),
        "references": references,
    }

    # 提取 metadata 子字段
    metadata = frontmatter.get("metadata", {})
    if isinstance(metadata, dict):
        if "tags" in metadata:
            info["tags"] = split_tag_list(metadata["tags"])
        if "mitre_attack" in metadata:
            info["mitre_attack"] = split_tag_list(metadata["mitre_attack"])

    return info


def generate_index(output_path: Path = None, stats_only: bool = False) -> dict:
    """生成完整索引"""
    skills = []
    categories = {}

    # 遍历所有 SKILL.md
    for skill_file in sorted(SKILLS_DIR.rglob("SKILL.md")):
        # 跳过 .claude/ 等隐藏目录
        if any(part.startswith(".") for part in skill_file.parts):
            continue

        try:
            info = extract_skill_info(skill_file)
            skills.append(info)

            # 分类统计
            cat = info["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(info["name"])
        except Exception as e:
            print(f"[WARN] 解析失败: {skill_file} — {e}", file=sys.stderr)

    # 构建索引
    index = {
        "generated_at": datetime.now().isoformat(),
        "total_skills": len(skills),
        "categories": {cat: len(names) for cat, names in sorted(categories.items())},
        "skills": skills,
    }

    # 统计输出
    if stats_only:
        print(f"\n{'='*50}")
        print(f" AboutSecurity Skills Index")
        print(f"{'='*50}")
        print(f" 总技能数: {len(skills)}")
        print(f" 分类数:   {len(categories)}")
        print(f"{'─'*50}")
        for cat, names in sorted(categories.items(), key=lambda x: -len(x[1])):
            print(f"  {cat:20} {len(names):3} skills")
        print(f"{'─'*50}")

        # MITRE ATT&CK 覆盖统计
        all_techniques = set()
        for skill in skills:
            for t in skill.get("mitre_attack", []):
                all_techniques.add(t)
        print(f"  MITRE ATT&CK 技术覆盖: {len(all_techniques)} techniques")

        # 有 references 的 skill 比例
        with_refs = sum(1 for s in skills if s["references"])
        print(f"  含 references 的 skill: {with_refs}/{len(skills)} ({100*with_refs//len(skills)}%)")
        print(f"{'='*50}\n")
        return index

    # 写入文件
    if output_path is None:
        output_path = DEFAULT_OUTPUT

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"[+] 索引已生成: {output_path}")
    print(f"    总技能数: {len(skills)}, 分类数: {len(categories)}")

    return index


def main():
    parser = argparse.ArgumentParser(description="生成 AboutSecurity skills 索引")
    parser.add_argument("--output", "-o", type=Path, default=None, help="输出路径 (默认: skills/index.json)")
    parser.add_argument("--stats", action="store_true", help="仅输出统计信息")
    args = parser.parse_args()

    generate_index(output_path=args.output, stats_only=args.stats)


if __name__ == "__main__":
    main()
