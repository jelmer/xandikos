Xandikos uses the PEP8 style guide.

You can install mandatory development dependencies with:

```
pip install .[dev]
```

You can verify whether you've introduced any style violations by running

```
ruff check; ruff format --check .
```

To check for type errors, rnu:

```
mypy xandikos
```

To run the tests, run:

```
python3 -m unittest tests.test_suite
```

Convenience targets in the Makefile are also provided ("make check", "make style", "make typing").

To run the compatibility tests, run one of:

```
make check-litmus
make check-pycaldav
make check-caldav-server-tester
make check-vdirsyncer
```

There are some very minimal developer documentation/vague design docs in notes/.

Please implement new RFCs as much as possible in their own file.
