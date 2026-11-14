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


def test_embed_profiles_resolve_dirs(tmp_path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        yaml.safe_dump(
            {
                "artifacts_dir": "artifacts",
                "embed": {
                    "default": "clip",
                    "profiles": [
                        {
                            "name": "clip",
                            "model": "clip-model",
                            "dim": 512,
                            "dir": "embed",
                            "encoder": "sentence_transformers",
                        },
                        {
                            "name": "siglip2",
                            "model": "siglip-model",
                            "dim": 768,
                            "dir": "embed_siglip2",
                            "encoder": "open_clip",
                        },
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(config_file)

    assert list(cfg.embed_profiles()) == ["clip", "siglip2"]
    assert cfg.embed_profile().name == "clip"
    assert cfg.embed_profile("siglip2").encoder == "open_clip"
    assert cfg.embeddings_dir_for("clip") == cfg.state_root / "embed"
    assert cfg.embeddings_dir_for("siglip2") == cfg.state_root / "embed_siglip2"
    assert cfg.shards_dir_for("siglip2") == cfg.state_root / "embed_siglip2" / "shards"


def test_legacy_embed_config_creates_default_profile(tmp_path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        yaml.safe_dump(
            {
                "artifacts_dir": "artifacts",
                "embed": {"model": "legacy-model", "dim": 4},
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(config_file)

    profile = cfg.embed_profile()
    assert profile.name == "clip"
    assert profile.model == "legacy-model"
    assert profile.dim == 4
    assert cfg.embeddings_dir_for() == cfg.state_root / "embed"


def test_relative_paths_resolve_against_config_file(tmp_path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        yaml.safe_dump({"corpus_dir": "videos", "artifacts_dir": "out"}),
        encoding="utf-8",
    )

    cfg = load_config(config_file)

    assert cfg.corpus_dir == tmp_path / "videos"
    assert cfg.artifacts_dir == tmp_path / "out"
