# -----------------------------------------------------------------------------
# Copyright (c) 2014--, The Qiita Development Team.
#
# Distributed under the terms of the BSD 3-clause License.
#
# The full license is in the file LICENSE, distributed with this software.
# -----------------------------------------------------------------------------

# Sample template constants
SAMPLE_TEMPLATE_EBI_COLS = {
    'collection_timestamp': 'timestamp',
    'physical_specimen_location': 'varchar'
}

SAMPLE_TEMPLATE_MAIN_COLS = {
    'sample_type': 'varchar',
    'description': 'varchar',
    'physical_specimen_remaining': 'bool',
    'dna_extracted': 'bool',
    'latitude': 'float8',
    'longitude': 'float8',
    'host_subject_id': 'varchar'
}

# Prep template constants
TARGET_GENE_DATA_TYPES = ['16S', '18S', 'ITS']
REQUIRED_TARGET_GENE_COLS = {'barcodesequence', 'linkerprimersequence',
                             'run_prefix', 'library_construction_protocol',
                             'experiment_design_description', 'platform'}
RENAME_COLS_DICT = {'barcode': 'barcodesequence',
                    'primer': 'linkerprimersequence'}
