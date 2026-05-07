from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_URL = "https://github.com/msitarzewski/agency-agents"
STOPWORDS = {
    "a",
    "an",
    "and",
    "agent",
    "agents",
    "as",
    "at",
    "be",
    "build",
    "can",
    "code",
    "create",
    "data",
    "default",
    "design",
    "developer",
    "development",
    "engineer",
    "engineering",
    "for",
    "from",
    "grade",
    "in",
    "into",
    "its",
    "level",
    "manager",
    "marketing",
    "of",
    "on",
    "or",
    "platform",
    "production",
    "project",
    "role",
    "sales",
    "specialist",
    "style",
    "support",
    "system",
    "systems",
    "testing",
    "that",
    "the",
    "to",
    "tooling",
    "with",
    "writes",
    "your",
}
SECTION_MAPPINGS = {
    "identity": "identity_memory",
    "memory": "identity_memory",
    "mission": "core_mission",
    "critical rules": "critical_rules",
    "workflow": "workflow_process",
    "communication style": "communication_style",
    "success metrics": "success_metrics",
    "advanced capabilities": "advanced_capabilities",
    "technical deliverables": "technical_deliverables",
    "learning": "learning_memory",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert agency-agents markdown personas into platform skill-pack JSON.")
    parser.add_argument(
        "--source-dir",
        default=str(Path("D:/ai合作产品/.tmp-agency-agents-ref")),
        help="Path to a cloned agency-agents repository.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output JSON path. Defaults to artifacts/agency-agents-skill-pack-preview-<timestamp>.json",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional maximum number of markdown files to convert.",
    )
    return parser.parse_args()


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def try_parse_yaml(frontmatter: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(frontmatter)
        return data if isinstance(data, dict) else {}
    except Exception:
        result: dict[str, Any] = {}
        for raw_line in frontmatter.splitlines():
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip().strip("'\"")
        return result


def split_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    return try_parse_yaml(parts[1]), parts[2].lstrip()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)


def normalize_heading(heading: str) -> str:
    heading = re.sub(r"[^\w\s&/-]+", " ", heading, flags=re.UNICODE)
    heading = re.sub(r"\s+", " ", heading).strip().lower()
    return heading


def tokenize(value: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9][a-z0-9+#._/-]{1,}", value.lower())
    normalized = []
    for token in tokens:
        token = token.strip("./-_")
        if len(token) < 2 or token in STOPWORDS:
            continue
        normalized.append(token)
    return normalized


def parse_markdown_sections(body: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_heading = "overview"
    sections[current_heading] = []
    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("#"):
            current_heading = normalize_heading(stripped.lstrip("#").strip()) or "overview"
            sections.setdefault(current_heading, [])
            continue
        if not stripped:
            continue
        bullet = stripped
        if bullet.startswith("- "):
            bullet = bullet[2:].strip()
        elif re.match(r"^\d+\.\s+", bullet):
            bullet = re.sub(r"^\d+\.\s+", "", bullet)
        sections.setdefault(current_heading, []).append(bullet)
    return sections


def pick_section(sections: dict[str, list[str]], *keywords: str) -> list[str]:
    for title, items in sections.items():
        if all(keyword in title for keyword in keywords):
            return items
    for keyword in keywords:
        for title, items in sections.items():
            if keyword in title:
                return items
    return []


def map_sections(sections: dict[str, list[str]]) -> dict[str, list[str]]:
    mapped: dict[str, list[str]] = {}
    for title, items in sections.items():
        target = None
        for key, mapped_name in SECTION_MAPPINGS.items():
            if key in title:
                target = mapped_name
                break
        if target is None:
            continue
        mapped[target] = items
    return mapped


def build_recommended_for(category: str, frontmatter: dict[str, Any], sections: dict[str, list[str]], relative_path: str) -> list[str]:
    bag: list[str] = []
    bag.extend(tokenize(category))
    bag.extend(tokenize(relative_path))
    bag.extend(tokenize(str(frontmatter.get("name", ""))))
    bag.extend(tokenize(str(frontmatter.get("description", ""))))
    bag.extend(tokenize(str(frontmatter.get("vibe", ""))))
    for key in ("core_mission", "critical_rules", "workflow_process", "success_metrics"):
        for item in map_sections(sections).get(key, [])[:6]:
            bag.extend(tokenize(item))
    counts = Counter(bag)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _count in ranked[:12]]


def convert_markdown_file(path: Path, source_root: Path) -> dict[str, Any] | None:
    raw = path.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(raw)
    if not frontmatter.get("name") and not frontmatter.get("description"):
        return None
    relative_path_obj = path.relative_to(source_root)
    relative_path = relative_path_obj.as_posix()
    category = relative_path_obj.parts[0] if len(relative_path_obj.parts) > 1 else "root"
    stem = path.stem
    stem_without_category = stem[len(category) + 1 :] if stem.startswith(f"{category}-") else stem
    skill_id = f"agency-{slugify(stem_without_category)}"
    sections = parse_markdown_sections(body)
    mapped_sections = map_sections(sections)
    name = str(frontmatter.get("name") or stem_without_category.replace("-", " ").title()).strip()
    description = str(frontmatter.get("description") or "").strip()
    vibe = str(frontmatter.get("vibe") or "").strip()
    note_parts = [part for part in [description, vibe] if part]
    note = " / ".join(note_parts) if note_parts else f"Imported from agency-agents: {name}"
    return {
        "id": skill_id,
        "label": f"Agency / {name}",
        "note": note,
        "source": "agency-agents",
        "scope": "role",
        "recommended_for": build_recommended_for(category, frontmatter, sections, relative_path),
        "metadata": {
            "external_repo": REPO_URL,
            "external_path": relative_path,
            "category": category,
            "name": name,
            "description": description,
            "vibe": vibe,
            "color": str(frontmatter.get("color") or "").strip(),
            "emoji": str(frontmatter.get("emoji") or "").strip(),
            "identity_memory": mapped_sections.get("identity_memory", pick_section(sections, "identity")),
            "core_mission": mapped_sections.get("core_mission", pick_section(sections, "mission")),
            "critical_rules": mapped_sections.get("critical_rules", pick_section(sections, "critical")),
            "workflow_process": mapped_sections.get("workflow_process", pick_section(sections, "workflow")),
            "communication_style": mapped_sections.get("communication_style", pick_section(sections, "communication")),
            "success_metrics": mapped_sections.get("success_metrics", pick_section(sections, "success")),
            "advanced_capabilities": mapped_sections.get("advanced_capabilities", pick_section(sections, "advanced")),
            "technical_deliverables": mapped_sections.get("technical_deliverables", pick_section(sections, "technical")),
        },
    }


def build_curated_seed(skills: list[dict[str, Any]]) -> list[str]:
    preferred_ids = [
        "agency-embedded-firmware-engineer",
        "agency-frontend-developer",
        "agency-ui-designer",
        "agency-code-reviewer",
        "agency-api-tester",
        "agency-test-results-analyzer",
        "agency-model-qa",
        "agency-devops-automator",
        "agency-sprint-prioritizer",
        "agency-game-designer",
        "agency-unity-multiplayer-engineer",
        "agency-unity-editor-tool-developer",
    ]
    category_weights = {
        "engineering": 6,
        "testing": 6,
        "design": 5,
        "game-development": 5,
        "project-management": 4,
        "product": 4,
        "specialized": 2,
    }
    keyword_weights = {
        "embedded": 12,
        "firmware": 12,
        "hardware": 10,
        "serial": 10,
        "uart": 10,
        "frontend": 9,
        "ui": 9,
        "ux": 8,
        "game": 8,
        "phaser": 8,
        "godot": 7,
        "unity": 7,
        "unreal": 7,
        "code-review": 9,
        "review": 8,
        "qa": 8,
        "test": 8,
        "testing": 8,
        "automation": 6,
        "devops": 8,
        "backend": 5,
        "product": 6,
        "project": 6,
        "manager": 6,
        "sprint": 6,
        "debug": 7,
    }
    scored: list[tuple[int, str]] = []
    for skill in skills:
        skill_id = str(skill.get("id", ""))
        category = str(skill.get("metadata", {}).get("category", "")).lower()
        tokens = set(str(item).lower() for item in skill.get("recommended_for", []) or [])
        tokens.update(tokenize(skill_id))
        tokens.update(tokenize(str(skill.get("label", ""))))
        score = category_weights.get(category, 0)
        for token in tokens:
            score += keyword_weights.get(token, 0)
        if score <= 0:
            continue
        scored.append((score, skill_id))
    scored.sort(key=lambda item: (-item[0], item[1]))
    ranked_ids = [skill_id for _score, skill_id in scored]
    available = {str(skill.get("id", "")) for skill in skills}
    curated = [skill_id for skill_id in preferred_ids if skill_id in available]
    for skill_id in ranked_ids:
        if skill_id not in curated:
            curated.append(skill_id)
        if len(curated) >= 16:
            break
    return curated[:16]


def main() -> int:
    args = parse_args()
    source_root = Path(args.source_dir).resolve()
    if not source_root.exists():
        raise SystemExit(f"Source repo not found: {source_root}")

    stamp = utc_stamp()
    output_path = Path(args.output).resolve() if args.output else Path("D:/ai合作产品/artifacts") / f"agency-agents-skill-pack-preview-{stamp}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    markdown_files = sorted(
        path
        for path in source_root.rglob("*.md")
        if ".github/" not in path.as_posix() and path.name.lower() != "readme.md"
    )
    if args.limit > 0:
        markdown_files = markdown_files[: args.limit]

    skills = [skill for path in markdown_files if (skill := convert_markdown_file(path, source_root)) is not None]
    category_counts = Counter(str(skill["metadata"]["category"]) for skill in skills)
    pack = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_repo": REPO_URL,
        "source_dir": str(source_root),
        "skill_count": len(skills),
        "categories": dict(sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))),
        "curated_seed_skill_ids": build_curated_seed(skills),
        "skill_library": skills,
    }
    output_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(output_path),
                "skill_count": len(skills),
                "categories": pack["categories"],
                "curated_seed_skill_ids": pack["curated_seed_skill_ids"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
