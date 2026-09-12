"""Verify material deletion removes content access while preserving provenance metadata."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="lucid-t19-delete-") as data_dir:
        os.environ["LUCID_DATA_DIR"] = data_dir
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
        from fastapi.testclient import TestClient

        from app import store
        from app.main import app

        with TestClient(app) as client:
            project_response = client.post("/api/projects", json={"title": "material deletion proof"})
            assert project_response.status_code == 200, project_response.text
            project = project_response.json()
            imported_response = client.post(
                f"/api/projects/{project['id']}/materials/text",
                json={"text": "A source statement that must remain traceable.", "label": "policy.txt"},
            )
            assert imported_response.status_code == 200, imported_response.text
            imported = imported_response.json()
            material_id = imported["material"]["id"]
            stored_path = Path(data_dir) / imported["material"]["metadata"]["stored_path"]
            assert stored_path.exists(), stored_path
            deleted_response = client.delete(f"/api/projects/{project['id']}/materials/{material_id}")
            assert deleted_response.status_code == 200, deleted_response.text
            deleted = deleted_response.json()
            assert deleted["deleted_at"], deleted
            assert not stored_path.exists(), stored_path
            assert store.get_material(project["id"], material_id)["deleted_at"]
        spans = [span for span in store.list_source_spans(project["id"]) if span["material_id"] == material_id]
        assert spans and spans[0]["excerpt"], spans
    print("PASS: material deletion blocks content while retaining source provenance metadata")


if __name__ == "__main__":
    main()
