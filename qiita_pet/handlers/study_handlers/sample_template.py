# -----------------------------------------------------------------------------
# Copyright (c) 2014--, The Qiita Development Team.
#
# Distributed under the terms of the BSD 3-clause License.
#
# The full license is in the file LICENSE, distributed with this software.
# -----------------------------------------------------------------------------

from os.path import basename
from json import loads, dumps

from tornado.web import authenticated, HTTPError
from tornado.escape import url_escape

from qiita_core.qiita_settings import r_client
from qiita_pet.handlers.base_handlers import BaseHandler
from qiita_db.util import get_files_from_uploads_folders
from qiita_db.study import Study
from qiita_db.metadata_template.sample_template import SampleTemplate
from qiita_db.metadata_template.util import looks_like_qiime_mapping_file
from qiita_db.software import Software, Parameters
from qiita_db.processing_job import ProcessingJob
from qiita_db.exceptions import QiitaDBUnknownIDError

from qiita_pet.handlers.api_proxy import (
    sample_template_summary_get_req,
    sample_template_post_req, sample_template_put_req,
    sample_template_delete_req, sample_template_filepaths_get_req,
    data_types_get_req, sample_template_samples_get_req,
    prep_template_samples_get_req, study_prep_get_req,
    sample_template_meta_cats_get_req, sample_template_category_get_req,
    sample_template_patch_request, get_sample_template_processing_status,
    check_fp)


SAMPLE_TEMPLATE_KEY_FORMAT = 'sample_template_%s'


def _check_study_access(study_id, user):
    """Raises an error if the given user doesn't have access to the study

    Parameters
    ----------
    study_id : int
        The study id
    user : qiita_db.user.User
        The user trying to access the study

    Raises
    ------
    HTTPError
        404 if the study does not exist
        403 if the user does not have access to the study
    """
    try:
        study = Study(int(study_id))
    except QiitaDBUnknownIDError:
        raise HTTPError(404, 'Study does not exist')
    if not study.has_access(user):
        raise HTTPError(403, 'User does not have access to study')


def sample_template_handler_post_request(study_id, user, filepath,
                                         data_type=None):
    """Creates a new sample template

    Parameters
    ----------
    study_id: int
        The study to add the sample information
    user: qiita_db.user import User
        The user performing the request
    filepath: str
        The path to the sample template file
    data_type: str, optional
        If filepath is a QIIME mapping file, the data type of the prep
        information file

    Returns
    -------
    dict of {'job': str}
        job: the id of the job adding the sample information to the study

    Raises
    ------
    HTTPError
        404 if the filepath doesn't exist
    """
    # Check if the current user has access to the study
    _check_study_access(study_id, user)

    # Check if the file exists
    fp_rsp = check_fp(study_id, filepath)
    if fp_rsp['status'] != 'success':
        raise HTTPError(404, 'Filepath not found')
    filepath = fp_rsp['file']

    is_mapping_file = looks_like_qiime_mapping_file(filepath)
    if is_mapping_file and not data_type:
        raise HTTPError(400, 'Please, choose a data type if uploading a '
                             'QIIME mapping file')

    qiita_plugin = Software.from_name_and_version('Qiita', 'alpha')
    cmd = qiita_plugin.get_command('create_sample_template')
    params = Parameters.load(
        cmd, values_dict={'fp': filepath, 'study_id': study_id,
                          'is_mapping_file': is_mapping_file,
                          'data_type': data_type})
    job = ProcessingJob.create(user, params, True)
    r_client.set(SAMPLE_TEMPLATE_KEY_FORMAT % study_id,
                 dumps({'job_id': job.id}))
    job.submit()
    return {'job': job.id}


class SampleTemplateHandler(BaseHandler):
    @authenticated
    def get(self):
        study_id = self.get_argument('study_id')

        # Check if the current user has access to the sample template
        _check_study_access(study_id, self.current_user)

        self.render('study_ajax/sample_summary.html', study_id=study_id)

    @authenticated
    def post(self):
        study_id = int(self.get_argument('study_id'))
        filepath = self.get_argument('filepath')
        data_type = self.get_argument('data_type')

        self.write(sample_template_handler_post_request(
            study_id, self.current_user, filepath, data_type=data_type))


def sample_template_overview_handler_get_request(study_id, user):
    # Check if the current user has access to the sample template
    _check_study_access(study_id, user)

    # Check if the sample template exists
    exists = SampleTemplate.exists(study_id)

    # The following information should always be provided:
    # The files that have been uploaded to the system and can be a
    # sample template file
    files = [f for _, f in get_files_from_uploads_folders(study_id)
             if f.endswith(('txt', 'tsv'))]
    # If there is a job associated with the sample information, the job id
    job = None
    job_info = r_client.get(SAMPLE_TEMPLATE_KEY_FORMAT % study_id)
    if job_info:
        job = loads(job_info)['job_id']

    # Specific information if it exists or not:
    data_types = []
    if exists:
        # If it exists, provide some information about it
        pass
    else:
        # It doesn't exist, besides the uploaded_files, we also need to
        # provide the data_types in case the user upload a QIIME mapping
        # file
        data_types = sorted(data_types_get_req()['data_types'])

    return {'exists': exists,
            'uploaded_files': files,
            'data_types': data_types,
            'user_can_edit': Study(study_id).can_edit(user),
            'job': job}


class SampleTemplateOverviewHandler(BaseHandler):
    @authenticated
    def get(self):
        study_id = int(self.get_argument('study_id'))
        self.write(
            sample_template_overview_handler_get_request(
                study_id, self.current_user))


def _build_sample_summary(study_id, user_id):
    """Builds the initial table of samples associated with prep templates

    Parameters
    ----------
    study_id : int
        Study to get samples from
    user_id : str
        User requesting the information

    Returns
    -------
    columns : list of dict
        SlickGrid formatted list of columns
    samples_table : list of dict
        SlickGrid formatted table information
    """
    # Load all samples available into dictionary and set
    samps_table = {s: {'sample': s} for s in
                   sample_template_samples_get_req(
        study_id, user_id)['samples']}
    all_samps = set(samps_table.keys())
    columns = [{"id": "sample", "name": "Sample", "field": "sample",
                "width": 240, "sortable": False}]
    # Add one column per prep template highlighting what samples exist
    preps = study_prep_get_req(study_id, user_id)["info"]
    for dt in preps:
        for prep in preps[dt]:
            col_field = "prep%d" % prep["id"]
            col_name = "%s - %d" % (prep["name"], prep["id"])
            columns.append({"id": col_field,
                            "name": col_name,
                            "field": col_field,
                            "sortable": False,
                            "width": 240})

            prep_samples = prep_template_samples_get_req(
                prep['id'], user_id)['samples']
            # Empty cell for samples not in the prep template
            for s in all_samps.difference(prep_samples):
                samps_table[s][col_field] = ""
            # X in cell for samples in the prep template
            for s in all_samps.intersection(prep_samples):
                samps_table[s][col_field] = "X"

    return columns, samps_table.values()


class SampleTemplateAJAX(BaseHandler):
    @authenticated
    def get(self):
        """Send formatted summary page of sample template"""
        study_id = self.get_argument('study_id')
        row_id = self.get_argument('row_id', '0')

        files = [f for _, f in get_files_from_uploads_folders(study_id)
                 if f.endswith(('txt', 'tsv'))]
        data_types = sorted(data_types_get_req()['data_types'])

        download_id = None
        download = sample_template_filepaths_get_req(
            study_id, self.current_user.id)
        if download['status'] == 'success':
            download_id = download['filepaths'].pop(0)[0]

        stats = sample_template_summary_get_req(study_id, self.current_user.id)
        if stats['status'] != 'success':
            if 'does not exist' in stats['message']:
                raise HTTPError(404, stats['message'])
            if 'User does not have access to study' in stats['message']:
                raise HTTPError(403, stats['message'])

        stats['download_id'] = download_id
        stats['files'] = files
        stats['study_id'] = study_id
        stats['data_types'] = data_types
        stats['row_id'] = row_id
        if 'filepaths' in download:
            stats['other_filepaths'] = [
                basename(fp) for _, fp in download['filepaths']]
        else:
            stats['other_filepaths'] = []
        # URL encode in case message has javascript-breaking characters in it
        stats['alert_message'] = url_escape(stats['alert_message'])
        self.render('study_ajax/sample_summary.html', **stats)

    @authenticated
    def post(self):
        """Edit/delete/create sample template"""
        action = self.get_argument('action')
        study_id = self.get_argument('study_id')
        if action == 'create':
            filepath = self.get_argument('filepath')
            data_type = self.get_argument('data_type')
            result = sample_template_post_req(study_id, self.current_user.id,
                                              data_type, filepath)
        elif action == 'update':
            filepath = self.get_argument('filepath')
            result = sample_template_put_req(study_id, self.current_user.id,
                                             filepath)
        elif action == 'delete':
            result = sample_template_delete_req(study_id, self.current_user.id)
        else:
            raise HTTPError(400, 'Unknown sample information action: %s'
                            % action)
        self.write(result)

    @authenticated
    def patch(self):
        """Patches a sample template in the system

        Follows the JSON PATCH specification:
        https://tools.ietf.org/html/rfc6902
        """
        req_op = self.get_argument('op')
        req_path = self.get_argument('path')
        req_value = self.get_argument('value', None)
        req_from = self.get_argument('from', None)

        response = sample_template_patch_request(
            self.current_user.id, req_op, req_path, req_value, req_from)

        self.write(response)


class SampleAJAX(BaseHandler):
    @authenticated
    def get(self):
        """Show the sample summary page"""
        study_id = self.get_argument('study_id')

        res = sample_template_meta_cats_get_req(
            int(study_id), self.current_user.id)

        if res['status'] == 'error':
            if 'does not exist' in res['message']:
                raise HTTPError(404, res['message'])
            elif 'User does not have access to study' in res['message']:
                raise HTTPError(403, res['message'])
            else:
                raise HTTPError(500, res['message'])

        meta_cats = res['categories']
        cols, samps_table = _build_sample_summary(study_id,
                                                  self.current_user.id)
        _, alert_type, alert_msg = get_sample_template_processing_status(
            study_id)
        self.render('study_ajax/sample_prep_summary.html',
                    table=samps_table, cols=cols, meta_available=meta_cats,
                    study_id=study_id, alert_type=alert_type,
                    alert_message=alert_msg)

    @authenticated
    def post(self):
        study_id = int(self.get_argument('study_id'))
        meta_col = self.get_argument('meta_col')
        values = sample_template_category_get_req(meta_col, study_id,
                                                  self.current_user.id)
        if values['status'] != 'success':
            self.write(values)
        else:
            self.write({'status': 'success',
                        'message': '',
                        'values': values['values']
                        })
