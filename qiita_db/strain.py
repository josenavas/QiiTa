# -----------------------------------------------------------------------------
# Copyright (c) 2014--, The Qiita Development Team.
#
# Distributed under the terms of the BSD 3-clause License.
#
# The full license is in the file LICENSE, distributed with this software.
# -----------------------------------------------------------------------------

from __future__ import division

from .base import QiitaObject
from .sql_connection import SQLConnectionHandler
from .util import insert_filepaths, convert_to_id
from .exceptions import QiitaDBDuplicateError


class Strain(QiitaObject):
    r""""""

    _table = "strain"

    @classmethod
    def create(cls, unofficial_name, sequence_fp, sample_id, isolation_date,
               isolation_description, storage_conditions_id,
               culture_collection_name):
        r""""""
        # Get the connection to the database
        conn_handler = SQLConnectionHandler()

        # Check if the strain already exists
        if cls.exists(unofficial_name, conn_handler=conn_handler):
            raise QiitaDBDuplicateError("Strain", unofficial_name)

        # Insert the object into the database
        strain_id = conn_handler.execute_fetchone(
            "INSERT INTO qiita.{0} (unofficial_name, sample_id, "
            "isolation_date, isolation_description, storage_conditions_id, "
            "culture_collection_name) VALUES "
            "(%s, %s, %s, %s, %s, %s) RETURNING strain_id".format(cls._table),
            (unofficial_name, sample_id, isolation_date, isolation_description,
             storage_conditions_id, culture_collection_name))[0]

        # Insert the filepath into the database
        filetype_id = convert_to_id("reference_seqs", "filepath_type",
                                    conn_handler)
        seq_fp_id = insert_filepaths(
            [(sequence_fp, filetype_id)], strain_id, "strain", "filepath",
            conn_handler)[0]

        conn_handler.execute("UPDATE qiita.{0} SET sequence_filepath_id=%s "
                             "WHERE strain_id=%s".format(cls._table),
                             (seq_fp_id, strain_id))

        return cls(strain_id)

    @classmethod
    def exists(cls, unofficial_name, conn_handler=None):
        r""""""
        conn_handler = conn_handler if conn_handler else SQLConnectionHandler()
        return conn_handler.execute_fetchone(
            "SELECT EXISTS(SELECT * FROM qiita.{0} WHERE "
            "unofficial_name=%s)".format(cls._table), (unofficial_name,))[0]
