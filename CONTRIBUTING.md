# Contributing

Bug reports, documentation improvements and pull requests are welcome.

1. Use Windows 10/11 and Python 3.12.
2. Run `Setup.bat` to create the environment and download the model.
3. Run `.venv\Scripts\python.exe -m pytest -q` before submitting changes.
4. Run `.venv\Scripts\python.exe selftest.py` for hardware-free runtime validation.
5. After configuring a camera, `tools/check_studio.py` tests the live dashboard with simulated mouse output.

Tests must not inject actual mouse input. Use `FakeMouse` or another output sink. Preserve F8's latched stop, button release on interruption, bounded camera shutdown and local-only processing. Verify UI changes at the minimum window size as well as the default size.

Keep pull requests focused and describe the problem, changed behavior and validation. Do not commit `config.json`, local IP addresses, camera images, logs, phone identifiers, virtual environments, driver downloads or model binaries. Use `config.example.json` as a sanitized starting point.

For recognition bugs, report Windows/Python versions, camera source type, lighting and hand pose. Redact personal paths and network addresses from logs. Screenshots are optional; Showcase view avoids including the camera background.

By contributing, you agree to license your contributions under the project's MIT license. Third-party components retain their own licenses.
