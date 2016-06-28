# -----------------------------------------------------------------------------
# Copyright (c) 2014--, The Qiita Development Team.
#
# Distributed under the terms of the BSD 3-clause License.
#
# The full license is in the file LICENSE, distributed with this software.
# -----------------------------------------------------------------------------

from tornado.web import HTTPError
from collections import defaultdict

import qiita_db as qdb
from .oauth2 import OauthBaseHandler, authenticate_oauth


def _get_prep_template(p_id):
    """Returns the prep template with the given id if it exists

    Parameters
    ----------
    p_id : str
        The prep template id

    Returns
    -------
    qiita_db.metadata_template.prep_template.PrepTemplate
        The requested prep template

    Raises
    ------
    HTTPError
        If the prep template does not exist, with error code 404
        If there is a problem instantiating the template, with error code 500
    """
    try:
        p_id = int(p_id)
        pt = qdb.metadata_template.prep_template.PrepTemplate(p_id)
    except qdb.exceptions.QiitaDBUnknownIDError:
        raise HTTPError(404)
    except Exception as e:
        raise HTTPError(500, 'Error instantiating prep template %s: %s'
                             % (p_id, str(e)))

    return pt


class PrepTemplateDataHandler(OauthBaseHandler):
    @authenticate_oauth
    def get(self, prep_id):
        """Retrieves the prep contents

        Parameters
        ----------
        prep_id : str
            The id of the prep template whose information is being retrieved

        Returns
        -------
        dict
            The contents of the prep information keyed by sample id
        """
        with qdb.sql_connection.TRN:
            pt = _get_prep_template(prep_id)
            response = {'data': pt.to_dataframe().to_dict(orient='index')}

        self.write(response)
