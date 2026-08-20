"""Generate release notices and copy license texts from the exact build environment."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import re
import shutil
import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


ROOT = Path(__file__).resolve().parents[1]
LICENSE_PREFIXES = ("license", "copying", "notice", "copyright")
MAX_LICENSE_BYTES = 4 * 1024 * 1024


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "package"


def _license_summary(metadata) -> str:
    value = metadata.get("License-Expression") or metadata.get("License") or ""
    lines = [line.strip() for line in str(value).splitlines() if line.strip()]
    if lines and lines[0].lower() not in {"unknown", "none"}:
        return lines[0][:180]
    classifiers = metadata.get_all("Classifier") or []
    license_classifiers = [item.removeprefix("License :: ") for item in classifiers if item.startswith("License :: ")]
    return "; ".join(license_classifiers)[:180]


def _source_url(metadata) -> str:
    for value in metadata.get_all("Project-URL") or []:
        label, separator, url = value.partition(",")
        if separator and label.strip().lower() in {"source", "repository", "homepage", "code"}:
            return url.strip()
    return str(metadata.get("Home-page") or "").strip()


def _direct_dependencies() -> set[str]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    direct = set()
    for raw_requirement in project.get("dependencies", []):
        requirement = Requirement(raw_requirement)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        direct.add(canonicalize_name(requirement.name))
    return direct


def _locked_distributions() -> set[str]:
    """Return the distributions that can actually enter the frozen artifact."""

    lock_path = ROOT / "requirements-lock-py313-win64.txt"
    if not lock_path.is_file():
        raise RuntimeError(f"Dependency lock is missing: {lock_path}")
    names = {
        canonicalize_name(match.group(1))
        for match in re.finditer(
            r"(?m)^([A-Za-z0-9][A-Za-z0-9_.-]*)==[^\s\\]+",
            lock_path.read_text(encoding="utf-8"),
        )
    }
    if not names:
        raise RuntimeError(f"No pinned distributions found in dependency lock: {lock_path}")
    return names


def _copy_distribution_licenses(distribution, destination: Path) -> list[str]:
    copied: list[str] = []
    seen_hashes: set[str] = set()
    for entry in distribution.files or ():
        basename = Path(str(entry)).name.lower()
        if not basename.startswith(LICENSE_PREFIXES):
            continue
        source = Path(distribution.locate_file(entry))
        try:
            size = source.stat().st_size
        except OSError:
            continue
        if not source.is_file() or size <= 0 or size > MAX_LICENSE_BYTES:
            continue
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        target_name = _safe_name(str(entry).replace("\\", "_").replace("/", "_"))
        target = destination / target_name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(target.name)
    return sorted(copied)


def generate(output_directory: Path, *, strict: bool) -> int:
    output = output_directory.resolve()
    build_root = (ROOT / "build").resolve()
    is_unapproved_repo_path = ROOT in output.parents and output != build_root and build_root not in output.parents
    if output == ROOT or is_unapproved_repo_path:
        raise RuntimeError(f"Unsafe compliance output directory: {output}")
    if output.exists():
        shutil.rmtree(output)
    python_licenses = output / "licenses" / "python"
    component_licenses = output / "licenses" / "components"
    python_licenses.mkdir(parents=True)
    component_licenses.mkdir(parents=True)

    direct = _direct_dependencies()
    locked = _locked_distributions()
    rows = []
    unresolved_direct = []
    unresolved_all = []
    seen_distributions: set[tuple[str, str]] = set()
    distributions = sorted(
        importlib.metadata.distributions(),
        key=lambda item: canonicalize_name(item.metadata.get("Name") or ""),
    )
    for distribution in distributions:
        name = str(distribution.metadata.get("Name") or "unknown")
        canonical_name = canonicalize_name(name)
        if canonical_name not in locked and canonical_name != "haizflow":
            continue
        distribution_key = (canonical_name, str(distribution.version))
        # Editable installs can expose both their ``.dist-info`` directory and
        # an additional metadata entry for the same project.  Treat those as
        # one distribution so a second empty entry cannot remove or invalidate
        # license evidence already copied for the first one.
        if distribution_key in seen_distributions:
            continue
        seen_distributions.add(distribution_key)
        license_text = _license_summary(distribution.metadata)
        package_destination = python_licenses / f"{_safe_name(name)}-{_safe_name(distribution.version)}"
        copied = _copy_distribution_licenses(distribution, package_destination)
        if not copied and package_destination.exists():
            package_destination.rmdir()
        if not license_text and not copied:
            unresolved_all.append(f"{name} {distribution.version}")
            if canonical_name in direct:
                unresolved_direct.append(f"{name} {distribution.version}")
        rows.append(
            (
                name,
                distribution.version,
                license_text or "Not declared in wheel metadata",
                _source_url(distribution.metadata),
                ", ".join(copied),
                canonical_name in direct,
            )
        )

    curated_source = ROOT / "licenses"
    if curated_source.is_dir():
        for source in sorted(curated_source.iterdir()):
            if source.is_file():
                shutil.copy2(source, component_licenses / source.name)

    lines = [
        "# Third-Party Notices",
        "",
        "This inventory is generated from the exact Python environment used to build the Windows artifact.",
        "License texts copied from installed wheels are under `licenses/python`; curated non-Python component texts are under `licenses/components`.",
        "",
        "## Non-Python Components",
        "",
        "| Component | Distribution status | License | Source |",
        "| --- | --- | --- | --- |",
        "| FFmpeg 8.1.2 essentials build | Bundled | GPL-3.0-or-later configured build | https://ffmpeg.org/ |",
        "| HY-MT2 1.8B Transformers, revision 9a341cd1b679d3efd23b46e847b01745a71ed792 | First-run downloaded model | Apache-2.0 | https://huggingface.co/tencent/Hy-MT2-1.8B |",
        "| HY-MT2 1.8B GGUF, revision 1cd5208700acedef4ef93019b6cfc148b8522d45 | First-run downloaded model | Apache-2.0 | https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF |",
        "| PP-OCRv5 Mobile ONNX (RapidOCR v3.8.0) | First-run downloaded model | Apache-2.0 | https://github.com/PaddlePaddle/PaddleOCR |",
        "| OmniVoice SDK 0.2.1 | First-run downloaded runtime | Apache-2.0 | https://github.com/k2-fsa/OmniVoice |",
        "| OmniVoice checkpoint, revision c5fdb5ccb189668d56333f77ba2629f4cd7535f4 | First-run downloaded model | CC-BY-NC-4.0 (non-commercial) | https://huggingface.co/k2-fsa/OmniVoice |",
        "| Douyin X-Bogus compatibility helper | Bundled adapted source | Apache-2.0 | https://github.com/jiji262/douyin-downloader |",
        "",
        "The release bundles the signed upstream FFmpeg 8.1.2 source archive under `sources/ffmpeg`. The publisher must also satisfy corresponding-source obligations for covered statically linked libraries.",
        "",
        "## Python Distributions",
        "",
        "| Package | Version | Direct | Declared license | Source | Copied license files |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name, version, license_text, source_url, copied, is_direct in rows:
        values = [name, version, "yes" if is_direct else "no", license_text, source_url, copied]
        escaped = [str(value).replace("|", "\\|").replace("\n", " ") for value in values]
        lines.append("| " + " | ".join(escaped) + " |")

    lines.extend(["", "## Metadata Gaps", ""])
    if unresolved_all:
        lines.extend(f"- {item}" for item in unresolved_all)
    else:
        lines.append("No installed distribution is missing both license metadata and a license file.")
    lines.extend(
        [
            "",
            "This document is an engineering inventory, not legal advice. The complete copied license texts govern their components.",
            "",
        ]
    )
    (output / "THIRD_PARTY_NOTICES.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"Generated notices for {len(rows)} Python distributions at: {output}")
    if unresolved_direct:
        print("Direct dependencies without license evidence: " + ", ".join(unresolved_direct), file=sys.stderr)
        return 1 if strict else 0
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    return generate(args.output, strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
