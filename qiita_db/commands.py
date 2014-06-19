from functools import partial
try:
    # Python 2
    from ConfigParser import ConfigParser
except ImportError:
    # Python 3
    from configparser import ConfigParser

from .study import Study, StudyPerson
from .user import User
from .util import get_filetypes, get_filepath_types
from .data import RawData


def make_study_from_cmd(owner, title, info):

    # Parse the configuration file
    config = ConfigParser()
    config.readfp(info)

    optional = dict(config.items('optional'))
    get_optional = lambda name: optional.get(name, None)
    get_required = partial(config.get, 'required')
    required_fields = ['timeseries_type_id', 'mixs_compliant',
                       'number_samples_collected', 'number_samples_promised',
                       'portal_type_id', 'reprocess', 'study_alias',
                       'study_description', 'study_abstract',
                       'metadata_complete']
    optional_fields = ['funding', 'most_recent_contact', 'spatial_series',
                       'vamps_id']
    infodict = {}
    for value in required_fields:
        infodict[value] = get_required(value)

    for value in optional_fields:
        optvalue = get_optional(value)
        if optvalue is not None:
            infodict[value] = optvalue

    emp_person_name_email = get_optional('emp_person_name')
    if emp_person_name_email is not None:
        emp_name, emp_email = emp_person_name_email.split(',')
        infodict['emp_person_id'] = StudyPerson.create(emp_name.strip(),
                                                       emp_email.strip())
    lab_name_email = get_optional('lab_person')
    if lab_name_email is not None:
        lab_name, lab_email = lab_name_email.split(',')
        infodict['lab_person_id'] = StudyPerson.create(lab_name.strip(),
                                                       lab_email.strip())
    pi_name_email = get_required('principal_investigator')
    pi_name, pi_email = pi_name_email.split(',')
    infodict['principal_investigator_id'] = StudyPerson.create(
        pi_name.strip(), pi_email.strip())
    # this will eventually change to using the Experimental Factory Ontolgoy
    # names
    efo_ids = get_required('efo_ids')
    efo_ids = [x.strip() for x in efo_ids.split(',')]

    Study.create(User(owner), title, efo_ids, infodict)


def load_raw_data_cmd(filepaths, filepath_types, filetype, study_ids):
    """Add new raw data by populating the relevant tables

    Parameters
    ----------
    filepaths : iterable of str
    filepath_types : iterable of str
    filetype : str
    study_ids : iterable of int
    """
    if len(filepaths) != len(filepath_types):
        raise ValueError("Please pass exactly one filepath_type for each "
                         "and every filepath")

    filetypes_dict = get_filetypes()
    filetype_id = filetypes_dict[filetype]

    filepath_types_dict = get_filepath_types()
    filepath_types = [filepath_types_dict[x] for x in filepath_types]

    studies = [Study(x) for x in study_ids]

    return RawData.create(filetype_id, zip(filepaths, filepath_types), studies)
