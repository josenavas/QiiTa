#!/usr/bin/env python
from __future__ import division

# -----------------------------------------------------------------------------
# Copyright (c) 2014--, The Qiita Development Team.
#
# Distributed under the terms of the BSD 3-clause License.
#
# The full license is in the file LICENSE, distributed with this software.
# -----------------------------------------------------------------------------

from pyqi.core.command import Command, CommandIn, ParameterCollection

from qiita_db.metadata_template import SampleTemplate
from qiime.util import MetadataMap


class SampleTemplateAdder(Command):
    BriefDescription = "Adds the sample template information to the database"
    LongDescription = "Adds sample template information to the database"
    CommandIns = ParameterCollection([
        CommandIn(Name='sample_template', DataType=MetadataMap,
                  Description="Sample template information to add to the "
                              "database.",
                  Required=True),
        CommandIn(Name='study_id', DataType=str,
                  Description="The study database identifier to which the "
                  "sample template belongs to.",
                  Required=True),
        CommandIn(Name='clear', DataType=bool,
                  Description="In case that the metadata already exists on "
                  "the database, remove the old one before the new one "
                  "is added",
                  Required=False, Default=False)
    ])

    def run(self, **kwargs):
        # Get parameters
        sample_template = kwargs['sample_template']
        study_id = kwargs['study_id']
        clear = kwargs['clear']

        if clear:
            SampleTemplate.delete(study_id)

        sample_temp = SampleTemplate.create(sample_template, study_id)

        return {'sample_template': sample_temp}

CommandConstructor = SampleTemplateAdder
