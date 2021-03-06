# Copyright (c) 2009-2021 The Regents of the University of Michigan
# This file is part of the HOOMD-blue project, released under the BSD 3-Clause License.

R""" Write system configurations to files.

Commands in the dump package write the system state out to a file every
*period* time steps. Check the documentation for details on which file format
each command writes.
"""

from collections import namedtuple
from hoomd import _hoomd
from hoomd.util import dict_flatten, array_to_strings
from hoomd.typeconverter import OnlyFrom
from hoomd.filter import ParticleFilter, All
from hoomd.parameterdicts import ParameterDict
from hoomd.logging import Logger, TypeFlags
from hoomd.operation import Analyzer
import numpy as np
import hoomd
import json
import os


class getar(hoomd.analyze._analyzer):
    """Analyzer for dumping system properties to a getar file at intervals.

    Getar files are a simple interface on top of archive formats (such
    as zip and tar) for storing trajectory data efficiently. A more
    thorough description of the format and a description of a python
    API to read and write these files is available at `the libgetar
    documentation <http://libgetar.readthedocs.io>`_.

    Properties to dump can be given either as a
    :py:class:`getar.DumpProp` object or a name. Supported property
    names are specified in the Supported Property Table in
    :py:class:``init.read_getar``.

    Files can be opened in write, append, or one-shot mode. Write mode
    overwrites files with the same name, while append mode adds to
    them. One-shot mode is intended for restorable system backups and
    is described below.

    **One-shot mode**

    In one-shot mode, activated by passing mode='1' to the getar
    constructor, properties are written to a temporary file, which
    then overwrites the file with the given filename. In this way, the
    file with the given filename should always have the most recent
    frame of successfully written data. This mode is designed for
    being able to dump restoration data often without wasting large
    amounts of space saving earlier data. Note that this
    create-and-overwrite process can be stressful on filesystems,
    particularly lustre filesystems, and can get your account blocked
    on some supercomputer resources if overused.

    For convenience, you can also specify **composite properties**,
    which are expanded according to the table below.

    .. tabularcolumns:: |p{0.25 \textwidth}|p{0.75 \textwidth}|
    .. csv-table::
       :header: "Name", "Result"
       :widths: 1, 3

       "global_all", "box, dimensions"
       "angle_all", "angle_type_names, angle_tag, angle_type"
       "bond_all", "bond_type_names, bond_tag, bond_type"
       "dihedral_all", "dihedral_type_names, dihedral_tag, dihedral_type"
       "improper_all", "improper_type_names, improper_tag, improper_type"
       "particle_all", "angular_momentum, body, charge, diameter, image, mass, moment_inertia, orientation, position, type, type_names, velocity"
       "all", "particle_all, angle_all, bond_all, dihedral_all, improper_all, global_all"
       "viz_static", "type, type_names, dimensions"
       "viz_dynamic", "position, box"
       "viz_all", "viz_static, viz_dynamic"
       "viz_aniso_dynamic", "viz_dynamic, orientation"
       "viz_aniso_all", "viz_static, viz_aniso_dynamic"

    **Particle-related metadata**

    Metadata about particle shape (for later visualization or use in
    restartable scripts) can be stored in a simple form through
    ``writeJSON``, which encodes JSON records
    as strings and stores them inside the dump file. Currently,
    classes inside :py:mod:`hoomd.dem` and :py:mod:`hoomd.hpmc` are
    equipped with `get_type_shapes()` methods which can provide
    per-particle-type shape information as a list.

    Example::

        dump = hoomd.dump.getar.simple('dump.sqlite', 1e3,
            static=['viz_static'],
            dynamic=['viz_aniso_dynamic'])

        dem_wca = hoomd.dem.WCA(nlist, radius=0.5)
        dem_wca.setParams('A', vertices=vertices, faces=faces)
        dump.writeJSON('type_shapes.json', dem_wca.get_type_shapes())

        mc = hpmc.integrate.ConvexPolygon(seed=415236)
        mc.shape_param.set('A', vertices=[(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)])
        dump.writeJSON('type_shapes.json', mc.get_type_shapes(), dynamic=True)

    """

    class DumpProp(namedtuple('DumpProp', ['name', 'highPrecision', 'compression'])):
        """Simple, internal, read-only namedtuple wrapper for specifying how
        getar properties will be dumped"""

        def __new__(self, name, highPrecision=False,
                     compression=_hoomd.GetarCompression.FastCompress):
            """Initialize a property dump description tuple.

            :param name: property name (string; see `Supported Property Table`_)
            :param highPrecision: if True, try to save this data in high-precision
            :param compression: one of `hoomd.dump.getar.Compression.{NoCompress, FastCompress, MediumCompress, SlowCompress`}.
            """
            return super(getar.DumpProp, self).__new__(
                self, name=name, highPrecision=highPrecision,
                compression=compression);

    Compression = _hoomd.GetarCompression;

    dump_modes = {'w': _hoomd.GetarDumpMode.Overwrite,
                  'a': _hoomd.GetarDumpMode.Append,
                  '1': _hoomd.GetarDumpMode.OneShot};

    substitutions = {
        'all': ['particle_all', 'angle_all', 'bond_all',
                'dihedral_all', 'improper_all', 'global_all'],
        'particle_all':
            ['angular_momentum', 'body', 'charge', 'diameter', 'image', 'mass', 'moment_inertia',
             'orientation', 'position', 'type', 'type_names', 'velocity'],
        'angle_all': ['angle_type_names', 'angle_tag', 'angle_type'],
        'bond_all': ['bond_type_names', 'bond_tag', 'bond_type'],
        'dihedral_all': ['dihedral_type_names', 'dihedral_tag', 'dihedral_type'],
        'improper_all': ['improper_type_names', 'improper_tag', 'improper_type'],
        'global_all': ['box', 'dimensions'],
        'viz_dynamic': ['position', 'box'],
        'viz_static': ['type', 'type_names', 'dimensions'],
        'viz_all': ['viz_static', 'viz_dynamic'],
        'viz_aniso_dynamic': ['viz_dynamic', 'orientation'],
        'viz_aniso_all': ['viz_static', 'viz_aniso_dynamic']};

    # List of properties we know how to dump and their enums
    known_properties = {'angle_type_names': _hoomd.GetarProperty.AngleNames,
                        'angle_tag': _hoomd.GetarProperty.AngleTags,
                        'angle_type': _hoomd.GetarProperty.AngleTypes,
                        'angular_momentum': _hoomd.GetarProperty.AngularMomentum,
                        'body': _hoomd.GetarProperty.Body,
                        'bond_type_names': _hoomd.GetarProperty.BondNames,
                        'bond_tag': _hoomd.GetarProperty.BondTags,
                        'bond_type': _hoomd.GetarProperty.BondTypes,
                        'box': _hoomd.GetarProperty.Box,
                        'charge': _hoomd.GetarProperty.Charge,
                        'diameter': _hoomd.GetarProperty.Diameter,
                        'dihedral_type_names': _hoomd.GetarProperty.DihedralNames,
                        'dihedral_tag': _hoomd.GetarProperty.DihedralTags,
                        'dihedral_type': _hoomd.GetarProperty.DihedralTypes,
                        'dimensions': _hoomd.GetarProperty.Dimensions,
                        'image': _hoomd.GetarProperty.Image,
                        'improper_type_names': _hoomd.GetarProperty.ImproperNames,
                        'improper_tag': _hoomd.GetarProperty.ImproperTags,
                        'improper_type': _hoomd.GetarProperty.ImproperTypes,
                        'mass': _hoomd.GetarProperty.Mass,
                        'moment_inertia': _hoomd.GetarProperty.MomentInertia,
                        'orientation': _hoomd.GetarProperty.Orientation,
                        'position': _hoomd.GetarProperty.Position,
                        'potential_energy': _hoomd.GetarProperty.PotentialEnergy,
                        'type': _hoomd.GetarProperty.Type,
                        'type_names': _hoomd.GetarProperty.TypeNames,
                        'velocity': _hoomd.GetarProperty.Velocity,
                        'virial': _hoomd.GetarProperty.Virial};

    # List of properties we know how to dump and their enums
    known_resolutions = {'angle_type_names': _hoomd.GetarResolution.Text,
                         'angle_tag': _hoomd.GetarResolution.Individual,
                         'angle_type': _hoomd.GetarResolution.Individual,
                         'angular_momentum': _hoomd.GetarResolution.Individual,
                         'body': _hoomd.GetarResolution.Individual,
                         'bond_type_names': _hoomd.GetarResolution.Text,
                         'bond_tag': _hoomd.GetarResolution.Individual,
                         'bond_type': _hoomd.GetarResolution.Individual,
                         'box': _hoomd.GetarResolution.Uniform,
                         'charge': _hoomd.GetarResolution.Individual,
                         'diameter': _hoomd.GetarResolution.Individual,
                         'dihedral_type_names': _hoomd.GetarResolution.Text,
                         'dihedral_tag': _hoomd.GetarResolution.Individual,
                         'dihedral_type': _hoomd.GetarResolution.Individual,
                         'dimensions': _hoomd.GetarResolution.Uniform,
                         'image': _hoomd.GetarResolution.Individual,
                         'improper_type_names': _hoomd.GetarResolution.Text,
                         'improper_tag': _hoomd.GetarResolution.Individual,
                         'improper_type': _hoomd.GetarResolution.Individual,
                         'mass': _hoomd.GetarResolution.Individual,
                         'moment_inertia': _hoomd.GetarResolution.Individual,
                         'orientation': _hoomd.GetarResolution.Individual,
                         'position': _hoomd.GetarResolution.Individual,
                         'potential_energy': _hoomd.GetarResolution.Individual,
                         'type': _hoomd.GetarResolution.Individual,
                         'type_names': _hoomd.GetarResolution.Text,
                         'velocity': _hoomd.GetarResolution.Individual,
                         'virial': _hoomd.GetarResolution.Individual};

    # List of properties which can't run in MPI mode
    bad_mpi_properties = ['potential_energy', 'virial'];

    def _getStatic(self, val):
        """Helper method to parse a static property specification element"""
        if type(val) == type(''):
            return self.DumpProp(name=val);
        else:
            return val;

    def _expandNames(self, vals):
        result = [];
        for val in vals:
            val = self._getStatic(val);
            if val.name in self.substitutions:
                subs = [self.DumpProp(name, val.highPrecision, val.compression) for name in
                        self.substitutions[val.name]];
                result.extend(self._expandNames(subs));
            else:
                result.append(val);

        return result;

    def __init__(self, filename, mode='w', static=[], dynamic={}, _register=True):
        """Initialize a getar dumper. Creates or appends an archive at the given file
        location according to the mode and prepares to dump the given
        sets of properties.

        Args:
            filename (str): Name of the file to open
            mode (str): Run mode; see mode list below.
            static (list): List of static properties to dump immediately
            dynamic (dict): Dictionary of {prop: period} periodic dumps
            _register (bool): If True, register as a hoomd analyzer (internal)

        Note that zip32-format archives can not be appended to at the
        moment; for details and solutions, see the libgetar
        documentation, section "Zip vs. Zip64." The gtar.fix module was
        explicitly made for this purpose, but be careful not to call it
        from within a running GPU HOOMD simulation due to strangeness in
        the CUDA driver.

        Valid mode arguments:

        * 'w': Write, and overwrite if file exists
        * 'a': Write, and append if file exists
        * '1': One-shot mode: keep only one frame of data. For details on one-shot mode, see the "One-shot mode" section of :py:class:`getar`.

        Property specifications can be either a property name (as a string) or
        :py:class:`DumpProp` objects if you desire greater control over how the
        property will be dumped.

        Example::

            # detailed API; see `dump.getar.simple` for simpler wrappers
            zip = dump.getar('dump.zip', static=['types'],
                      dynamic={'orientation': 10000,
                               'velocity': 5000,
                               dump.getar.DumpProp('position', highPrecision=True): 10000})

        """

        self._static = self._expandNames(static);
        self._dynamic = {};

        for key in dynamic:
            period = dynamic[key];
            for prop in self._expandNames([key]):
                self._dynamic[prop] = period;

        if _register:
            hoomd.analyze._analyzer.__init__(self);
            self.analyzer_name = "dump.getar%d" % (hoomd.analyze._analyzer.cur_id - 1);

        for val in self._static:
            if prop.name not in self.known_properties:
                raise RuntimeError('Unknown static property in dump.getar: {}'.format(val));

        for val in self._dynamic:
            if val.name not in self.known_properties:
                raise RuntimeError('Unknown dynamic property in dump.getar: {}'.format(val));

        try:
            dumpMode = self.dump_modes[mode];
        except KeyError:
            raise RuntimeError('Unknown open mode: {}'.format(mode));

        if dumpMode == self.dump_modes['a'] and not os.path.isfile(filename):
            dumpMode = self.dump_modes['w'];

        self.cpp_analyzer = _hoomd.GetarDumpWriter(hoomd.context.current.system_definition,
                                                filename, dumpMode,
                                                hoomd.context.current.system.getCurrentTimeStep());

        for val in set(self._static):
            prop = self._getStatic(val);
            if hoomd.context.current.device.comm.num_ranks > 1 and prop.name in self.bad_mpi_properties:
                raise RuntimeError(('dump.getar: Can\'t dump property {} '
                                    'with MPI!').format(prop.name));
            else:
                self.cpp_analyzer.setPeriod(self.known_properties[prop.name],
                                            self.known_resolutions[prop.name],
                                            _hoomd.GetarBehavior.Constant,
                                            prop.highPrecision, prop.compression, 0);

        for prop in self._dynamic:
            try:
                if hoomd.context.current.device.comm.num_ranks > 1 and prop.name in self.bad_mpi_properties:
                    raise RuntimeError(('dump.getar: Can\'t dump property {} '
                                        'with MPI!').format(prop.name));
                else:
                    for period in self._dynamic[prop]:
                        self.cpp_analyzer.setPeriod(self.known_properties[prop.name],
                                                    self.known_resolutions[prop.name],
                                                    _hoomd.GetarBehavior.Discrete,
                                                    prop.highPrecision, prop.compression,
                                                    int(period));
            except TypeError: # We got a single value, not an iterable
                if hoomd.context.current.device.comm.num_ranks > 1 and prop.name in self.bad_mpi_properties:
                    raise RuntimeError(('dump.getar: Can\'t dump property {} '
                                        'with MPI!').format(prop.name));
                else:
                    self.cpp_analyzer.setPeriod(self.known_properties[prop.name],
                                                self.known_resolutions[prop.name],
                                                _hoomd.GetarBehavior.Discrete,
                                                prop.highPrecision, prop.compression,
                                                int(self._dynamic[prop]));

        if _register:
            self.setupAnalyzer(int(self.cpp_analyzer.getPeriod()));

    def writeJSON(self, name, contents, dynamic=True):
        """Encodes the given JSON-encodable object as a string and writes it
        (immediately) as a quantity with the given name. If dynamic is
        True, writes the record as a dynamic record with the current
        timestep.

        Args:
            name (str): Name of the record to save
            contents (str): Any datatype encodable by the :py:mod:`json` module
            dynamic (bool): If True, dump a dynamic quantity with the current timestep; otherwise, dump a static quantity

        Example::

            dump = hoomd.dump.getar.simple('dump.sqlite', 1e3,
                static=['viz_static'], dynamic=['viz_dynamic'])
            dump.writeJSON('params.json', dict(temperature=temperature, pressure=pressure))
        """
        if dynamic:
            timestep = hoomd.context.current.system.getCurrentTimeStep()
        else:
            timestep = -1

        self.cpp_analyzer.writeStr(name, json.dumps(contents), timestep)

    @classmethod
    def simple(cls, filename, period, mode='w', static=[], dynamic=[], high_precision=False):
        """Create a :py:class:`getar` dump object with a simpler interface.

        Static properties will be dumped once immediately, and dynamic
        properties will be dumped every `period` steps. For detailed
        explanation of arguments, see :py:class:`getar`.

        Args:
            filename (str): Name of the file to open
            period (int): Period to dump the given dynamic properties with
            mode (str): Run mode; see mode list in :py:class:`getar`.
            static (list): List of static properties to dump immediately
            dynamic (list): List of properties to dump every `period` steps
            high_precision (bool): If True, dump precision properties

        Example::

            # for later visualization of anisotropic systems
            zip2 = hoomd.dump.getar.simple(
                 'dump.sqlite', 100000, 'a', static=['viz_static'], dynamic=['viz_aniso_dynamic'])
            # as backup to restore from later
            backup = hoomd.dump.getar.simple(
                'backup.tar', 10000, '1', static=['viz_static'], dynamic=['viz_aniso_dynamic'])

        """
        dynamicDict = {cls.DumpProp(name, highPrecision=high_precision): period for name in dynamic};
        return cls(filename=filename, mode=mode, static=static, dynamic=dynamicDict);

    @classmethod
    def immediate(cls, filename, static, dynamic):
        """Immediately dump the given static and dynamic properties to the given filename.

        For detailed explanation of arguments, see :py:class:`getar`.

        Example::

            hoomd.dump.getar.immediate(
                'snapshot.tar', static=['viz_static'], dynamic=['viz_dynamic'])

        """
        dumper = getar(filename, 'w', static, {key: 1 for key in dynamic}, _register=False);
        dumper.cpp_analyzer.analyze(hoomd.context.current.system.getCurrentTimeStep());
        dumper.close();
        del dumper.cpp_analyzer;

    def close(self):
        """Closes the trajectory if it is open. Finalizes any IO beforehand."""
        self.cpp_analyzer.close();
