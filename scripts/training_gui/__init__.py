"""The local run console for encoder training.

A small FastAPI application that starts pre-configured training runs from a
browser page on the machine that has the GPU. It is offline tooling: nothing in
``app/`` imports it, and the guard in
``tests/test_encoder_training_dataset.py::test_app_never_imports_the_offline_tooling``
covers it automatically because that test rejects any ``scripts`` import.

The console never decides anything about training. It selects a command from a
catalogue checked into the repository, runs it, and shows what it wrote.
"""
