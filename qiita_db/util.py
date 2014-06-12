r"""
Util functions (:mod: `qiita_db.util`)
======================================

..currentmodule:: qiita_db.util

This module provides different util functions.

Methods
-------

..autosummary::
    :toctree: generated/

    quote_column_name
    quote_data_value
    get_datatypes
    scrub_data
    exists_table
    exists_dynamic_table
    get_db_files_base_dir
    compute_checksum

"""
# -----------------------------------------------------------------------------
# Copyright (c) 2014--, The Qiita Development Team.
#
# Distributed under the terms of the BSD 3-clause License.
#
# The full license is in the file LICENSE, distributed with this software.
# -----------------------------------------------------------------------------

from __future__ import division
from binascii import crc32

from qiita_db.sql_connection import SQLConnectionHandler


def quote_column_name(c):
    """Lowercases the string and puts double quotes around it
    """
    return '"%s"' % c.lower()


def quote_data_value(c):
    """Puts single quotes around a string"""
    return "'%s'" % c


def scrub_data(s):
    r"""Scrubs data fields of characters not allowed by PostgreSQL

    disallowed characters:
        '   ;

    Parameters
    ----------
    s : str
        The string to clean up

    Returns
    -------
    str
        The scrubbed string
    """
    ret = s.replace("'", "")
    ret = ret.replace(";", "")
    return ret


def exists_table(table, conn_handler):
    r"""Checks if `table` exists on the database connected through
    `conn_handler`

    Parameters
    ----------
    table : str
        The table name to check if exists
    conn_handler : SQLConnectionHandler
        The connection handler object connected to the DB
    """
    return conn_handler.execute_fetchone(
        "SELECT exists(SELECT * FROM information_schema.tables WHERE "
        "table_name=%s)", (table,))[0]


def exists_dynamic_table(table, prefix, suffix, conn_handler):
    r"""Checks if the dynamic`table` exists on the database connected through
    `conn_handler`, and its name starts with prefix and ends with suffix

    Parameters
    ----------
    table : str
        The table name to check if exists
    prefix : str
        The table name prefix
    suffix : str
        The table name suffix
    conn_handler : SQLConnectionHandler
        The connection handler object connected to the DB
    """
    return (table.startswith(prefix) and table.endswith(suffix) and
            exists_table(table, conn_handler))


def get_db_files_base_dir(conn_handler=None):
    r"""Returns the path to the base directory of all db files

    Returns
    -------
    str
        The path to the base directory of all db files
    """
    conn_handler = (conn_handler if conn_handler is not None
                    else SQLConnectionHandler())
    return conn_handler.execute_fetchone(
        "SELECT base_data_dir FROM settings")[0]


def compute_checksum(filepath):
    r"""Returns the checksum of the file pointed by filepath

    Parameters
    ----------
    filepath : str
        The path to the file

    Returns
    -------
    int
        The file checksum
    """
    crc = None
    with open(filepath, "Ub") as f:
        # Go line by line so we don't need to load the entire file in memory
        for line in f:
            if crc is None:
                crc = crc32(line)
            else:
                crc = crc32(line, crc)
    # We need the & 0xffffffff in order to get the same numeric value across
    # all python versions and platforms
    return crc & 0xffffffff
