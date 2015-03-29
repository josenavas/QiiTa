# -----------------------------------------------------------------------------
# Copyright (c) 2014--, The Qiita Development Team.
#
# Distributed under the terms of the BSD 3-clause License.
#
# The full license is in the file LICENSE, distributed with this software.
# -----------------------------------------------------------------------------

from __future__ import division
from future.builtins import zip
from future.utils import viewitems, PY3
from copy import deepcopy
from os.path import join
from time import strftime
from functools import partial
from os.path import basename
from future.utils.six import StringIO

import pandas as pd
import numpy as np
import warnings
from skbio.util import find_duplicates
from skbio.io.util import open_file

from qiita_core.exceptions import IncompetentQiitaDeveloperError
from qiita_db.exceptions import (QiitaDBDuplicateError, QiitaDBColumnError,
                         QiitaDBUnknownIDError, QiitaDBNotImplementedError,
                         QiitaDBDuplicateHeaderError, QiitaDBError,
                         QiitaDBWarning, QiitaDBExecutionError)
from qiita_db.base import QiitaObject
from qiita_db.sql_connection import SQLConnectionHandler
from qiita_db.ontology import Ontology
from qiita_db.util import (exists_table, get_table_cols,
                   convert_to_id,
                   convert_from_id, get_mountpoint, insert_filepaths,
                   scrub_data, infer_status)
from qiita_db.study import Study
from qiita_db.data import RawData
from qiita_db.logger import LogEntry
from .base_metadata_template import BaseSample, MetadataTemplate
from .util import (as_python_types, get_invalid_sample_names, get_datatypes,
                   prefix_sample_names_with_id)

if PY3:
    from string import ascii_letters as letters, digits
else:
    from string import letters, digits


class PrepSample(BaseSample):
    r"""Class that models a sample present in a PrepTemplate.

    See Also
    --------
    BaseSample
    Sample
    """
    _table = "common_prep_info"
    _table_prefix = "prep_"
    _column_table = "prep_columns"
    _id_column = "prep_template_id"

    def _check_template_class(self, md_template):
        r"""Checks that md_template is of the correct type

        Parameters
        ----------
        md_template : PrepTemplate
            The metadata template

        Raises
        ------
        IncompetentQiitaDeveloperError
            If `md_template` is not a PrepTemplate object
        """
        if not isinstance(md_template, PrepTemplate):
            raise IncompetentQiitaDeveloperError()


class PrepTemplate(MetadataTemplate):
    r"""Represent the PrepTemplate of a raw data. Provides access to the
    tables in the DB that holds the sample preparation information.

    See Also
    --------
    MetadataTemplate
    SampleTemplate
    """
    _table = "common_prep_info"
    _table_prefix = "prep_"
    _column_table = "prep_columns"
    _id_column = "prep_template_id"
    _sample_cls = PrepSample

    @classmethod
    def create(cls, md_template, raw_data, study, data_type,
               investigation_type=None):
        r"""Creates the metadata template in the database

        Parameters
        ----------
        md_template : DataFrame
            The metadata template file contents indexed by samples Ids
        raw_data : RawData
            The raw_data to which the prep template belongs to.
        study : Study
            The study to which the prep template belongs to.
        data_type : str or int
            The data_type of the prep template
        investigation_type : str, optional
            The investigation type, if relevant

        Returns
        -------
        A new instance of `cls` to access to the PrepTemplate stored in the DB

        Raises
        ------
        QiitaDBColumnError
            If the investigation_type is not valid
            If a required column is missing in md_template
        """
        # If the investigation_type is supplied, make sure it is one of
        # the recognized investigation types
        if investigation_type is not None:
            cls.validate_investigation_type(investigation_type)

        invalid_ids = get_invalid_sample_names(md_template.index)
        if invalid_ids:
            raise QiitaDBColumnError("The following sample names in the prep"
                                     " template contain invalid characters "
                                     "(only alphanumeric characters or periods"
                                     " are allowed): %s." %
                                     ", ".join(invalid_ids))
        # We are going to modify the md_template. We create a copy so
        # we don't modify the user one
        md_template = deepcopy(md_template)

        # Prefix the sample names with the study_id
        prefix_sample_names_with_id(md_template, study.id)

        # In the database, all the column headers are lowercase
        md_template.columns = [c.lower() for c in md_template.columns]

        # Check that we don't have duplicate columns
        if len(set(md_template.columns)) != len(md_template.columns):
            raise QiitaDBDuplicateHeaderError(
                find_duplicates(md_template.columns))

        # Get a connection handler
        conn_handler = SQLConnectionHandler()
        queue_name = "CREATE_PREP_TEMPLATE_%d" % raw_data.id
        conn_handler.create_queue(queue_name)

        # Check if the data_type is the id or the string
        if isinstance(data_type, (int, long)):
            data_type_id = data_type
            data_type_str = convert_from_id(data_type, "data_type",
                                            conn_handler)
        else:
            data_type_id = convert_to_id(data_type, "data_type", conn_handler)
            data_type_str = data_type

        # We need to check for some special columns, that are not present on
        # the database, but depending on the data type are required.
        missing = cls._check_special_columns(md_template, data_type_str)

        # Get some useful information from the metadata template
        sample_ids = md_template.index.tolist()
        num_samples = len(sample_ids)

        # Get the required columns from the DB
        db_cols = get_table_cols(cls._table, conn_handler)

        # Remove the sample_id and study_id columns
        db_cols.remove('sample_id')
        db_cols.remove(cls._id_column)

        # Retrieve the headers of the metadata template
        headers = list(md_template.keys())

        # Check that md_template has the required columns
        remaining = set(db_cols).difference(headers)
        missing = missing.union(remaining)
        missing = missing.difference(cls.translate_cols_dict)
        if missing:
            raise QiitaDBColumnError("Missing columns: %s"
                                     % ', '.join(missing))

        # Insert the metadata template
        # We need the prep_id for multiple calls below, which currently is not
        # supported by the queue system. Thus, executing this outside the queue
        prep_id = conn_handler.execute_fetchone(
            "INSERT INTO qiita.prep_template (data_type_id, raw_data_id, "
            "investigation_type) VALUES (%s, %s, %s) RETURNING "
            "prep_template_id", (data_type_id, raw_data.id,
                                 investigation_type))[0]

        # Insert values on required columns
        values = _as_python_types(md_template, db_cols)
        values.insert(0, sample_ids)
        values.insert(0, [prep_id] * num_samples)
        values = [v for v in zip(*values)]
        conn_handler.add_to_queue(
            queue_name,
            "INSERT INTO qiita.{0} ({1}, sample_id, {2}) "
            "VALUES (%s, %s, {3})".format(
                cls._table, cls._id_column, ', '.join(db_cols),
                ', '.join(['%s'] * len(db_cols))),
            values, many=True)

        # Insert rows on *_columns table
        headers = list(set(headers).difference(db_cols))
        datatypes = _get_datatypes(md_template.ix[:, headers])
        # psycopg2 requires a list of tuples, in which each tuple is a set
        # of values to use in the string formatting of the query. We have all
        # the values in different lists (but in the same order) so use zip
        # to create the list of tuples that psycopg2 requires.
        values = [
            v for v in zip([prep_id] * len(headers), headers, datatypes)]
        conn_handler.add_to_queue(
            queue_name,
            "INSERT INTO qiita.{0} ({1}, column_name, column_type) "
            "VALUES (%s, %s, %s)".format(cls._column_table, cls._id_column),
            values, many=True)

        # Create table with custom columns
        table_name = cls._table_name(prep_id)
        column_datatype = ["%s %s" % (col, dtype)
                           for col, dtype in zip(headers, datatypes)]
        conn_handler.add_to_queue(
            queue_name,
            "CREATE TABLE qiita.{0} (sample_id varchar, "
            "{1})".format(table_name, ', '.join(column_datatype)))

        # Insert values on custom table
        values = _as_python_types(md_template, headers)
        values.insert(0, sample_ids)
        values = [v for v in zip(*values)]
        conn_handler.add_to_queue(
            queue_name,
            "INSERT INTO qiita.{0} (sample_id, {1}) "
            "VALUES (%s, {2})".format(table_name, ", ".join(headers),
                                      ', '.join(["%s"] * len(headers))),
            values, many=True)

        try:
            conn_handler.execute_queue(queue_name)
        except Exception:
            # Clean up row from qiita.prep_template
            conn_handler.execute(
                "DELETE FROM qiita.prep_template where "
                "{0} = %s".format(cls._id_column), (prep_id,))

            # Check if sample IDs present here but not in sample template
            sql = ("SELECT sample_id from qiita.required_sample_info WHERE "
                   "study_id = %s")
            # Get list of study sample IDs, prep template study IDs,
            # and their intersection
            prep_samples = set(md_template.index.values)
            unknown_samples = prep_samples.difference(
                s[0] for s in conn_handler.execute_fetchall(sql, [study.id]))
            if unknown_samples:
                raise QiitaDBExecutionError(
                    'Samples found in prep template but not sample template: '
                    '%s' % ', '.join(unknown_samples))

            # some other error we haven't seen before so raise it
            raise

        # figuring out the filepath of the backup
        _id, fp = get_mountpoint('templates')[0]
        fp = join(fp, '%d_prep_%d_%s.txt' % (study.id, prep_id,
                  strftime("%Y%m%d-%H%M%S")))
        # storing the backup
        pt = cls(prep_id)
        pt.to_file(fp)

        # adding the fp to the object
        pt.add_filepath(fp)

        # creating QIIME mapping file
        pt.create_qiime_mapping_file(fp)

        return pt

    @classmethod
    def validate_investigation_type(self, investigation_type):
        """Simple investigation validation to avoid code duplication

        Parameters
        ----------
        investigation_type : str
            The investigation type, should be part of the ENA ontology

        Raises
        -------
        QiitaDBColumnError
            The investigation type is not in the ENA ontology
        """
        ontology = Ontology(convert_to_id('ENA', 'ontology'))
        terms = ontology.terms + ontology.user_defined_terms
        if investigation_type not in terms:
            raise QiitaDBColumnError("'%s' is Not a valid investigation_type. "
                                     "Choose from: %s" % (investigation_type,
                                                          ', '.join(terms)))

    @classmethod
    def _check_template_special_columns(cls, md_template, data_type):
        r"""Checks for special columns based on obj type

        Parameters
        ----------
        md_template : DataFrame
            The metadata template file contents indexed by sample ids
        data_type : str
            The data_type of the template.

        Returns
        -------
        set
            The set of missing columns

        Notes
        -----
        Sometimes people use different names for the same columns. We just
        rename them to use the naming that we expect, so this is normalized
        across studies.
        """
        # We only have column requirements if the data type of the raw data
        # is one of the target gene types
        missing_cols = set()
        if data_type in TARGET_GENE_DATA_TYPES:
            md_template.rename(columns=RENAME_COLS_DICT, inplace=True)

            # Check for all required columns for target genes studies
            missing_cols = REQUIRED_TARGET_GENE_COLS.difference(
                md_template.columns)

        return missing_cols

    @classmethod
    def delete(cls, id_):
        r"""Deletes the table from the database

        Parameters
        ----------
        id_ : obj
            The object identifier

        Raises
        ------
        QiitaDBExecutionError
            If the prep template already has a preprocessed data
        QiitaDBUnknownIDError
            If no prep template with id = id_ exists
        """
        table_name = cls._table_name(id_)
        conn_handler = SQLConnectionHandler()

        if not cls.exists(id_):
            raise QiitaDBUnknownIDError(id_, cls.__name__)

        preprocessed_data_exists = conn_handler.execute_fetchone(
            "SELECT EXISTS(SELECT * FROM qiita.prep_template_preprocessed_data"
            " WHERE prep_template_id=%s)", (id_,))[0]

        if preprocessed_data_exists:
            raise QiitaDBExecutionError("Cannot remove prep template %d "
                                        "because a preprocessed data has been"
                                        " already generated using it." % id_)

        # Delete the prep template filepaths
        conn_handler.execute(
            "DELETE FROM qiita.prep_template_filepath WHERE "
            "prep_template_id = %s", (id_, ))

        # Drop the prep_X table
        conn_handler.execute(
            "DROP TABLE qiita.{0}".format(table_name))

        # Remove the rows from common_prep_info
        conn_handler.execute(
            "DELETE FROM qiita.{0} where {1} = %s".format(cls._table,
                                                          cls._id_column),
            (id_,))

        # Remove the rows from prep_columns
        conn_handler.execute(
            "DELETE FROM qiita.{0} where {1} = %s".format(cls._column_table,
                                                          cls._id_column),
            (id_,))

        # Remove the row from prep_template
        conn_handler.execute(
            "DELETE FROM qiita.prep_template where "
            "{0} = %s".format(cls._id_column), (id_,))

    def data_type(self, ret_id=False):
        """Returns the data_type or the data_type id

        Parameters
        ----------
        ret_id : bool, optional
            If true, return the id instead of the string, default false.

        Returns
        -------
        str or int
            string value of data_type or data_type_id if ret_id is True
        """
        ret = "_id" if ret_id else ""
        conn_handler = SQLConnectionHandler()
        return conn_handler.execute_fetchone(
            "SELECT d.data_type{0} FROM qiita.data_type d JOIN "
            "qiita.prep_template p ON p.data_type_id = d.data_type_id WHERE "
            "p.prep_template_id=%s".format(ret), (self.id,))[0]

    @property
    def raw_data(self):
        conn_handler = SQLConnectionHandler()
        return conn_handler.execute_fetchone(
            "SELECT raw_data_id FROM qiita.prep_template "
            "WHERE prep_template_id=%s", (self.id,))[0]

    @property
    def preprocessed_data(self):
        conn_handler = SQLConnectionHandler()
        prep_datas = conn_handler.execute_fetchall(
            "SELECT preprocessed_data_id FROM "
            "qiita.prep_template_preprocessed_data WHERE prep_template_id=%s",
            (self.id,))
        return [x[0] for x in prep_datas]

    @property
    def preprocessing_status(self):
        r"""Tells if the data has been preprocessed or not

        Returns
        -------
        str
            One of {'not_preprocessed', 'preprocessing', 'success', 'failed'}
        """
        conn_handler = SQLConnectionHandler()
        return conn_handler.execute_fetchone(
            "SELECT preprocessing_status FROM qiita.prep_template "
            "WHERE {0}=%s".format(self._id_column), (self.id,))[0]

    @preprocessing_status.setter
    def preprocessing_status(self, state):
        r"""Update the preprocessing status

        Parameters
        ----------
        state : str, {'not_preprocessed', 'preprocessing', 'success', 'failed'}
            The current status of preprocessing

        Raises
        ------
        ValueError
            If the state is not known.
        """
        if (state not in ('not_preprocessed', 'preprocessing', 'success') and
                not state.startswith('failed:')):
            raise ValueError('Unknown state: %s' % state)

        conn_handler = SQLConnectionHandler()

        conn_handler.execute(
            "UPDATE qiita.prep_template SET preprocessing_status = %s "
            "WHERE {0} = %s".format(self._id_column),
            (state, self.id))

    @property
    def investigation_type(self):
        conn_handler = SQLConnectionHandler()
        sql = ("SELECT investigation_type FROM qiita.prep_template "
               "WHERE {0} = %s".format(self._id_column))
        return conn_handler.execute_fetchone(sql, [self._id])[0]

    @investigation_type.setter
    def investigation_type(self, investigation_type):
        r"""Update the investigation type

        Parameters
        ----------
        investigation_type : str
            The investigation type to set, should be part of the ENA ontology

        Raises
        ------
        QiitaDBColumnError
            If the investigation type is not a valid ENA ontology
        """
        if investigation_type is not None:
            self.validate_investigation_type(investigation_type)

        conn_handler = SQLConnectionHandler()

        conn_handler.execute(
            "UPDATE qiita.prep_template SET investigation_type = %s "
            "WHERE {0} = %s".format(self._id_column),
            (investigation_type, self.id))

    @property
    def study_id(self):
        """Gets the study id with which this prep template is associated

        Returns
        -------
        int
            The ID of the study with which this prep template is associated
        """
        conn = SQLConnectionHandler()
        sql = ("SELECT srd.study_id FROM qiita.prep_template pt JOIN "
               "qiita.study_raw_data srd ON pt.raw_data_id = srd.raw_data_id "
               "WHERE prep_template_id = %d" % self.id)
        study_id = conn.execute_fetchone(sql)
        if study_id:
            return study_id[0]
        else:
            raise QiitaDBError("No studies found associated with prep "
                               "template ID %d" % self._id)

    def create_qiime_mapping_file(self, prep_template_fp):
        """This creates the QIIME mapping file and links it in the db.

        Parameters
        ----------
        prep_template_fp : str
            The prep template filepath that should be concatenated to the
            sample template go used to generate a new  QIIME mapping file

        Returns
        -------
        filepath : str
            The filepath of the created QIIME mapping file

        Raises
        ------
        ValueError
            If the prep template is not a subset of the sample template
        """
        rename_cols = {
            'barcode': 'BarcodeSequence',
            'barcodesequence': 'BarcodeSequence',
            'primer': 'LinkerPrimerSequence',
            'linkerprimersequence': 'LinkerPrimerSequence',
            'description': 'Description',
        }

        # getting the latest sample template
        _, sample_template_fp = SampleTemplate(
            self.study_id).get_filepaths()[0]

        # reading files via pandas
        st = load_template_to_dataframe(sample_template_fp)
        pt = load_template_to_dataframe(prep_template_fp)
        st_sample_names = set(st.index)
        pt_sample_names = set(pt.index)

        if not pt_sample_names.issubset(st_sample_names):
            raise ValueError(
                "Prep template is not a sub set of the sample template, files:"
                "%s %s - samples: %s" % (sample_template_fp, prep_template_fp,
                                         str(pt_sample_names-st_sample_names)))

        mapping = pt.join(st, lsuffix="_prep")
        mapping.rename(columns=rename_cols, inplace=True)

        # Gets the orginal mapping columns and readjust the order to comply
        # with QIIME requirements
        cols = mapping.columns.values.tolist()
        cols.remove('BarcodeSequence')
        cols.remove('LinkerPrimerSequence')
        cols.remove('Description')
        new_cols = ['BarcodeSequence', 'LinkerPrimerSequence']
        new_cols.extend(cols)
        new_cols.append('Description')
        mapping = mapping[new_cols]

        # figuring out the filepath for the QIIME map file
        _id, fp = get_mountpoint('templates')[0]
        filepath = join(fp, '%d_prep_%d_qiime_%s.txt' % (self.study_id,
                        self.id, strftime("%Y%m%d-%H%M%S")))

        # Save the mapping file
        mapping.to_csv(filepath, index_label='#SampleID', na_rep='unknown',
                       sep='\t')

        # adding the fp to the object
        self.add_filepath(filepath)

        return filepath

    @property
    def status(self):
        """The status of the prep template

        Returns
        -------
        str
            The status of the prep template

        Notes
        -----
        The status of a prep template is inferred by the status of the
        processed data generated from this prep template. If no processed
        data has been generated with this prep template; then the status
        is 'sandbox'.
        """
        conn_handler = SQLConnectionHandler()
        sql = """SELECT processed_data_status
                FROM qiita.processed_data_status pds
                  JOIN qiita.processed_data pd
                    USING (processed_data_status_id)
                  JOIN qiita.preprocessed_processed_data ppd_pd
                    USING (processed_data_id)
                  JOIN qiita.prep_template_preprocessed_data pt_ppd
                    USING (preprocessed_data_id)
                WHERE pt_ppd.prep_template_id=%s"""
        pd_statuses = conn_handler.execute_fetchall(sql, (self._id,))

        return infer_status(pd_statuses)
