# -----------------------------------------------------------------------------
# Copyright (c) 2014--, The Qiita Development Team.
#
# Distributed under the terms of the BSD 3-clause License.
#
# The full license is in the file LICENSE, distributed with this software.
# -----------------------------------------------------------------------------

from .strided_state_unifrac import StridedStateUnifracHandler

__all__ = []

ENDPOINTS = (
    (r"/toolbox/strided_state_unifrac/", StridedStateUnifracHandler), )
