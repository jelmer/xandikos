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
        })

        # Multi-user mode with two principals, so the cross-user RFC 6638
        # checks (free/busy lookup, inbox delivery, auto-schedule,
        # schedule-tag) actually run instead of reporting "unknown".
        # X-Remote-User is trusted from localhost; see the server flags below.
        cls.caldav = cls._client('alice')
        cls.caldav.features = xandikos_features
        cls.extra = cls._client('bob')

        # Each principal needs its own calendar-user-address-set to be
        # addressable as an attendee; multi-user mode has no default email
        # to fall back on.
        for client, address in ((cls.caldav, 'alice'), (cls.extra, 'bob')):
            client.principal().set_properties([
                caldav.elements.cdav.CalendarUserAddressSet()
                + caldav.elements.dav.Href(value='mailto:%s@example.com' % address)
            ])

    @staticmethod
    def _client(user):
        return caldav.DAVClient(
            url='http://127.0.0.1:5233/',
            headers={'X-Remote-User': user},
        )

    def test_check_compatibility(self):
        """Run server quirk checker against Xandikos."""
        from caldav_server_tester import ServerQuirkChecker

        checker = ServerQuirkChecker(
            self.caldav, debug_mode="assert", extra_clients=[self.extra]
        )
        checker.check_all()

        # The cross-user setup is easy to break (a stale trust CIDR, a
        # principal without an address); without it the RFC 6638 checks
        # quietly report "unknown" and the run still passes. Fail loudly
        # instead.
        self.assertEqual(1, len(checker.extra_principals))
        for feature in (
            'scheduling',
            'scheduling.mailbox',
            'scheduling.freebusy-query',
            'scheduling.auto-schedule',
            'scheduling.schedule-tag',
            'scheduling.schedule-tag.stable-partstat',
        ):
            self.assertEqual(
                'full',
                checker.features_checked.is_supported(feature, str),
                '%s was not established as supported' % feature,
            )

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

XANDIKOS_SUBCOMMAND=multi-user \
	run_xandikos 5233 5234 --defaults --trust-x-remote-user-from=127.0.0.1/32

# Reactivate the virtual environment to run tests
source "${VENV_DIR}/bin/activate"

# Run the compatibility test
cd "${VENV_DIR}"
python -m unittest test_compatibility "$@"
