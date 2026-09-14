from pathlib import Path


def test_expected_project_structure_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    expected = [
        "README.md",
        "run.py",
        "pyproject.toml",
        "configs/mvp.yaml",
        "src/solder_mvp/inventory.py",
        "src/solder_mvp/sampler.py",
        "src/solder_mvp/contact_sheet.py",
        "src/solder_mvp/candidate_detector.py",
        "src/solder_mvp/grid_fitter.py",
        "src/solder_mvp/roi_exporter.py",
        "src/solder_mvp/evaluator.py",
        "src/solder_mvp/cli.py",
        "manifests/.gitkeep",
        "reviews/.gitkeep",
        "outputs/.gitkeep",
    ]
    assert all((root / relative).exists() for relative in expected)


def test_workspace_contains_no_original_images_or_archives() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = {".jpg", ".jpeg", ".zip"}
    assert not [path for path in root.rglob("*") if path.is_file() and path.suffix.casefold() in forbidden]
