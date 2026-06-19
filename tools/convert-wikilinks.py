#!/usr/bin/env python3
"""
Convert Obsidian [[wiki-links]] to standard markdown links with relative paths.

One-shot tool used during the initial Friday Labs OS repo setup. Run once
after moving docs into subdirectories under docs/.

After conversion the dossier renders correctly on GitHub AND in Obsidian.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_ROOT = REPO_ROOT / "docs"

# Filename (without .md) -> subdir under docs/
FILE_MAP = {
    "Mark 1 Index": "",
    "Mark 1 Compute Architecture": "architecture",
    "Friday Labs OS Architecture": "architecture",
    "Telemetry Command Node": "architecture",
    "ROS 2 Interface and Message Contract": "architecture",
    "Mark 1 Simulation and Dev Environment": "architecture",
    "Authority Lease Protocol": "addendums",
    "Safe-Stop Latency Budget": "addendums",
    "Sensor Ownership": "addendums",
    "Power Budget": "addendums",
    "AI Inference Location": "addendums",
    "friday_msgs Schema Conventions": "addendums",
    "Command Center Protocol Security": "addendums",
    "OTA Update Strategy": "addendums",
    "Mission Logging and Replay": "addendums",
    "Stage 5 Acceptance Criteria": "addendums",
    "Spark Authority and friday-core-os Definition": "addendums",
    "Mechanical Design Reference": "addendums",
    "mmWave Human Detection": "addendums",
    "Locomotion Control Unit": "modules",
    "Adaptive Research Module": "modules",
    "Aerial Companion Bay": "modules",
    "Phase 1 Implementation Kickoff": "onboarding",
}

# Aliases that resolve to another file in FILE_MAP
ALIASES = {
    "Friday Labs OS": "Friday Labs OS Architecture",
}

# Skill names — resolve to .claude/skills/<name>/SKILL.md at repo root
SKILLS = {
    "friday-msgs-author",
    "lifecycle-node-scaffold",
    "sim-bringup",
    "fault-injection",
    "safe-stop-audit",
    "module-spec",
    "qos-audit",
    "command-center-protocol",
}

# Out-of-scope / unwritten references — bolded since they have no target
EXTERNAL = {
    "Friday Labs",
    "Spark",
    "Command Center Protocol Mapping",
}

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

stats = {
    "internal": 0,
    "skill": 0,
    "external": 0,
    "unknown": 0,
}


def github_anchor(section: str) -> str:
    """Approximate GitHub's anchor slug generation."""
    s = section.strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s.lower()


def compute_relative_path(source_subdir: str, target_subdir: str, target_filename: str) -> str:
    if source_subdir == target_subdir:
        return f"{target_filename}.md"
    if source_subdir == "":
        return f"{target_subdir}/{target_filename}.md" if target_subdir else f"{target_filename}.md"
    if target_subdir == "":
        return f"../{target_filename}.md"
    return f"../{target_subdir}/{target_filename}.md"


def compute_skill_path(source_subdir: str, skill_name: str) -> str:
    if source_subdir == "":
        return f"../.claude/skills/{skill_name}/SKILL.md"
    return f"../../.claude/skills/{skill_name}/SKILL.md"


def convert_link(match: re.Match, source_subdir: str) -> str:
    full = match.group(1)

    if "|" in full:
        link_part, display = full.split("|", 1)
        display = display.strip()
    else:
        link_part = full
        display = None

    if "#" in link_part:
        name, section = link_part.split("#", 1)
        anchor = "#" + github_anchor(section)
    else:
        name = link_part
        anchor = ""

    name = name.strip()

    # Same-page anchor link: [[#Section]] or [[#Section|Display]]
    if name == "":
        if display is None:
            display = link_part.lstrip("#").strip()
        stats["internal"] += 1
        return f"[{display}]({anchor})"

    if display is None:
        display = name

    if name in ALIASES:
        name = ALIASES[name]

    if name in SKILLS:
        path = compute_skill_path(source_subdir, name)
        stats["skill"] += 1
        return f"[{display}]({path}{anchor})"

    if name in EXTERNAL:
        stats["external"] += 1
        return f"**{display}**"

    if name not in FILE_MAP:
        print(f"  WARNING: Unknown reference: {name}", file=sys.stderr)
        stats["unknown"] += 1
        return match.group(0)

    target_subdir = FILE_MAP[name]
    path = compute_relative_path(source_subdir, target_subdir, name)
    stats["internal"] += 1
    return f"[{display}]({path}{anchor})"


def process_file(path: Path, source_subdir: str):
    content = path.read_text(encoding="utf-8")
    new_content = WIKILINK_RE.sub(lambda m: convert_link(m, source_subdir), content)
    if new_content != content:
        path.write_text(new_content, encoding="utf-8")


def main():
    files = sorted(DOCS_ROOT.rglob("*.md"))
    for md_file in files:
        rel = md_file.relative_to(DOCS_ROOT)
        parts = rel.parts
        source_subdir = "" if len(parts) == 1 else parts[0]
        process_file(md_file, source_subdir)

    print(f"Processed {len(files)} files.")
    print(f"  Internal links converted:  {stats['internal']}")
    print(f"  Skill links converted:     {stats['skill']}")
    print(f"  External refs bolded:      {stats['external']}")
    print(f"  Unknown refs left as-is:   {stats['unknown']}")
    if stats["unknown"] > 0:
        print(f"\n  NOTE: {stats['unknown']} unknown references retained as [[wiki-link]] format.")
        print(f"  Review warnings above and either add to FILE_MAP/EXTERNAL or remove from source.")


if __name__ == "__main__":
    main()
