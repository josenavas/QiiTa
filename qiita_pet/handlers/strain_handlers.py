# -----------------------------------------------------------------------------
# Copyright (c) 2014--, The Qiita Development Team.
#
# Distributed under the terms of the BSD 3-clause License.
#
# The full license is in the file LICENSE, distributed with this software.
# -----------------------------------------------------------------------------

from __future__ import division
from os.path import exists, join

from tornado.web import authenticated, HTTPError
from wtforms import (Form, StringField, SelectField, DateTimeField,
                     TextAreaField, validators)

from qiita_db.study import Study
from qiita_db.metadata_template import SampleTemplate
from qiita_db.strain import Strain
from qiita_db.util import get_files_from_uploads_folders, get_mountpoint
from .base_handlers import BaseHandler


class StrainEditorForm(Form):
    r""""""
    unofficial_name = StringField('Unofficial name', [validators.Required()])
    sequence_fp = SelectField('Sequence file', [validators.Required()],
                              coerce=lambda x: x)
    sample_id = SelectField('Sample origin', coerce=lambda x: x)
    isolation_date = DateTimeField('Isolation date', [validators.Required()])
    isolation_description = TextAreaField('Isolation description',
                                          [validators.Required()])
    storage_conditions = SelectField('Storage conditions',
                                     [validators.Required()],
                                     coerce=lambda x: x)
    culture_collection = SelectField('Culture collection',
                                     [validators.Required()],
                                     coerce=lambda x: x)

    def __init__(self, study, **kwargs):
        super(StrainEditorForm, self).__init__(**kwargs)
        # Populate the sequence fp drop down
        self.sequence_fp.choices = [
            (fp, fp) for fp in get_files_from_uploads_folders(str(study.id))]
        # Populate the sample id drop down
        st = SampleTemplate(study.sample_template)
        self.sample_id.choices = [(sid, sid) for sid in st]
        # Populate the storage conditions drop down
        self.storage_conditions.choices = [
            (1, "-80C. 20% glycerol in mega medium"),
            (2, "-90C. 20% glycerol in mega medium")]
        # Populate the culture collection drop down
        self.culture_collection.choices = [('ATCC', 'ATCC')]


class CreateStrainHandler(BaseHandler):

    @authenticated
    def get(self, arguments):
        study_id = int(self.get_argument('study_id'))
        rd_tab = int(self.get_argument('rd_tab'))

        study = Study(study_id)
        creation_form = StrainEditorForm(study)

        self.render('edit_strain.html', user=self.current_user,
                    creation_form=creation_form, study_id=study_id,
                    rd_tab=rd_tab)

    @authenticated
    def post(self, arguments):
        study_id = int(self.request.arguments.pop("study_id")[0])
        study = Study(study_id)
        rd_tab = self.request.arguments.pop("rd_tab")[0]
        form_data = StrainEditorForm(study)
        form_data.process(data=self.request.arguments)

        _, base_fp = get_mountpoint("uploads")[0]
        sequence_fp = join(base_fp, str(study_id),
                           form_data.data['sequence_fp'][0])
        if not exists(sequence_fp):
            raise HTTPError(400, "This file doesn't exist: %s" % sequence_fp)

        the_strain = Strain.create(
            form_data.data['unofficial_name'][0],
            sequence_fp,
            form_data.data['sample_id'][0],
            form_data.data['isolation_date'][0],
            form_data.data['isolation_description'][0],
            form_data.data['storage_conditions'][0],
            form_data.data['culture_collection'][0])

        self.redirect('/study/description/%s' % study_id)


class CreateStrainAJAX(BaseHandler):
    @authenticated
    def get(self):
        strain_unofficial = self.get_argument('strain_unofficial', None)

        if strain_unofficial is None:
            self.write('False')
            return

        self.write('False' if Strain.exists(strain_unofficial) else 'True')
