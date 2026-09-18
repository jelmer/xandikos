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
# Install pinned versions from requirements file. A failure here used to be
# swallowed, which left the compatibility test failing later with a confusing
# ImportError instead of the actual pip error.
pip install -q -r "$(dirname $0)/caldav-server-tester-requirements.txt"

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
        # Where Xandikos deviates from the checker's default expectations.
        xandikos_features = FeatureSet({
            # Principal property search returns 403 (not implemented)
            "principal-search": "ungraceful",
            # Xandikos applies a time-range filter that carries no component
            # type to every component, rather than rejecting the query. The
            # tester defaults to "unsupported" because RFC4791 section 9.7 has
            # nowhere legal to put such a time-range, but accepting it is a
            # superset of the required behaviour.
            "search.time-range.comp-type-optional": {"support": "full"},
            # supported-calendar-component-set has no setter: every calendar
            # reports the same hardcoded component list and accepts any
            # component, yet MKCALENDAR still answers 201.
            "create-calendar.with-supported-component-types": {
                "support": "unsupported",
                "behaviour": (
                    "the restriction is ignored: asked for ['VTODO'], it "
                    "advertises ['VAVAILABILITY', 'VEVENT', 'VFREEBUSY', "
                    "'VJOURNAL', 'VTODO'], and a VEVENT can be saved to the "
                    "calendar"
                ),
            },
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
