# Dystros
# Copyright (C) 2016 Jelmer Vernooij <jelmer@jelmer.uk>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; version 2
# of the License or (at your option) any later version of
# the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA  02110-1301, USA.

import tempfile
import shutil
import unittest

from dystros.collection import GitCollection


class GitCollectionTest(unittest.TestCase):

    def test_create_bare(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        gc = GitCollection.create(d, bare=True)
        self.assertIsInstance(gc, GitCollection)
        self.assertEqual(gc.repo.path, d)

    def test_create_nonbare(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        gc = GitCollection.create(d, bare=False)
        self.assertIsInstance(gc, GitCollection)
        self.assertEqual(gc.repo.path, d)
