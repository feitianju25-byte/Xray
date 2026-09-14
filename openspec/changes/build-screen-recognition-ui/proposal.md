## Why

The project needs a usable software interface before the professional recognition algorithm is ready, so the workflow, screen capture behavior, and annotation experience can be designed and tested early. The interaction should hide the launcher window, keep the desktop usable, monitor the screen continuously, and draw only recognition annotations through a transparent click-through overlay.

The current YOLO integration is a debugging backend, not the final product purpose. The product direction is a desktop shell for a future specialized recognition algorithm, with YOLO used only to validate the live capture, inference, and annotation pipeline.

## What Changes

- Add a desktop application interface with five to six primary function buttons, including a prominent start recognition action.
- Add a transparent click-through overlay entered from the start recognition action after the launcher window is hidden.
- Add screen capture orchestration for live monitoring so the app can repeatedly capture the entire screen for recognition.
- Add an annotation overlay that displays image marks without blocking normal desktop interaction.
- Add a YOLO recognition module using the existing conda `torch` environment and a lightweight `yolo11n.pt` model, with simulated demo marks retained for UI testing.
- Treat YOLO as a replaceable debug backend behind a stable recognition contract for future professional algorithms.
- Evolve the live recognition flow toward a latest-frame pipeline: the UI thread draws only, the capture worker continuously refreshes the newest frame, and the recognition worker processes the newest available frame without queueing stale frames.
- Add a small floating control panel for recognizing the current frame, toggling automatic recognition, pausing monitoring, and stopping recognition.

## Capabilities

### New Capabilities
- `screen-recognition-ui`: Desktop UI, live screen monitoring workflow, transparent click-through annotation overlay, screen capture handoff, placeholder recognition module, and visual annotation behavior.

### Modified Capabilities
- None.

## Impact

- Affects the application entry point, UI layer, screen capture integration, and recognition module structure.
- Introduces a future-facing interface between UI code and the recognition algorithm.
- Requires thread-safe handoff between capture, recognition, and overlay rendering so slow inference does not block desktop interaction.
- May add GUI/screenshot dependencies depending on implementation choice.
- Uses a generic COCO-pretrained YOLO model for debugging; project-specific recognition code or weights can replace it later.
