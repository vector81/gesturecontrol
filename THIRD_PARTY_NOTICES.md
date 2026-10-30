# Third-party components

GestureControl's original source code is MIT licensed. Dependencies, external applications and downloaded assets retain their own licenses and terms.

- [MediaPipe](https://github.com/google-ai-edge/mediapipe): hand landmark inference. The model is downloaded from Google's public hosting during setup, not committed here.
- [OpenCV](https://github.com/opencv/opencv): camera capture and image processing, installed through `opencv-contrib-python`.
- [PyAutoGUI](https://github.com/asweigart/pyautogui): Windows pointer input.
- [Qt for Python / PySide6](https://doc.qt.io/qtforpython-6/licenses.html): native UI. Review upstream LGPL/GPL/commercial licensing options before redistributing a packaged application with Qt binaries.
- [NumPy](https://numpy.org/): image arrays and numerical operations.
- [pytest](https://pytest.org/): automated tests.
- [DroidCam](https://droidcam.app/): a separate third-party application; not included or relicensed by this project. Some features require its paid upgrade.

Python dependencies are installed separately by pip. Windows fonts are loaded from the user's existing installation and are not distributed. USB drivers and personal diagnostic artifacts are not part of the repository.
