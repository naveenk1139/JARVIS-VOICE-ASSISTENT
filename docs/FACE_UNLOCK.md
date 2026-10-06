# Optional face unlock (desktop)

The original `jarvis.py` started with a webcam loop and crashed when the trained model, the
Haar cascade or the camera was missing. Face unlock is now an **opt-in extra** that reports its
status and lets the assistant start anyway.

> The browser UI deliberately has **no** face unlock: webcams are not available to a server-side
> process, and asking for camera permission adds no real security for a local assistant.

## 1. Install the vision extra

```bash
pip install -e ".[vision]"     # opencv-python, numpy
```

## 2. Provide the cascade

Download the standard frontal-face cascade and place it in `Face-Recognition/`:

```bash
mkdir -p Face-Recognition
curl -L -o Face-Recognition/haarcascade_frontalface_default.xml \
  https://raw.githubusercontent.com/opencv/opencv/4.x/data/haarcascades/haarcascade_frontalface_default.xml
```

## 3. Capture a small dataset

Record ~30–50 greyscale crops of your face, named `<id>.<n>.jpg`, for example:

```bash
mkdir -p Face-Recognition/dataset
# Use your webcam tool of choice; a simple OpenCV capture loop is enough:
python - <<'PY'
import cv2, os
cascade = cv2.CascadeClassifier("Face-Recognition/haarcascade_frontalface_default.xml")
cam = cv2.VideoCapture(0)
os.makedirs("Face-Recognition/dataset", exist_ok=True)
count = 0
while count < 40:
    ok, frame = cam.read()
    if not ok:
        break
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    for (x, y, w, h) in cascade.detectMultiScale(gray, 1.2, 5, minSize=(90, 90)):
        count += 1
        cv2.imwrite(f"Face-Recognition/dataset/1.{count}.jpg", gray[y:y+h, x:x+w])
        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
    cv2.imshow("capture", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break
cam.release()
cv2.destroyAllWindows()
print("captured", count, "images")
PY
```

## 4. Train and test

```bash
jarvis train-face Face-Recognition/dataset     # writes Face-Recognition/trainer/trainer.yml
jarvis unlock                                  # one-shot recognition test
```

`train-face` accepts `--model` and `--cascade` to override the default paths.

## 5. Enable it at startup

```bash
JARVIS_REQUIRE_FACE_UNLOCK=true
JARVIS_FACE_OWNER_NAME=Aarav
jarvis desktop
```

## Statuses you may see

| Status | Meaning | What to do |
| --- | --- | --- |
| `disabled` | `JARVIS_REQUIRE_FACE_UNLOCK` is not set | — |
| `dependency_missing` | OpenCV/numpy is not installed | `pip install -e ".[vision]"` |
| `model_missing` | Trainer or cascade file not found | Run the capture + `train-face` steps |
| `no_camera` | Camera could not be opened | Check permissions; another app may hold the device |
| `failed` | A face was seen but the confidence stayed above the threshold | Re-capture in better light, retrain |
| `success` | Confidence below the threshold (lower is a better match) | Welcome back |

Threshold and attempts live in `jarvis/security/face_unlock.py` (`threshold=100.0`,
`attempts=60`) and are easy to tune.

## Privacy notes

- Everything runs locally; no biometric data leaves your machine.
- Images live in `Face-Recognition/dataset/`, which is git-ignored, as is the trained model.
- LBPH is a *convenience* lock, not a security boundary — it can be fooled by a photograph.
  Treat it as a friendly "hello" rather than authentication, and keep your real OS login enabled.
