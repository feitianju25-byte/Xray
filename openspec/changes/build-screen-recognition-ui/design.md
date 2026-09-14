## Context

See `proposal.md` for motivation. The current project is a local X-ray/image-analysis workspace with Python scripts and no established OpenSpec specs. This change should create a usable desktop interface and a live transparent overlay workflow while keeping the actual professional recognition algorithm outside the scope.

YOLO is currently used only as a debug backend. The durable product goal is a desktop shell that can host a future specialized recognition algorithm without rewriting the UI, capture, or overlay layers.

## Goals / Non-Goals

**Goals:**
- Create a desktop UI structure that can launch from the project and expose five to six primary actions.
- Make "start recognition" the central workflow and transition into a transparent click-through overlay.
- Capture screen frames continuously during recognition and send them through a stable recognition-module boundary.
- Render only annotation marks across the overlay using a YOLO recognizer, while retaining simulated marks for UI testing.
- Keep the UI and recognition algorithm decoupled so the algorithm can be added later without reworking the interface.
- Process the newest available screen frame and drop stale frames instead of building an inference backlog.
- Keep capture and recognition work off the UI thread so the overlay and controls remain responsive.

**Non-Goals:**
- Implement real X-ray defect recognition or train project-specific models.
- Persist recognition sessions, export reports, or manage training data.
- Build a web service or multi-user system.
- Support advanced multi-monitor behavior beyond a reasonable first-display/default-screen implementation.

## Decisions

### Decision: Build a desktop-first interface
Use a desktop GUI entry point rather than a web app for the first implementation.

Rationale: the key workflow is screen capture plus annotation display, which is more direct in a local desktop application. The existing workspace is also Python-oriented, making a Python GUI the lowest-friction first path.

Alternative considered: a browser-based frontend. This would make layout iteration easy, but screen capture and annotation behavior would depend on browser permissions and would not naturally mirror the desktop screen.

### Decision: Hide the launcher and show a transparent click-through overlay
Model the application as a launcher window that hides, followed by a transparent overlay that only draws annotations.

Rationale: this keeps the launcher out of the way while the user can continue operating the desktop. It matches the requested YOLO-style overlay behavior better than rendering a screenshot background.

Alternative considered: a screenshot-backed full-screen preview. That can show the desktop image, but it blocks normal interaction and can turn black when capture fails.

### Decision: Use YOLO behind the recognition result contract
Define recognition output as a list of detection marks with fields such as bounding box coordinates, label, confidence, and display color. The current implementation loads `yolo11n.pt` through Ultralytics using the existing conda `torch` environment and converts YOLO boxes into this contract.

Rationale: the UI can now run a real model without binding the overlay to a specific X-ray defect detector. Later project-trained weights, a Python algorithm module, a native library wrapper, or a service client only need to conform to the same contract.

Alternative considered: leave recognition calls as demo-only. That helped build the UI, but it no longer proves the model integration path.

### Decision: Treat YOLO as a debug backend
Do not make YOLO the center of the architecture. Keep it as the current default backend for testing whether capture, inference, result conversion, and transparent overlay drawing work end to end.

Rationale: the final software is intended as a shell for a professional recognition algorithm. Hard-coding UI behavior to YOLO concepts would create avoidable rework when the specialized detector replaces the debug model.

Alternative considered: build a YOLO-focused desktop annotation tool. That would make sense for general object detection, but it does not match the intended final product.

### Decision: Keep screen monitoring live and process the newest frame
Capture frames continuously and have recognition process the latest available frame. If recognition is slower than capture, older frames are discarded rather than queued.

Rationale: the requested workflow is to keep watching the screen without interrupting desktop operation. Manual recognition allows the user to decide when to run detection, while automatic recognition supports YOLO-like continuous output later.

Alternative considered: a one-shot capture. That avoids repeated capture work, but it does not meet the live monitoring requirement.

Alternative considered: queue every captured frame. That can preserve chronological completeness, but it is wrong for desktop overlay interaction because stale detections would appear after the screen has already changed.

### Decision: Separate UI, capture, and recognition execution
Use the main UI thread only for Tk windows, overlay drawing, and controls. Use a capture worker to keep the latest full-screen frame fresh. Use a recognition worker to run the active backend on the newest frame and publish the latest detection marks.

Rationale: YOLO or a future professional algorithm can be slow enough to block Tk if run in the main loop. Separating responsibilities keeps the desktop operable, makes exit controls responsive, and creates a cleaner insertion point for future algorithms.

Alternative considered: run capture and inference directly from the overlay refresh callback. That is simpler, but it risks UI freezes and makes future heavier algorithms harder to integrate.

## Risks / Trade-offs

- Transparent click-through overlays can behave differently across Windows display settings -> Start with default display support and keep a separate control panel for exit.
- Screenshot permissions or dependency behavior may vary by environment -> Isolate screen capture behind a small adapter so it can be replaced.
- Generic COCO YOLO may not detect X-ray defects -> Keep the model path replaceable and document that project-specific weights are needed later.
- Capture may fail in restricted sessions -> Fall back to a generated frame and show that state clearly in the control panel.
- Inference can be slower than the capture rate -> Use latest-frame handoff and drop stale frames instead of building a queue.
- Threaded capture and recognition add synchronization complexity -> Keep shared state small: latest frame, latest result, status, and stop flags.

## Migration Plan

1. Add the UI entry point and module structure alongside existing scripts.
2. Add the placeholder recognition module and result data contract.
3. Add the live transparent overlay flow and annotation rendering.
4. Split the live pipeline into UI drawing, capture worker, and recognition worker responsibilities.
5. Verify the application can launch, capture frames, render simulated marks or YOLO marks, allow desktop interaction, and clear the overlay cleanly.

Rollback is straightforward for this first UI change: remove the new UI modules and dependencies if they are not adopted.

## Implementation Map

- `run_app.py`: Starts the desktop application.
- `screen_recognition_app/app.py`: Owns the launcher, transparent click-through overlay, floating controls, overlay drawing, pause, and exit behavior.
- `screen_recognition_app/screen_capture.py`: Captures the current desktop through Windows APIs and returns a fallback frame if capture is unavailable.
- `screen_recognition_app/contract.py`: Defines `FrameImage`, `DetectionMark`, and `RecognitionResult`.
- `screen_recognition_app/recognizer.py`: Provides the recognition backend contract, `YoloRecognizer` backed by `yolo11n.pt`, and `PlaceholderRecognizer` for simulated marks.
- Future pipeline module: coordinates the latest-frame handoff among the capture worker, recognition worker, and overlay refresh loop.

## Runtime Defaults

- Automatic recognition is enabled by default so the overlay starts producing YOLO marks after entering recognition mode.
- Demo marks are available from the control panel for UI testing but are off by default.
- The overlay draws only annotation primitives and uses a transparent color key; it does not draw a screenshot background.
- A small floating control window remains visible because a fully click-through overlay cannot reliably host clickable controls.
- Recognition uses the newest available frame. Stale frames are disposable because the overlay should represent the current desktop, not historical screen states.
- The active backend is YOLO for debugging until a professional recognition backend is available.

## Open Questions

- Exact labels for the five to six function buttons can be adjusted during implementation without changing the core behavior.
- The final professional algorithm integration form is not decided yet: Python module, custom weights, native library, or local service.
- The best long-term screen capture backend remains open; a replaceable adapter should allow moving from the current Windows capture path to `mss`, Windows Graphics Capture, or DXGI Desktop Duplication if needed.
