## Purpose

Adds configurable recognition backends, persistent recognition parameters, and screenshot-backed history so the desktop app can support repeatable algorithm testing beyond the initial live overlay prototype.

## ADDED Requirements

### Requirement: Model selection
The system SHALL allow the user to select the active recognition model or backend configuration used by the live recognition pipeline.

#### Scenario: User selects a model file
- **WHEN** the user chooses a supported model file from the model selection control
- **THEN** the system stores that model selection
- **AND** subsequent recognition uses the selected model after the recognizer is reloaded

#### Scenario: Model loading fails
- **WHEN** the selected model cannot be loaded
- **THEN** the system displays a visible error status
- **AND** the system keeps the previous working recognizer active when one exists

#### Scenario: Future professional backend is configured
- **WHEN** a future professional backend is selected
- **THEN** the system uses the same recognition result contract as the YOLO debug backend
- **AND** overlay rendering behavior remains unchanged

### Requirement: Recognition parameters
The system SHALL expose configurable recognition parameters and persist them between application launches.

#### Scenario: User changes recognition thresholds
- **WHEN** the user changes confidence or IoU threshold settings
- **THEN** the system saves the new values
- **AND** future recognition requests use those values

#### Scenario: User changes runtime behavior
- **WHEN** the user changes capture interval, maximum inference rate, device preference, or annotation display options
- **THEN** the system saves the new values
- **AND** the active recognition pipeline applies the updated settings without requiring a full application restart where practical

#### Scenario: App starts with saved settings
- **WHEN** the user launches the application after changing settings
- **THEN** the system loads the saved configuration
- **AND** the UI reflects the configured model and recognition parameters

### Requirement: Screenshot-backed recognition history
The system SHALL save recognition history records with screenshots for completed recognition results when history capture is enabled.

#### Scenario: Automatic recognition returns detections
- **WHEN** automatic recognition completes and history capture is enabled
- **THEN** the system saves the recognized screen image as a screenshot
- **AND** the system saves structured detection metadata linked to that screenshot

#### Scenario: Automatic recognition returns no detections
- **WHEN** automatic recognition completes with no detections
- **AND** saving empty results is disabled
- **THEN** the system does not save a screenshot for that empty result

#### Scenario: Manual recognition is requested
- **WHEN** the user runs manual recognition while history capture is enabled
- **THEN** the system saves the recognized screen image and structured metadata regardless of whether detections are present

#### Scenario: User saves a capture
- **WHEN** the user activates the save capture action during recognition mode
- **THEN** the system saves the latest available screen image
- **AND** the system saves the latest displayed annotation result linked to that image

### Requirement: History sessions
The system SHALL group saved recognition history into timestamped sessions with metadata describing the run.

#### Scenario: Recognition session starts
- **WHEN** the user enters recognition mode and history capture is enabled
- **THEN** the system creates a timestamped session directory
- **AND** the system writes session metadata including model selection, backend type, parameters, and start time

#### Scenario: Recognition session stops
- **WHEN** the user exits recognition mode
- **THEN** the system finalizes the active history session
- **AND** saved records remain available in the configured history directory

#### Scenario: User reviews saved files
- **WHEN** the user opens the history directory
- **THEN** each saved record includes a screenshot file and machine-readable detection metadata that can be inspected outside the application
