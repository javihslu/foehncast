"""Build the repo-managed DAG and source bundle for Cloud Composer."""

from __future__ import annotations

from collections.abc import Sequence
import argparse
import json
from pathlib import Path
import shutil
from typing import Any


def _resolved_project_root(project_root: str | Path | None = None) -> Path:
    if project_root is None:
        return Path(__file__).resolve().parents[2]
    return Path(project_root).expanduser().resolve()


def composer_bundle_mappings(
    project_root: str | Path | None = None,
) -> list[dict[str, str]]:
    """Return the reviewed source-to-target mappings for the Composer bundle."""
    root = _resolved_project_root(project_root)
    dag_dir = root / "dags"
    dag_paths = sorted(path for path in dag_dir.glob("*.py") if path.is_file())
    if not dag_paths:
        raise FileNotFoundError(f"No DAG entrypoints found under {dag_dir}.")

    mappings = [
        {
            "source": str(path.relative_to(root)),
            "target": path.name,
            "type": "file",
        }
        for path in dag_paths
    ]
    mappings.extend(
        [
            {
                "source": "src/foehncast",
                "target": "foehncast",
                "type": "directory",
            },
            {"source": "config.yaml", "target": "config.yaml", "type": "file"},
            {
                "source": "pyproject.toml",
                "target": "pyproject.toml",
                "type": "file",
            },
            {
                "source": "feature_repo",
                "target": "feature_repo",
                "type": "directory",
            },
        ]
    )

    for mapping in mappings:
        source_path = root / mapping["source"]
        if not source_path.exists():
            raise FileNotFoundError(
                f"Required Composer bundle path not found: {source_path}"
            )

    return mappings


def build_composer_bundle(
    output_dir: str | Path,
    *,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Copy the reviewed DAG bundle into the requested output directory."""
    root = _resolved_project_root(project_root)
    output_path = Path(output_dir).expanduser().resolve()

    if output_path.exists():
        if output_path.is_dir():
            shutil.rmtree(output_path)
        else:
            output_path.unlink()
    output_path.mkdir(parents=True, exist_ok=True)

    ignore_patterns = shutil.ignore_patterns("__pycache__", "*.pyc")
    mappings = composer_bundle_mappings(root)
    for mapping in mappings:
        source_path = root / mapping["source"]
        target_path = output_path / mapping["target"]
        if mapping["type"] == "directory":
            shutil.copytree(
                source_path,
                target_path,
                dirs_exist_ok=True,
                ignore=ignore_patterns,
            )
            continue

        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)

    return {
        "project_root": str(root),
        "output_dir": str(output_path),
        "entries": mappings,
    }


def write_composer_bundle_manifest(
    manifest: dict[str, Any],
    manifest_path: str | Path,
) -> Path:
    """Persist a stable JSON manifest for the Composer DAG bundle."""
    path = Path(manifest_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m foehncast.composer_bundle")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--project-root", default="")
    build_parser.add_argument("--output-dir", required=True)
    build_parser.add_argument("--manifest-path", default="")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "build":
        manifest = build_composer_bundle(
            args.output_dir,
            project_root=args.project_root or None,
        )
        if args.manifest_path:
            write_composer_bundle_manifest(manifest, args.manifest_path)
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())


__all__ = [
    "build_composer_bundle",
    "composer_bundle_mappings",
    "write_composer_bundle_manifest",
]
