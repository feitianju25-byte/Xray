## 1. Application Structure

- [x] 1.1 Choose the initial desktop GUI framework based on the local Python environment and document the run command.
- [x] 1.2 Create a dedicated UI application entry point without disrupting existing analysis scripts.
- [x] 1.3 Create separate modules for the main window, preview rendering, screen capture adapter, and recognition placeholder.

## 2. Main Interface

- [x] 2.1 Build the main window with five to six primary function buttons.
- [x] 2.2 Make the start recognition button visually prominent and connect it to the preview workflow.
- [x] 2.3 Add safe placeholder behavior for the non-recognition buttons.

## 3. Recognition Module Boundary

- [x] 3.1 Define the recognition input-output contract for captured frames and detection marks.
- [x] 3.2 Install Ultralytics into the existing conda `torch` environment without reinstalling PyTorch.
- [x] 3.3 Download and load `yolo11n.pt` as the default YOLO model.
- [x] 3.4 Convert YOLO detections into overlay detection marks.
- [x] 3.5 Keep simulated detection output available for UI annotation testing.

## 4. Live Overlay Workflow

- [x] 4.1 Implement capture from the main window into a transparent click-through overlay instead of an opaque preview.
- [x] 4.2 Add a screen capture adapter that can obtain frames from the current display context.
- [x] 4.3 Implement a live capture flow that refreshes the current frame continuously.
- [x] 4.4 Add manual YOLO recognition, automatic YOLO recognition, demo marks, pause, and exit controls for the overlay workflow.

## 5. Annotation Rendering

- [x] 5.1 Render detection marks over the transparent overlay using the recognition result contract.
- [x] 5.2 Ensure empty recognition results leave the overlay stable and non-blocking.
- [x] 5.3 Verify simulated detections appear at the expected screen positions.

## 6. Verification

- [x] 6.1 Verify the application launches from the documented command.
- [x] 6.2 Verify the main window displays the required function buttons.
- [x] 6.3 Verify start recognition opens a transparent live overlay and exit clears it.
- [x] 6.4 Verify the placeholder recognizer can process captured frames without a real algorithm.
- [x] 6.5 Run `openspec validate build-screen-recognition-ui --strict` and resolve any planning artifact issues.

## 7. Next Architecture Pass

- [x] 7.1 Refactor live recognition so the Tk main thread only manages windows, controls, and overlay drawing.
- [x] 7.2 Add a capture worker that continuously updates the latest full-screen frame.
- [x] 7.3 Add a recognition worker that processes only the newest available frame and drops stale frames.
- [x] 7.4 Keep YOLO as a replaceable debug backend behind the recognition contract.
- [x] 7.5 Add status reporting for capture state, active backend, device, inference FPS, capture FPS, and detection count.
- [x] 7.6 Document the professional algorithm integration point so future backends can replace YOLO without UI changes.
