# -----------------------------------------------------------------------------
# Copyright (c) 2014--, The Qiita Development Team.
#
# Distributed under the terms of the BSD 3-clause License.
#
# The full license is in the file LICENSE, distributed with this software.
# -----------------------------------------------------------------------------


from tornado.web import authenticated

from qiita_ware.toolbox.strided_state_unifrac import run_strided_state_unifrac
from qiita_pet.handlers.base_handlers import BaseHandler


class StridedStateUnifracHandler(BaseHandler):
    @authenticated
    def get(self):
        self.render('toolbox/strided_state_unifrac/ssu.html')

    @authenticated
    def post(self):
        # The format of each of the files entry is a list of dictionaries
        # to actually get the contents of the file we need to access to the
        # first element of the list and the 'body' key
        cat_map_f = self.request.files['category-map-file'][0]['body']
        sample_id_f = self.request.files['sample-id-file'][0]['body']
        tree = self.get_argument('tree-sel')
        tree_f = (self.request.files['tree-file'][0]['body']
                  if tree == 'Other' else None)
        print cat_map_f
        print sample_id_f
        print tree
        print tree_f
        # cat_map_f = self.get_argument('category-map-file')
        # tree_f = self.get_argument('tree-file')
        #
        # print sample_id_f, cat_map_f, tree_f
