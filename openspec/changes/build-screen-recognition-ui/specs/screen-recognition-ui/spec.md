## Purpose

Provides a desktop application interface for starting live screen-based recognition, keeping the desktop usable, and displaying visual annotations through a transparent click-through overlay while the professional recognition algorithm is still replaceable.

The current YOLO backend is for debugging the capture-inference-overlay pipeline. The system is intended to host a future specialized recognition backend through the same recognition result contract.

## ADDED Requirements

### Requirement: Main control interface
The system SHALL provide a desktop main window with a clear set of primary function controls, including start recognition and additional placeholder actions for future workflow functions.

#### Scenario: Main window opens with primary controls
- **WHEN** the user launches the application
- **THEN** the system displays a main window with five to six visible function buttons
- **AND** one button is clearly dedicated to starting recognition

#### Scenario: Placeholder functions are visible but non-destructive
- **WHEN** the user selects a placeholder function button
- **THEN** the system provides a visible placeholder response without starting recognition or modifying project data

### Requirement: Start recognition opens a transparent overlay
The system SHALL hide the main control interface and show a transparent click-through overlay when the user starts recognition.

#### Scenario: User starts recognition
- **WHEN** the user activates the start recognition control
- **THEN** the system minimizes or hides the main control interface
- **AND** the system displays a transparent overlay above the desktop without drawing an opaque background

#### Scenario: Transparent overlay preserves desktop interaction
- **WHEN** the system is showing the capture overlay
- **THEN** the user can continue interacting with desktop content underneath the overlay

### Requirement: Live monitor captures screen frames
The system SHALL repeatedly capture screen imagery from the entire current display context during recognition mode and pass captured frames to the recognition module boundary.

#### Scenario: Recognition mode captures a frame
- **WHEN** recognition mode is active
- **THEN** the system obtains screen image frames covering the full desktop for recognition processing

#### Scenario: Captured frame reaches recognition boundary
- **WHEN** a screen image frame is captured
- **THEN** the system passes the frame to the recognition module using a defined input-output contract

#### Scenario: Latest frame supersedes stale frames
- **WHEN** new screen frames are captured faster than recognition can process them
- **THEN** the system keeps the newest available frame for recognition
- **AND** stale unprocessed frames are discarded instead of queued for later annotation

### Requirement: Recognition module uses a replaceable backend
The system SHALL define a recognition module boundary that runs a debug YOLO backend by default and can later be replaced with a project-specific professional recognition backend.

#### Scenario: YOLO recognizer processes a frame
- **WHEN** the YOLO recognition module receives a captured frame
- **THEN** it returns a valid recognition result structure
- **AND** any model detections are converted into overlay detection marks

#### Scenario: Professional backend replaces YOLO
- **WHEN** a future professional recognition backend is configured
- **THEN** the UI uses the same recognition input-output contract
- **AND** overlay rendering does not require YOLO-specific behavior

#### Scenario: UI handles empty results
- **WHEN** the recognition module returns no detections
- **THEN** the overlay remains stable and shows no error state caused by empty results

### Requirement: Recognition pipeline remains responsive
The system SHALL keep UI drawing, screen capture, and recognition work separated so recognition does not block desktop interaction.

#### Scenario: Recognition takes longer than a UI refresh
- **WHEN** the active recognition backend is still processing a frame
- **THEN** the overlay and floating controls remain responsive
- **AND** the UI continues to display the most recent completed detection result

#### Scenario: Recognition publishes a new result
- **WHEN** the recognition backend finishes processing the newest available frame
- **THEN** the system updates the latest recognition result
- **AND** the overlay refresh displays the new detection marks on its next draw cycle

### Requirement: Recognition overlay displays annotations
The system SHALL display only visual annotations in the transparent overlay based on recognition results.

#### Scenario: Recognition result contains detection marks
- **WHEN** the recognition module returns one or more detection marks
- **THEN** the system displays corresponding on-screen annotations at the reported positions across the overlay

#### Scenario: Recognition result contains no detection marks
- **WHEN** the recognition module returns an empty detection list
- **THEN** the system displays the overlay without detection annotations

### Requirement: Recognition can be controlled safely
The system SHALL provide a small floating control panel for manual recognition, automatic recognition, pause, and exit without blocking the desktop.

#### Scenario: User stops recognition
- **WHEN** the user activates the exit control during recognition mode
- **THEN** the system closes the overlay and control panel
- **AND** returns to the main control interface

#### Scenario: User runs manual recognition
- **WHEN** the user activates the manual recognition control
- **THEN** the system runs the recognition module against the latest captured frame
- **AND** displays returned detection marks on the overlay

#### Scenario: User enables automatic recognition
- **WHEN** the user enables automatic recognition
- **THEN** the system repeatedly updates recognition marks using newly captured frames

#### Scenario: User enables demo marks
- **WHEN** the user enables demo marks
- **THEN** the recognizer returns simulated detection marks for UI testing instead of YOLO marks

#### Scenario: Stop is requested during frame processing
- **WHEN** the user requests stop while a frame is being processed
- **THEN** the system finishes or cancels the current cycle safely
- **AND** no further recognition cycles are started
