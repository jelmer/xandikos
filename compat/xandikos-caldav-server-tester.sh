#!/bin/bash
# Run caldav-server-tester against Xandikos.
set -e

. $(dirname $0)/common.sh

VENV_DIR=$(dirname $0)/caldav-server-tester-venv
[ -z "$PYTHON" ] && PYTHON=python3

# Set up virtual environment
if [ ! -d "${VENV_DIR}" ]; then
    echo "Creating virtual environment for caldav-server-tester"
    ${PYTHON} -m venv "${VENV_DIR}"
fi

# Activate virtual environment
source "${VENV_DIR}/bin/activate"

# Install caldav and caldav-server-tester
echo "Installing caldav and caldav-server-tester..."
pip install -q --upgrade pip
# Install pinned versions from requirements file
if pip install -q -r "$(dirname $0)/caldav-server-tester-requirements.txt" 2>/dev/null; then
    echo "caldav-server-tester installed successfully"
else
    echo "WARNING: caldav-server-tester not available on PyPI, skipping..."
    echo "The testCheckCompatibility test will be skipped"
fi

# Deactivate venv before running xandikos so it uses system Python
deactivate

# Create test configuration
cat <<EOF>$(dirname $0)/caldav-server-tester-venv/test_compatibility.py
import unittest
import caldav
from caldav.compatibility_hints import FeatureSet


class TestXandikosCompatibility(unittest.TestCase):
    """Test Xandikos server CalDAV compatibility."""

    @classmethod
    def setUpClass(cls):
        """Set up test class."""
        # Configure known Xandikos limitations/quirks
        #
        # Xandikos supports most core CalDAV features including:
        # - Basic calendar operations (create, delete, read, update)
        # - Event and todo management
        # - Time-range searches for events and todos
        # - Category searches (basic)
        # - Combined searches (logical AND of time-range and category)
        # - Recurring events (basic support)
        # - Server-side recurrence expansion for events (basic cases)
        #
        # Known limitations/unsupported features:
        xandikos_features = FeatureSet({
            # Category search with full string matching is not supported
            # (e.g., "hands,feet,head" won't match an event with those exact categories)
            "search.category.fullstring": "unsupported",

            # Component type filtering is required - searches must specify event=True or todo=True
            # (can't search without explicit component type specification)
            "search.comp-type-optional": "unsupported",

            # Recurring task queries with status filters fail when querying future recurrences
            # (searching for pending recurring tasks doesn't include implicit future occurrences)
            "search.recurrences.includes-implicit.todo.pending": "unsupported",

            # Server-side recurrence expansion is buggy for tasks and event exceptions
            # (expanded recurring todos and events with exceptions may not be handled correctly)
            "search.recurrences.expanded.todo": "unsupported",
            "search.recurrences.expanded.exception": "unsupported",
        })

        cls.caldav = caldav.DAVClient(
            url='http://localhost:5233/',
            username=None,
            password=None
        )
        cls.caldav.features = xandikos_features

    def test_check_compatibility(self):
        """Run server quirk checker against Xandikos."""
        from caldav_server_tester import ServerQuirkChecker

        checker = ServerQuirkChecker(self.caldav, debug_mode="assert")
        checker.check_all()

        # Report results
        observed = checker.features_checked.dotted_feature_set_list(compact=True)

        print("\n" + "="*60)
        print("Xandikos Server Compatibility Report")
        print("="*60)
        for feature, details in observed.items():
            support = details.get('support', 'unknown')
            print(f"{feature}: {support}")
            if 'behaviour' in details:
                print(f"  Behaviour: {details['behaviour']}")
        print("="*60)


if __name__ == '__main__':
    unittest.main(verbosity=2)
EOF

run_xandikos 5233 5234 --defaults

# Reactivate the virtual environment to run tests
source "${VENV_DIR}/bin/activate"

# Run the compatibility test
cd "${VENV_DIR}"
python -m unittest test_compatibility "$@"
