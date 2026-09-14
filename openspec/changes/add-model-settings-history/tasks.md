## 1. Configuration

- [x] 1.1 Add a typed application settings model with defaults for backend, model path, thresholds, device, timing, annotation display, and history saving.
- [x] 1.2 Add JSON load/save helpers with validation and fallback behavior for missing or invalid settings files.
- [x] 1.3 Make app startup load settings and reflect them in the main UI state.

## 2. Model And Parameter UI

- [x] 2.1 Replace placeholder Settings behavior with a settings dialog for model path, backend type, confidence, IoU, device, capture interval, inference interval, and history options.
- [x] 2.2 Add a model file picker for YOLO `.pt` weights and persist the selected path.
- [x] 2.3 Apply changed settings to the active pipeline and recognizer without requiring a full app restart where practical.
- [x] 2.4 Preserve the previous working recognizer if a newly selected model fails to load.

## 3. Recognizer Configuration

- [x] 3.1 Update `YoloRecognizer` to accept configurable confidence, IoU, device preference, and model path.
- [x] 3.2 Add a recognizer factory that builds the active backend from settings.
- [x] 3.3 Keep the factory extensible for future professional algorithm backends.

## 4. History Persistence

- [x] 4.1 Add a history session writer that creates timestamped session directories under the configured history root.
- [x] 4.2 Save session metadata with model, backend, parameters, device preference, and start time.
- [x] 4.3 Save PNG screenshots for completed recognition results according to history settings.
- [x] 4.4 Save per-frame detection metadata and append a JSONL session index.
- [x] 4.5 Wire manual recognition and save capture actions so requested captures are saved even when no detections are present.

## 5. Pipeline Integration

- [x] 5.1 Extend recognition result publication to include enough context for history saving, including frame, result, reason, and sequence id.
- [x] 5.2 Ensure automatic recognition saves only detection-bearing frames by default.
- [x] 5.3 Ensure history saving does not block overlay drawing or desktop interaction more than necessary.

## 6. Verification

- [x] 6.1 Verify the app still launches and enters recognition mode with default settings.
- [x] 6.2 Verify changing the YOLO model path persists and is used on the next recognition run.
- [x] 6.3 Verify changing confidence or IoU affects recognition behavior and persists across launches.
- [x] 6.4 Verify history sessions contain metadata, screenshots, per-frame JSON, and JSONL index records.
- [x] 6.5 Verify automatic empty results are not saved by default.
- [x] 6.6 Run `openspec validate add-model-settings-history --strict`.
