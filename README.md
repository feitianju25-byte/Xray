# Screen Recognition UI

> 项目完整目录、数据格式和 Git 管理边界见
> [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md)。

This project contains a desktop UI prototype for live screen-based recognition.
The current implementation hides the launcher window, monitors the desktop in real time, and draws recognition marks through a transparent click-through overlay so the user can continue operating the desktop underneath.

## Run

Recommended, using the existing conda environment that already contains PyTorch:

```powershell
.\run_app_torch.bat
```

or:

```powershell
.\run_app_torch.ps1
```

The launcher uses:

```text
D:\Learning\Conda\envs\torch\python.exe
```

This avoids installing a second PyTorch copy.

Generic Python launch still works only if the active Python has the required YOLO dependencies:

```powershell
python run_app.py
```

`run_app.py` now automatically relaunches itself with `D:\Learning\Conda\envs\torch\python.exe` when that environment exists, so accidental launches from another Python should still use the correct YOLO environment.

The UI uses Python's built-in `tkinter` module. Screen capture uses the Windows desktop APIs with a safe fallback frame when capture is unavailable in the current session.

## Current Workflow

1. Launch the app with `python run_app.py`.
2. Click `Start Recognition`.
3. The launcher window hides after a short delay.
4. A transparent, click-through overlay is placed above the desktop.
5. A small `Recognition Controls` window remains visible for control actions.
6. The overlay continuously captures the current screen.
7. YOLO recognition marks are drawn over the desktop without drawing a screenshot background.

## Controls

- `Recognize Now`: run YOLO on the latest captured frame.
- `Auto Detect`: continuously run YOLO on refreshed frames.
- `Demo Marks`: switch to simulated detection boxes for UI testing.
- `Pause`: pause live screen monitoring.
- `Exit`: close the overlay/control window and restore the launcher.

`Auto Detect` is enabled by default. `Demo Marks` is off by default now that YOLO is connected.

## YOLO Model

- Current model: `yolo11n.pt`
- Current dependency environment: `D:\Learning\Conda\envs\torch`
- Current PyTorch: `torch 2.9.1+cu128`
- CUDA status in this environment: available during setup

The bundled model is a generic COCO-pretrained model. It is suitable for proving the live detection pipeline, but it is not an X-ray defect model. Replace `yolo11n.pt` with a project-specific trained model when one is available.

## Code Map

- `run_app.py`: application entry point.
- `screen_recognition_app/app.py`: launcher window, transparent click-through overlay, floating control panel, and runtime workflow.
- `screen_recognition_app/screen_capture.py`: Windows screen capture adapter plus fallback frame generation.
- `screen_recognition_app/contract.py`: frame, detection mark, and recognition result data contracts.
- `screen_recognition_app/recognizer.py`: YOLO recognizer plus optional simulated detection output.

## Known Runtime Notes

- The current recognizer uses generic YOLO weights, not a project-specific X-ray defect model.
- In restricted desktop sessions, screen capture can fall back to a generated frame; the control panel reports `fallback capture` in that case.
- The overlay attempts to use Windows click-through and capture-exclusion APIs. If either API is unavailable, the control panel reports the limitation.
