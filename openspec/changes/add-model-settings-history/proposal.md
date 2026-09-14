## Why

The recognition UI now has a working live overlay pipeline, but it still behaves like a fixed debug prototype: the model path, inference parameters, and recognition outputs are not configurable or preserved. The next step is to make the app useful for iterative algorithm testing by allowing model switching, parameter tuning, and session history with screenshots.

## What Changes

- Add model/backend selection so the current YOLO debug model can be switched without changing code.
- Add recognition parameter settings for confidence, IoU, device preference, capture interval, inference behavior, and annotation display options.
- Persist settings across app launches using a local configuration file.
- Add recognition history recording for completed inference results.
- Save screenshots for recognized frames alongside structured detection metadata.
- Add controls for starting/stopping history capture and for saving a manual capture with the current annotations.
- Keep YOLO as a debug backend while preserving the future professional algorithm boundary.

## Capabilities

### New Capabilities
- `recognition-configuration-history`: Model selection, parameter configuration, persistent settings, and screenshot-backed recognition history.

### Modified Capabilities
- None.

## Impact

- Affects the desktop UI, floating controls, recognition pipeline configuration, recognizer construction, and session lifecycle.
- Adds local persisted configuration and local run history directories under the project workspace.
- Introduces screenshot encoding for captured recognition frames.
- Requires careful storage defaults so automatic recognition does not fill disk unexpectedly.
