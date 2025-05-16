# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Xandikos is a lightweight CardDAV/CalDAV server that stores data in Git repositories. It implements WebDAV, CalDAV, and CardDAV protocols, enabling calendar and contact synchronization with various clients like Thunderbird, iOS, and mobile apps.

## Development Commands

### Core Commands

```bash
# Install dependencies
pip install -e '.[dev]'

# Run tests
make check  # Run unit tests
make style  # Run ruff linter
make typing  # Run mypy type checks
python -m unittest xandikos.tests.test_suite  # Run all tests with unittest
python -m unittest xandikos.tests.test_caldav  # Run specific test module

# Run compatibility tests
make check-litmus  # Run WebDAV test suite
make check-pycaldav  # Run pycaldav client tests
make check-vdirsyncer  # Run vdirsyncer client tests
make check-all  # Run all checks (unit tests, compatibility tests, style checks)

# Coverage
make coverage  # Generate coverage data
make coverage-html  # Generate HTML coverage report

# Documentation
make docs  # Build documentation

# Start development server with default calendars/address books
./bin/xandikos --defaults -d $HOME/dav
```

### Code Formatting

```bash
make reformat  # Format code with ruff
```

## Architecture

Xandikos has a layered architecture:

1. **Protocol Layer**
   - `webdav.py`: Core WebDAV implementation
   - `caldav.py`: CalDAV protocol (calendars)
   - `carddav.py`: CardDAV protocol (contacts)
   - `davcommon.py`: Shared DAV functionality

2. **Storage Layer**
   - `store/git.py`: Git-based storage backend
   - `store/vdir.py`: Directory-based storage
   - `store/index.py`: Property indexing
   - `store/config.py`: Collection configuration

3. **Web/Application Layer**
   - `web.py`: Main application that combines protocols
   - `wsgi.py`: WSGI application interface

4. **Data Format Handling**
   - `icalendar.py`: iCalendar format for events
   - `vcard.py`: vCard format for contacts

5. **Entry Point**
   - `__main__.py`: CLI interface

The server follows a stateless design, with all data stored in Git repositories. This provides versioning, history, and recovery capabilities. Collections (calendars/address books) are stored as directories containing .ics or .vcf files.

## Key Concepts

1. **Collections**: Containers for resources (calendar/address book)
2. **Resources**: Individual items (events/contacts)
3. **Properties**: Metadata on collections/resources
4. **Git Storage**: Files stored in Git repos with UIDs as identifiers

## Limitations

- Designed primarily for single-user deployment
- Relies on external authentication through REMOTE_USER
- Limited multi-user support

## Rust Component

The project has an early-stage Rust component (using pyo3) intended to integrate with the Python codebase. This is incomplete and under development.