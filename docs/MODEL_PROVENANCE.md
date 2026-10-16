# Model Provenance & Evaluation

Both models are bundled inside the Flutter app (`app/assets/models/`). No runtime
downloads. Neither is executed on the server (4 GB RAM, no GPU).

## 1. Face embedding — MobileFaceNet (TFLite)

| | |
|---|---|
| File | `mobilefacenet.tflite` (5.1 MB) |
| Upstream | `andrewpks/convert-tensorflow-mobilefacenet-model-to-tflite` (Apache-2.0), converted from `sirius-ai/MobileFaceNet_TF` (Apache-2.0), checkpoint `MobileFaceNet_iter_14000` |
| Input | `[1,112,112,3]` float32 RGB, `(x − 127.5) / 128.0` |
| Output | `[1,128]` float32 → L2-normalize → cosine similarity |
| Run on | Device (tflite_flutter, CPU, XNNPACK) |

**Local verification (this repo, Python LiteRT smoke test on design assets):**
- embedding dim 128, unit norm ✔
- same person (flipped + brightness-perturbed crop): cosine **0.992**
- different person (stock photo, similar demographics, naive crop): cosine **0.651**

**Threshold:** server-side `face_match_threshold`, default **0.75**.
⚠️ This default is a conservative starting point, *not* a calibrated value.
It MUST be calibrated with real genuine/impostor enrollment crops before
deployment (the 0.65 impostor score on naive crops shows crop alignment matters;
the app performs a 5-point-ish affine alignment from ML Kit landmarks before
inference to widen the margin).

## 2. Passive anti-spoofing — FaceAntiSpoofing (TFLite)

| | |
|---|---|
| File | `FaceAntiSpoofing.tflite` (4.1 MB) |
| Upstream | `syaringan357/Android-MobileFaceNet-MTCNN-FaceAntiSpoofing` (MIT), “Deep-Tree” anti-spoof model |
| Input | `[1,256,256,3]` float32 RGB in `[0,1]`, **tight face crop required** |
| Outputs | two `[1,8]` heads: `Identity` = class predictions, `Identity_1` = one-hot leaf mask |
| Decision rule | `spoof_score = Σ |predᵢ|·maskᵢ`; `≤ 0.2 ⇒ live`, `> 0.2 ⇒ attack` (published rule from upstream reference implementation) |

**Local verification:** tight face crops of a real photo → spoof score
0.0038–0.0066 (LIVE). Out-of-distribution full portrait with background → 0.99 (SPOOF).
The model is sensitive to crop tightness, so the app only scores ML Kit
bounding-box crops with margin, and rejects capture when detection is poor.

**Honest limitation:** no real presentation-attack dataset (printed photos,
screen replays, masks) was evaluated in this repository, so the true detection
error rates are unknown. The model is real and the rule is published, but until a
calibration report exists the hostel policy may set `require_liveness=false`,
in which case attendance lands as `pending_review` for warden confirmation —
never auto-verified. The app does not claim spoofing is impossible.

## Liveness architecture

`LivenessVerifier` is an abstraction in the app (`app/lib/features/attendance/liveness/`):
- v1: passive texture PAD via the model above, per-capture score.
- Extension point: active challenge-response (blink / head-turn driven by ML Kit
  eye-openness and head-pose signals) can be added behind the same interface once
  it is validated; it is deliberately **not** shipped as an unvalidated heuristic.

## Data handling

- Raw camera frames are never uploaded or stored.
- Embeddings (0.5 KB) are the only biometric artifact that leaves the device;
  the server stores them AES-GCM encrypted, access-controlled, deletable by the
  student (`DELETE /face-enrollment`) or by an admin (audited).
- Embeddings and raw attempt coordinates are excluded from logs.
