# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the PyMVPA package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Converter for PyMVPA object to HDF5 format."""

__docformat__ = 'restructuredtext'

import numpy as N
import h5py

#
# TODO: check for recursions!!!
#
def hdf2obj(hdf):
    # already at the level of real data
    if isinstance(hdf, h5py.Dataset):
        if not len(hdf.shape):
            # extract the scalar from the 0D array
            return hdf[()]
        else:
            # read array-dataset into an array
            value = N.empty(hdf.shape, hdf.dtype)
            hdf.read_direct(value)
            return value
    else:
        # check if we have a class instance definition here
        if not ('__class__' in hdf.attrs or '__reconstructor__' in hdf.attrs):
            raise RuntimeError("Found hdf group without class instance "
                    "information (group: %s). This is a conceptual bug in the "
                    "parser or the hdf writer. Please report." % hdf.name)

        if '__reconstructor__' in hdf.attrs:
            # we found something that has some special idea about how it wants
            # to be reconstructed
            # look for arguments for that reconstructor
            recon = hdf.attrs['__reconstructor__']
            mod = hdf.attrs['__reconstructor_module__']
            if mod == '__builtin__':
                raise NotImplementedError(
                        "Built-in reconstructors are not supported (yet). "
                        "Got: '%s'." % recon)

            # turn names into definitions
            mod = __import__(mod, fromlist=[recon])
            recon = mod.__dict__[recon]

            if '__reconstructor_args__' in hdf:
                recon_args = _hdf_tupleitems_to_obj(hdf['__reconstructor_args__'])
            else:
                recon_args = ()

            # reconstruct
            obj = recon(*recon_args)

            # TODO Handle potentially avialable state settings
            return obj

        cls = hdf.attrs['__class__']
        mod = hdf.attrs['__module__']
        if not mod == '__builtin__':
            # some custom class is desired
            # import the module and the class
            mod = __import__(mod, fromlist=[cls])
            # get the class definition from the module dict
            cls = mod.__dict__[cls]

            # create the object
            if issubclass(cls, dict):
                obj = dict.__new__(cls)
                # insert the state of the object
                obj.__dict__.update(
                        _hdf_dictitems_to_obj(hdf, skip=['__items__']))
                # charge the dict itself
                obj.update(_hdf_dictitems_to_obj(hdf['__items__']))
                return obj
            else:
                obj = object.__new__(cls)
                # insert the state of the object
                obj.__dict__.update(_hdf_dictitems_to_obj(hdf))
                return obj

        else:
            # built in type (there should be only 'list', 'dict' and 'None'
            # that would not be in a Dataset
            if cls == 'NoneType':
                return None
            elif cls == 'tuple':
                return _hdf_tupleitems_to_obj(hdf['__items__'])
            elif cls == 'list':
                return _hdf_listitems_to_obj(hdf['__items__'])
            elif cls == 'dict':
                return _hdf_dictitems_to_obj(hdf['__items__'])
            else:
                raise RuntimeError("Found hdf group with a builtin type "
                        "that is not handled by the parser (group: %s). This "
                        "is a conceptual bug in the parser. Please report."
                        % hdf.name)


def _hdf_dictitems_to_obj(hdf, skip=None):
    if skip is None:
        skip = []
    return dict([(item, hdf2obj(hdf[item]))
                    for item in hdf
                        if not item in skip])


def _hdf_listitems_to_obj(hdf):
    return [hdf2obj(hdf[str(i)]) for i in xrange(len(hdf))]


def _hdf_tupleitems_to_obj(hdf):
    return tuple(_hdf_listitems_to_obj(hdf))

#
# TODO: check for recursions!!!
#
def obj2hdf(hdf, obj, name, **kwargs):
    # if it is somthing that can go directly into HDF5, put it there
    # right away
    if N.isscalar(obj) or isinstance(obj, N.ndarray):
        hdf.create_dataset(name, None, None, obj, **kwargs)
        return

    # complex objects
    grp = hdf.create_group(name)

    # try disassembling the object
    try:
        pieces = obj.__reduce__()
    except TypeError:
        # probably a container
        pieces = None

    # common container handling, either __reduce__ was not possible
    # or it was the default implementation
    if pieces is None or pieces[0].__name__ == '_reconstructor':
        # store class info (fully-qualified)
        grp.attrs.create('__class__', obj.__class__.__name__)
        grp.attrs.create('__module__', obj.__class__.__module__)
        if isinstance(obj, list) or isinstance(obj, tuple):
            items = grp.create_group('__items__')
            for i, item in enumerate(obj):
                obj2hdf(items, item, str(i), **kwargs)
        elif isinstance(obj, dict):
            items = grp.create_group('__items__')
            for key in obj:
                obj2hdf(items, obj[key], key, **kwargs)
        # pull all remaining data from the default __reduce__
        if not pieces is None and len(pieces) > 2:
            # there is something in the state
            state = pieces[2]
            # loop over all attributes and store them
            for attr in state:
                obj2hdf(grp, state[attr], attr, **kwargs)
        # for the default __reduce__ there is nothin else to do
        return
    else:
        # XXX handle custom reduce
        grp.attrs.create('__reconstructor__', pieces[0].__name__)
        grp.attrs.create('__reconstructor_module__', pieces[0].__module__)
        args = grp.create_group('__reconstructor_args__')
        for i, arg in enumerate(pieces[1]):
            obj2hdf(args, arg, str(i), **kwargs)
        return
