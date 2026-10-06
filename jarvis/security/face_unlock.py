"""Optional optical face unlock for the desktop app.

The legacy ``jarvis.py`` crashed on start when the trained model, the Haar
cascade or the webcam were missing. This version reports a *result* instead, so
the assistant can always fall back to a normal login.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

log = logging.getLogger(__name__)


class UnlockStatus(str, Enum):
    DISABLED = "disabled"
    SUCCESS = "success"
    FAILED = "failed"
    NO_CAMERA = "no_camera"
    MODEL_MISSING = "model_missing"
    DEPENDENCY_MISSING = "dependency_missing"


@dataclass(slots=True)
class UnlockResult:
    status: UnlockStatus
    message: str
    confidence: float | None = None

    @property
    def unlocked(self) -> bool:
        return self.status is UnlockStatus.SUCCESS


class FaceUnlock:
    """Recognise the owner with a Haar cascade + LBPH model."""

    def __init__(
        self,
        *,
        model_path: str | Path,
        cascade_path: str | Path,
        owner: str = "master",
        threshold: float = 100.0,
        attempts: int = 60,
    ) -> None:
        self.model_path = Path(model_path)
        self.cascade_path = Path(cascade_path)
        self.owner = owner
        self.threshold = threshold  # LBPH: lower is a better match
        self.attempts = attempts

    # ------------------------------------------------------------------ checks
    def availability(self) -> UnlockResult | None:
        """Return a failure result when unlocking cannot even be attempted."""
        try:
            import cv2  # noqa: F401
        except Exception as exc:
            return UnlockResult(
                UnlockStatus.DEPENDENCY_MISSING,
                f"Face unlock needs OpenCV (pip install 'jarvis-assistant[vision]'). ({exc})",
            )
        missing = [str(path) for path in (self.model_path, self.cascade_path) if not Path(path).is_file()]
        if missing:
            return UnlockResult(
                UnlockStatus.MODEL_MISSING,
                "Face unlock is not trained yet; missing: "
                + ", ".join(missing)
                + ". Run 'jarvis train-face' first (see docs/FACE_UNLOCK.md).",
            )
        return None

    # ------------------------------------------------------------------- unlock
    def run(self) -> UnlockResult:
        unavailable = self.availability()
        if unavailable is not None:
            log.warning("Face unlock skipped: %s", unavailable.message)
            return unavailable

        import cv2

        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.read(str(self.model_path))
        cascade = cv2.CascadeClassifier(str(self.cascade_path))

        capture = cv2.VideoCapture(0)
        if not capture.isOpened():
            return UnlockResult(
                UnlockStatus.NO_CAMERA, "I could not open the camera; continuing without face unlock."
            )

        try:
            frames = 0
            best: float | None = None
            while frames < self.attempts:
                frames += 1
                ok, frame = capture.read()
                if not ok:
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(90, 90))
                for x, y, w, h in faces:
                    _, confidence = recognizer.predict(gray[y : y + h, x : x + w])
                    best = confidence if best is None else min(best, confidence)
                    if confidence < self.threshold:
                        return UnlockResult(
                            UnlockStatus.SUCCESS,
                            f"Optical face recognition complete. Welcome back, {self.owner}.",
                            confidence=float(confidence),
                        )
            detail = f"best confidence {best:.1f}" if best is not None else "no face detected"
            return UnlockResult(
                UnlockStatus.FAILED,
                f"Face recognition failed ({detail}). Falling back to standard access.",
                confidence=best,
            )
        finally:
            capture.release()
            cv2.destroyAllWindows()


def unlock_if_enabled(config) -> UnlockResult:
    """Run the unlock flow only when it is switched on in the configuration."""
    if not config.require_face_unlock:
        return UnlockResult(UnlockStatus.DISABLED, "Face unlock is disabled.")
    unlocker = FaceUnlock(
        model_path=config.face_model_path,
        cascade_path=config.face_cascade_path,
        owner=config.face_owner_name or config.display_name(),
    )
    return unlocker.run()


def train_faces(
    *,
    dataset_dir: str | Path,
    model_path: str | Path,
    cascade_path: str | Path,
    owner_id: int = 1,
) -> tuple[int, str]:
    """Train an LBPH model from a folder of ``<id>.<n>.jpg`` face images.

    Returns ``(image_count, message)``. Kept tiny on purpose: the desktop app
    only needs enough data to recognise its owner.
    """
    dataset = Path(dataset_dir)
    images = sorted(p for p in dataset.glob("*.jpg"))
    if not images:
        return 0, f"No training images found in {dataset}."

    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        return 0, (f"Face training needs OpenCV and numpy: pip install 'jarvis-assistant[vision]'. ({exc})")

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    faces: list[object] = []
    labels: list[int] = []
    for image_path in images:
        gray = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            continue
        faces.append(gray)
        labels.append(owner_id)

    if not faces:
        return 0, "None of the images could be read."

    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    recognizer.train(faces, np.array(labels))
    recognizer.write(str(model_path))
    if not Path(cascade_path).is_file():
        return len(faces), (
            f"Trained on {len(faces)} images and wrote {model_path}. Warning: the Haar cascade "
            f"at {cascade_path} is missing - download haarcascade_frontalface_default.xml."
        )
    return len(faces), f"Trained on {len(faces)} images and wrote {model_path}."
