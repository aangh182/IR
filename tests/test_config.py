from __future__ import annotations

import yaml

from ir.config import REPO_ROOT, load_config


def test_default_config_loads() -> None:
    cfg = load_config(REPO_ROOT / "config.yaml")

    assert cfg.embed.model == "sentence-transformers/clip-ViT-B-16"
    assert cfg.embed.dim == 512
    assert cfg.artifacts_dir == REPO_ROOT / "artifacts"
    assert cfg.db_path.name == "metadata.sqlite"
    assert cfg.search.weights.dense == 1.0


def test_relative_paths_resolve_against_config_file(tmp_path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        yaml.safe_dump({"corpus_dir": "videos", "artifacts_dir": "out"}),
        encoding="utf-8",
    )

    cfg = load_config(config_file)

    assert cfg.corpus_dir == tmp_path / "videos"
    assert cfg.artifacts_dir == tmp_path / "out"
