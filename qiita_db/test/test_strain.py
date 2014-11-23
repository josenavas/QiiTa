# -----------------------------------------------------------------------------
# Copyright (c) 2014--, The Qiita Development Team.
#
# Distributed under the terms of the BSD 3-clause License.
#
# The full license is in the file LICENSE, distributed with this software.
# -----------------------------------------------------------------------------

from unittest import TestCase, main
from os import remove, close
from os.path import basename
from tempfile import mkstemp
from datetime import datetime

from qiita_core.util import qiita_test_checker
from qiita_db.strain import Strain
from qiita_db.util import get_mountpoint
from qiita_db.exceptions import QiitaDBDuplicateError


@qiita_test_checker()
class StrainTests(TestCase):
    def setUp(self):
        self.unofficial_name = "test unofficial_name"
        fd, self.sequence_fp = mkstemp(suffix=".fna")
        close(fd)
        self.sample_id = "1.SKB1.640202"
        self.isolation_date = datetime(2011, 11, 11, 13, 00, 00)
        self.isolation_description = "Some isolation description"
        self.storage_conditions_id = 1
        self.culture_collection_name = "ATCC"

        _, self.db_dir = get_mountpoint("strain")[0]
        self._clean_up_files = []

    def tearDown(self):
        for f in self._clean_up_files:
            remove(f)

    def test_create(self):
        """Correctly creates the rows in the DB for the strain"""
        # Check that the returned object has the correct id
        obs = Strain.create(
            self.unofficial_name, self.sequence_fp, self.sample_id,
            self.isolation_date, self.isolation_description,
            self.storage_conditions_id, self.culture_collection_name)
        self.assertEqual(obs.id, 2)

        # Check that the information on the database is correct
        obs = self.conn_handler.execute_fetchall(
            "SELECT * FROM qiita.strain WHERE strain_id=2")
        # strain_id, unofficial_name, official_name, taxonomy,
        # sequence_filepath_id, sample_id, isolation_date,
        # isolation_description, storage_conditions_id,
        # culture_collection_name, todo_properties
        exp = [[2, self.unofficial_name, None, None, 16, self.sample_id,
                self.isolation_date, self.isolation_description,
                self.storage_conditions_id, self.culture_collection_name,
                None]]
        self.assertEqual(obs, exp)

        # Check that the filepaths have been correctly added to the db
        obs = self.conn_handler.execute_fetchall(
            "SELECT * FROM qiita.filepath WHERE filepath_id=16")
        exp = [[16, "2_%s" % basename(self.sequence_fp), 10, '0', 1, 10]]
        self.assertEqual(obs, exp)

    def test_create_duplicate(self):
        with self.assertRaises(QiitaDBDuplicateError):
            Strain.create(
                "Bacteroides thetaiotaomicron VPI-5482, B. theta VPI-5482",
                self.sequence_fp, self.sample_id,
                self.isolation_date, self.isolation_description,
                self.storage_conditions_id, self.culture_collection_name)

    def test_exists_true(self):
        self.assertTrue(Strain.exists(
            "Bacteroides thetaiotaomicron VPI-5482, B. theta VPI-5482"))

    def test_exists_false(self):
        self.assertFalse(Strain.exists("Do not exists"))


if __name__ == '__main__':
    main()
