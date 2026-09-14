## Context

See `proposal.md` for motivation. The existing app has a transparent overlay, a latest-frame pipeline, a YOLO debug recognizer, and placeholder main-window buttons for Capture, Save, and Settings. The professional algorithm is still outside scope, so this change must improve configurability without tying the app more tightly to YOLO.

## Goals / Non-Goals

**Goals:**
- Add a persisted configuration object for model/backend selection, recognition thresholds, device choice, capture timing, display options, and history behavior.
- Let the user switch the YOLO debug model path from the UI while preserving the recognizer contract for future professional backends.
- Apply parameter changes to the active pipeline and recognizer safely.
- Save screenshots and detection metadata for recognized frames in timestamped sessions.
- Avoid saving every raw capture frame; history records should correspond to completed recognition results or explicit user saves.

**Non-Goals:**
- Build a full history browser UI in this pass.
- Implement training-data export formats beyond straightforward JSON metadata and PNG screenshots.
- Implement the final professional recognition algorithm.
- Add storage quotas or automatic cleanup beyond conservative default save rules.

## Decisions

### Decision: Use a local app configuration file
Store settings in a small JSON file under the project, such as `screen_recognition_app_config.json`.

Rationale: the app is still a local prototype and does not need a database. JSON is easy to inspect and edit when debugging model paths and thresholds.

Alternative considered: store settings only in memory. That would make testing repetitive because every launch would lose the selected model and parameters.

### Decision: Treat model selection as backend configuration
Represent the selected backend as a configuration value with fields for backend type, model path, confidence, IoU, and device preference. The first implementation can instantiate `YoloRecognizer`, but the config shape should not assume every future backend is YOLO.

Rationale: the product is a shell for a future professional algorithm. Keeping backend identity in configuration prevents the UI from becoming a YOLO-only tool.

Alternative considered: add only a "choose .pt file" button. That is faster but creates UI and state naming that would need to be rewritten later.

### Decision: Rebuild recognizers on model-affecting changes
When model path, backend type, confidence, IoU, or device preference changes, build a new recognizer and swap it into the pipeline during a controlled pause/restart.

Rationale: model objects may hold GPU memory and internal state. Rebuilding is simpler and more reliable than mutating a loaded model in place.

Alternative considered: mutate the existing recognizer directly. That is lower overhead for small settings but risky for failed model reloads and future backend implementations.

### Decision: Save history on completed recognition results
Create a session directory when recognition mode starts and history saving is enabled. Save screenshots and metadata when the recognition worker publishes a result, with default behavior of saving automatic results only when detections are present and manual results regardless of emptiness.

Rationale: this matches the latest-frame pipeline: the meaningful unit is a completed inference result, not every captured frame. It also limits disk growth while preserving the data the user asked to keep.

Alternative considered: save every captured frame. That would be simple in the capture worker but can fill storage rapidly and produces many frames that were never recognized.

### Decision: Store screenshots plus structured JSON
Save screenshots as PNG files and detection metadata as JSON/JSONL records linked by frame id or filename. Include a metadata file for session-level model and parameter snapshots.

Rationale: PNG screenshots are easy to inspect manually, while JSON detection metadata stays usable for later debugging, replay, or conversion to training formats.

Alternative considered: write a single custom binary session file. That is compact but makes manual inspection and incremental debugging harder.

## Risks / Trade-offs

- Screenshot history can expose sensitive desktop content -> Keep saving controlled by an explicit setting and make the history directory visible in the UI/status.
- Automatic recognition can produce many screenshots -> Default to saving only automatic results with detections, while manual saves always preserve the requested frame.
- Model switching can fail or temporarily stall inference -> Keep the previous working recognizer until the new one loads successfully.
- Writing PNG files from the recognition path can add latency -> Use a small history writer boundary so saving can be moved to a background writer if needed.

## Migration Plan

1. Add default configuration loading with safe fallback values.
2. Add settings/model UI that reads and writes configuration.
3. Make recognizer construction derive from configuration.
4. Add history session creation and record writing.
5. Wire manual recognition and save capture actions to history behavior.
6. Verify existing start recognition behavior still works with history disabled and enabled.

Rollback: disable or remove the configuration and history modules, then fall back to the current hard-coded YOLO recognizer and no persisted history.

## Open Questions

- A full history viewer is deferred; this change only needs saved files that can be inspected from the filesystem.
- Long-term storage cleanup policy is deferred until real usage shows expected screenshot volume.
