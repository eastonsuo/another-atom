from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from another_atom.contracts.schemas import ArtifactType
from another_atom.storage.models import Artifact


def save_artifact(
    db: Session, run_id: str, artifact_type: ArtifactType, value: BaseModel
) -> Artifact:
    artifact = db.scalar(
        select(Artifact).where(
            Artifact.run_id == run_id,
            Artifact.artifact_type == artifact_type.value,
        )
    )
    if artifact is None:
        artifact = Artifact(run_id=run_id, artifact_type=artifact_type.value, payload={})
        db.add(artifact)
    artifact.payload = value.model_dump(mode="json")
    db.flush()
    return artifact


def get_artifact(db: Session, run_id: str, artifact_type: ArtifactType) -> Artifact | None:
    return db.scalar(
        select(Artifact).where(
            Artifact.run_id == run_id,
            Artifact.artifact_type == artifact_type.value,
        )
    )
