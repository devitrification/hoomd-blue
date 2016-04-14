# -- start license --
# Highly Optimized Object-oriented Many-particle Dynamics -- Blue Edition
# (HOOMD-blue) Open Source Software License Copyright 2009-2016 The Regents of
# the University of Michigan All rights reserved.

# HOOMD-blue may contain modifications ("Contributions") provided, and to which
# copyright is held, by various Contributors who have granted The Regents of the
# University of Michigan the right to modify and/or distribute such Contributions.

# You may redistribute, use, and create derivate works of HOOMD-blue, in source
# and binary forms, provided you abide by the following conditions:

# * Redistributions of source code must retain the above copyright notice, this
# list of conditions, and the following disclaimer both in the code and
# prominently in any materials provided with the distribution.

# * Redistributions in binary form must reproduce the above copyright notice, this
# list of conditions, and the following disclaimer in the documentation and/or
# other materials provided with the distribution.

# * All publications and presentations based on HOOMD-blue, including any reports
# or published results obtained, in whole or in part, with HOOMD-blue, will
# acknowledge its use according to the terms posted at the time of submission on:
# http://codeblue.umich.edu/hoomd-blue/citations.html

# * Any electronic documents citing HOOMD-Blue will link to the HOOMD-Blue website:
# http://codeblue.umich.edu/hoomd-blue/

# * Apart from the above required attributions, neither the name of the copyright
# holder nor the names of HOOMD-blue's contributors may be used to endorse or
# promote products derived from this software without specific prior written
# permission.

# Disclaimer

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDER AND CONTRIBUTORS ``AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND/OR ANY
# WARRANTIES THAT THIS SOFTWARE IS FREE OF INFRINGEMENT ARE DISCLAIMED.

# IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
# INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# -- end license --

# Maintainer: joaander / All Developers are free to add commands for new features

from hoomd import _hoomd
import hoomd;

import math;
import sys;
import gc;
import os;
import re;
import platform;

## \package hoomd.init
# \brief Data initialization commands
#
# Commands in the init package initialize the particle system. Initialization via
# any of the commands here must be done before any other command in hoomd_script can
# be run.
#
# \sa \ref page_quick_start

## Tests if the system has been initialized
#
# Returns True if a previous init.create* or init.read* command has completed successfully and initialized the system.
# Returns False otherwise.
def is_initialized():
    if hoomd.context.current.system is None:
        return False;
    else:
        return True;

## Create an empty system
#
# \param N Number of particles to create
# \param box a data.boxdim object that defines the simulation box
# \param particle_types List of particle type names (must not be zero length)
# \param bond_types List of bond type names (may be zero length)
# \param angle_types List of angle type names (may be zero length)
# \param dihedral_types List of Dihedral type names (may be zero length)
# \param improper_types List of improper type names (may be zero length)
#
# \b Examples:
# \code
# system = init.create_empty(N=1000, box=data.boxdim(L=10)
# system = init.create_empty(N=64000, box=data.boxdim(L=1, dimensions=2, volume=1000), particle_types=['A', 'B'])
# system = init.create_empty(N=64000, box=data.boxdim(L=20), bond_types=['polymer'], dihedral_types=['dihedralA', 'dihedralB'], improper_types=['improperA', 'improperB', 'improperC'])
# \endcode
#
# After init.create_empty returns, the requested number of particles will have been created with
# <b> <i> DEFAULT VALUES</i> </b> and further initialization \b MUST be performed. See hoomd.data
# for full details on how such initialization can be performed.
#
# Specifically, all created particles will be:
# - At position 0,0,0
# - Have velocity 0,0,0
# - In box image 0,0,0
# - Have orientation 1,0,0,0
# - Have the type `particle_types[0]`
# - Have charge 0
# - Have a mass of 1.0
#
# The particle, bond, angle, dihedral, and improper types will be created and set to the names specified. Use these
# type names later in the job script to refer to particles (i.e. in lj.set_params)
#
# \note The resulting empty system must have its particles fully initialized via python code, \b BEFORE
# any other hoomd_script commands are executed. For example, if the pair.lj command were to be
# run before the initial particle positions were set, \b all particles would have position 0,0,0 and the memory
# initialized by the neighbor list would be so large that the memory allocation would fail.
#
# \warning create_empty() is deprecated. Use data.make_snapshot() and init.read_snapshot() instead. create_empty will be
#          removed in the next release of HOOMD-blue.
#
# \sa hoomd.data
def create_empty(N, box, particle_types=['A'], bond_types=[], angle_types=[], dihedral_types=[], improper_types=[]):
    hoomd.util.print_status_line();

    # check if initialization has already occurred
    if is_initialized():
        hoomd.context.msg.error("Cannot initialize more than once\n");
        raise RuntimeError('Error initializing');

    hoomd.context.msg.warning("init.create_empty() is deprecated. Use data.make_snapshot and init.read_snapshot instead\n");

    hoomd.context._verify_init();

    # create the empty system
    if not isinstance(box, hoomd.data.boxdim):
        hoomd.context.msg.error('box must be a data.boxdim object');
        raise TypeError('box must be a data.boxdim object');

    boxdim = box._getBoxDim();

    my_domain_decomposition = _create_domain_decomposition(boxdim);
    if my_domain_decomposition is not None:
        hoomd.context.current.system_definition = _hoomd.SystemDefinition(N,
                                                           boxdim,
                                                           len(particle_types),
                                                           len(bond_types),
                                                           len(angle_types),
                                                           len(dihedral_types),
                                                           len(improper_types),
                                                           hoomd.context.exec_conf,
                                                           my_domain_decomposition);
    else:
        hoomd.context.current.system_definition = _hoomd.SystemDefinition(N,
                                                           boxdim,
                                                           len(particle_types),
                                                           len(bond_types),
                                                           len(angle_types),
                                                           len(dihedral_types),
                                                           len(improper_types),
                                                           hoomd.context.exec_conf)

    hoomd.context.current.system_definition.setNDimensions(box.dimensions);

    # transfer names to C++
    for i,name in enumerate(particle_types):
        hoomd.context.current.system_definition.getParticleData().setTypeName(i,name);
    for i,name in enumerate(bond_types):
        hoomd.context.current.system_definition.getBondData().setTypeName(i,name);
    for i,name in enumerate(angle_types):
        hoomd.context.current.system_definition.getAngleData().setTypeName(i,name);
    for i,name in enumerate(dihedral_types):
        hoomd.context.current.system_definition.getDihedralData().setTypeName(i,name);
    for i,name in enumerate(improper_types):
        hoomd.context.current.system_definition.getImproperData().setTypeName(i,name);

    # initialize the system
    hoomd.context.current.system = _hoomd.System(hoomd.context.current.system_definition, 0);

    _perform_common_init_tasks();
    return hoomd.data.system_data(hoomd.context.current.system_definition);

## Reads initial system state from an XML file
#
# \param filename File to read
# \param restart If it exists, read \a restart instead of \a filename
# \param time_step (if specified) Time step number to use instead of the one stored in the XML file
# \param wrap_coordinates Wrap input coordinates back into the box
#
# \b Examples:
# \code
# init.read_xml(filename="data.xml")
# init.read_xml(filename="init.xml", restart="restart.xml")
# init.read_xml(filename="directory/data.xml")
# init.read_xml(filename="restart.xml", time_step=0)
# system = init.read_xml(filename="data.xml")
# \endcode
#
# All particles, bonds, etc...  are read from the given XML file,
# setting the initial condition of the simulation.
# After this command completes, the system is initialized allowing
# other commands in hoomd_script to be run. For more details
# on the file format read by this command, see \ref page_xml_file_format.
#
# For restartable jobs, specify the initial condition in \a filename and the restart file in \a restart.
# init.read_xml will read the restart file if it exists, otherwise it will read \a filename.
#
# All values are read in native units, see \ref page_units for more information.
#
# If \a time_step is specified, its value will be used as the initial time
# step of the simulation instead of the one read from the XML file.
#
# If \a wrap_coordinates is set to True, input coordinates will be wrapped
# into the box specified inside the XML file. If it is set to False, out-of-box
# coordinates will result in an error.
#
# The result of init.read_xml can be saved in a variable and later used to read and/or change particle properties
# later in the script. See hoomd.data for more information.
#
# \sa dump.xml
def read_xml(filename, restart = None, time_step = None, wrap_coordinates = False):
    hoomd.util.print_status_line();

    hoomd.context._verify_init();

    # check if initialization has already occured
    if is_initialized():
        hoomd.context.msg.error("Cannot initialize more than once\n");
        raise RuntimeError("Error reading XML file");

    filename_to_read = filename;
    if restart is not None:
        if os.path.isfile(restart):
            filename_to_read = restart;

    # read in the data
    initializer = _hoomd.HOOMDInitializer(hoomd.context.exec_conf,filename_to_read,wrap_coordinates);
    snapshot = initializer.getSnapshot()

    my_domain_decomposition = _create_domain_decomposition(snapshot._global_box);
    if my_domain_decomposition is not None:
        hoomd.context.current.system_definition = _hoomd.SystemDefinition(snapshot, hoomd.context.exec_conf, my_domain_decomposition);
    else:
        hoomd.context.current.system_definition = _hoomd.SystemDefinition(snapshot, hoomd.context.exec_conf);

    # initialize the system
    if time_step is None:
        hoomd.context.current.system = _hoomd.System(hoomd.context.current.system_definition, initializer.getTimeStep());
    else:
        hoomd.context.current.system = _hoomd.System(hoomd.context.current.system_definition, time_step);

    _perform_common_init_tasks();
    return hoomd.data.system_data(hoomd.context.current.system_definition);

## Generates N randomly positioned particles of the same type
#
# \param N Number of particles to create
# \param phi_p Packing fraction of particles in the simulation box (unitless)
# \param name Name of the particle type to create
# \param min_dist Minimum distance particles will be separated by (in distance units)
# \param box Simulation box dimensions (data.boxdim object)
# \param seed Random seed
# \param dimensions The number of dimensions in the simulation (2 or 3(default))
#
# Either \a phi_p or \a box must be specified. If \a phi_p is provided, it overrides the value of \a box.
#
# \b Examples:
# \code
# init.create_random(N=2400, phi_p=0.20)
# init.create_random(N=2400, phi_p=0.40, min_dist=0.5)
# system = init.create_random(N=2400, box=data.boxdim(L=20))
# \endcode
#
# \a N particles are randomly placed in the simulation box.
#
# When phi_p is set, the
# dimensions of the created box are such that the packing fraction
# of particles in the box is \a phi_p. The number density \e n
# is related to the packing fraction by \f$n = 2d/\pi \cdot \phi_P\f$,
# where d is the dimension, and assuming the particles have a radius of 0.5.
# All particles are created with the same type, given by \a name.
#
# The result of init.create_random can be saved in a variable and later used to read and/or change particle properties
# later in the script. See hoomd.data for more information.
#
def create_random(N, phi_p=None, name="A", min_dist=0.7, box=None, seed=1, dimensions=3):
    hoomd.util.print_status_line();

    hoomd.context._verify_init();

    # check if initialization has already occured
    if is_initialized():
        hoomd.context.msg.error("Cannot initialize more than once\n");
        raise RuntimeError("Error initializing");

    # check that dimensions are appropriate
    if dimensions not in (2,3):
        raise ValueError('dimensions must be 2 or 3')

    # abuse the polymer generator to generate single particles

    if phi_p is not None:
        # calculate the box size
        L = math.pow(math.pi/(2.0*dimensions)*N / phi_p, 1.0/dimensions);
        box = hoomd.data.boxdim(L=L, dimensions=dimensions);

    if box is None:
        raise RuntimeError('box or phi_p must be specified');

    if not isinstance(box, hoomd.data.boxdim):
        hoomd.context.msg.error('box must be a data.boxdim object');
        raise TypeError('box must be a data.boxdim object');

    # create the generator
    generator = _hoomd.RandomGenerator(hoomd.context.exec_conf, box._getBoxDim(), seed, box.dimensions);

    # build type list
    type_vector = _hoomd.std_vector_string();
    type_vector.append(name);

    # empty bond lists for single particles
    bond_ab = _hoomd.std_vector_uint();
    bond_type = _hoomd.std_vector_string();

    # create the generator
    generator.addGenerator(int(N), _hoomd.PolymerParticleGenerator(hoomd.context.exec_conf, 1.0, type_vector, bond_ab, bond_ab, bond_type, 100, box.dimensions));

    # set the separation radius
    generator.setSeparationRadius(name, min_dist/2.0);

    # generate the particles
    generator.generate();

    # initialize snapshot
    snapshot = generator.getSnapshot()

    my_domain_decomposition = _create_domain_decomposition(snapshot._global_box);
    if my_domain_decomposition is not None:
        hoomd.context.current.system_definition = _hoomd.SystemDefinition(snapshot, hoomd.context.exec_conf, my_domain_decomposition);
    else:
        hoomd.context.current.system_definition = _hoomd.SystemDefinition(snapshot, hoomd.context.exec_conf);

    # initialize the system
    hoomd.context.current.system = _hoomd.System(hoomd.context.current.system_definition, 0);

    _perform_common_init_tasks();
    return hoomd.data.system_data(hoomd.context.current.system_definition);

## Generates any number of randomly positioned polymers of configurable types
#
# \param box Simulation box dimensions (data.boxdim object)
# \param polymers Specification for the different polymers to create (see below)
# \param separation Separation radii for different particle types (see below)
# \param seed Random seed to use
#
# Any number of polymers can be generated, of the same or different types, as
# specified in the argument \a polymers. Parameters for each polymer include
# bond length, particle type list, bond list, and count.
#
# The syntax is best shown by example. The below line specifies that 600 block copolymers
# A6B7A6 with a %bond length of 1.2 be generated.
# \code
# polymer1 = dict(bond_len=1.2, type=['A']*6 + ['B']*7 + ['A']*6,
#                 bond="linear", count=600)
# \endcode
# Here is an example for a second polymer, specifying just 100 polymers made of 5 B beads
# bonded in a branched pattern
# \code
# polymer2 = dict(bond_len=1.2, type=['B']*5,
#                 bond=[(0, 1), (1,2), (1,3), (3,4)] , count=100)
# \endcode
# The \a polymers argument can be given a list of any number of polymer types specified
# as above. \a count randomly generated polymers of each type in the list will be
# generated in the system.
#
# In detail:
# - \a bond_len defines the %bond length of the generated polymers. This should
#   not necessarily be set to the equilibrium %bond length! The generator is dumb and doesn't know
#   that bonded particles can be placed closer together than the separation (see below). Thus
#   \a bond_len must be at a minimum set at twice the value of the largest separation radius. An
#   error will be generated if this is not the case.
# - \a type is a python list of strings. Each string names a particle type in the order that
#   they will be created in generating the polymer.
# - \a %bond can be specified as "linear" in which case the generator connects all particles together
#   with bonds to form a linear chain. \a %bond can also be given a list if python tuples (see example
#   above).
#   - Each tuple in the form of \c (a,b) specifies that particle \c a of the polymer be bonded to
#   particle \c b. These bonds are given the default type name of 'polymer' to be used when specifying parameters to
#   bond forces such as bond.harmonic.
#   - A tuple with three elements (a,b,type) can be used as above, but with a custom name for the bond. For example,
#   a simple branched polymer with different bond types on each branch could be defined like so:
#\code
#bond=[(0,1), (1,2), (2,3,'branchA'), (3,4,'branchA), (2,5,'branchB'), (5,6,'branchB')]
#\endcode
#
# \a separation \b must contain one entry for each particle type specified in \a polymers
# ('A' and 'B' in the examples above). The value given is the separation radius of each
# particle of that type. The generated polymer system will have no two overlapping
# particles.
#
# \b Examples:
# \code
# init.create_random_polymers(box=data.boxdim(L=35),
#                             polymers=[polymer1, polymer2],
#                             separation=dict(A=0.35, B=0.35));
#
# init.create_random_polymers(box=data.boxdim(L=31),
#                             polymers=[polymer1],
#                             separation=dict(A=0.35, B=0.35), seed=52);
#
# # create polymers in an orthorhombic box
# init.create_random_polymers(box=data.boxdim(Lx=18,Ly=10,Lz=25),
#                             polymers=[polymer2],
#                             separation=dict(A=0.35, B=0.35), seed=12345);
#
# # create a triclinic box with tilt factors xy=0.1 xz=0.2 yz=0.3
# init.create_random_polymers(box=data.boxdim(L=18, xy=0.1, xz=0.2, yz=0.3),
#                             polymeres=[polymer2],
#                             separation=dict(A=0.35, B=0.35));
# \endcode
#
# With all other parameters the same, create_random_polymers will always create the
# same system if \a seed is the same. Set a different \a seed (any integer) to create
# a different random system with the same parameters. Note that different versions
# of HOOMD \e may generate different systems even with the same seed due to programming
# changes.
#
# \note 1. For relatively dense systems (packing fraction 0.4 and higher) the simple random
# generation algorithm may fail to find room for all the particles and print an error message.
# There are two methods to solve this. First, you can lower the separation radii allowing particles
# to be placed closer together. Then setup integrate.nve with the \a limit option set to a
# relatively small value. A few thousand time steps should relax the system so that the simulation can be
# continued without the limit or with a different integrator. For extremely troublesome systems,
# generate it at a very low density and shrink the box with the command update.box_resize
# to the desired final size.
#
# \note 2. The polymer generator always generates polymers as if there were linear chains. If you
# provide a non-linear %bond topology, the bonds in the initial configuration will be stretched
# significantly. This normally doesn't pose a problem for harmonic bonds (bond.harmonic) as
# the system will simply relax over a few time steps, but can cause the system to blow up with FENE
# bonds (bond.fene).
#
# \note 3. While the custom %bond list allows you to create ring shaped polymers, testing shows that
# such conformations have trouble relaxing and get stuck in tangled configurations. If you need
# to generate a configuration of rings, you may need to write your own specialized initial configuration
# generator that writes HOOMD XML input files (see \ref page_xml_file_format). HOOMD's built-in polymer generator
# attempts to be as general as possible, but unfortunately cannot work in every possible case.
#
# The result of init.create_random_polymers can be saved in a variable and later used to read and/or change particle
# properties later in the script. See hoomd.data for more information.
#
def create_random_polymers(box, polymers, separation, seed=1):
    hoomd.util.print_status_line();

    hoomd.context._verify_init();

    # check if initialization has already occured
    if is_initialized():
        hoomd.context.msg.error("Cannot initialize more than once\n");
        raise RuntimeError("Error creating random polymers");

    if len(polymers) == 0:
        hoomd.context.msg.error("Polymers list cannot be empty.\n");
        raise RuntimeError("Error creating random polymers");

    if len(separation) == 0:
        hoomd.context.msg.error("Separation dict cannot be empty.\n");
        raise RuntimeError("Error creating random polymers");

    if not isinstance(box, hoomd.data.boxdim):
        hoomd.context.msg.error('Box must be a data.boxdim object\n');
        raise TypeError('box must be a data.boxdim object');

    # create the generator
    generator = _hoomd.RandomGenerator(hoomd.context.exec_conf,box._getBoxDim(), seed, box.dimensions);

    # make a list of types used for an eventual check vs the types in separation for completeness
    types_used = [];

    # track the minimum bond length
    min_bond_len = None;

    # build the polymer generators
    for poly in polymers:
        type_list = [];
        # check that all fields are specified
        if not 'bond_len' in poly:
            hoomd.context.msg.error('Polymer specification missing bond_len\n');
            raise RuntimeError("Error creating random polymers");

        if min_bond_len is None:
            min_bond_len = poly['bond_len'];
        else:
            min_bond_len = min(min_bond_len, poly['bond_len']);

        if not 'type' in poly:
            hoomd.context.msg.error('Polymer specification missing type\n');
            raise RuntimeError("Error creating random polymers");
        if not 'count' in poly:
            hoomd.context.msg.error('Polymer specification missing count\n');
            raise RuntimeError("Error creating random polymers");
        if not 'bond' in poly:
            hoomd.context.msg.error('Polymer specification missing bond\n');
            raise RuntimeError("Error creating random polymers");

        # build type list
        type_vector = _hoomd.std_vector_string();
        for t in poly['type']:
            type_vector.append(t);
            if not t in types_used:
                types_used.append(t);

        # build bond list
        bond_a = _hoomd.std_vector_uint();
        bond_b = _hoomd.std_vector_uint();
        bond_name = _hoomd.std_vector_string();

        # if the bond setting is 'linear' create a default set of bonds
        if poly['bond'] == 'linear':
            for i in range(0,len(poly['type'])-1):
                bond_a.append(i);
                bond_b.append(i+1);
                bond_name.append('polymer')
        #if it is a list, parse the user custom bonds
        elif type(poly['bond']) == type([]):
            for t in poly['bond']:
                # a 2-tuple gets the default 'polymer' name for the bond
                if len(t) == 2:
                    a,b = t;
                    name = 'polymer';
                # and a 3-tuple specifies the name directly
                elif len(t) == 3:
                    a,b,name = t;
                else:
                    hoomd.context.msg.error('Custom bond ' + str(t) + ' must have either two or three elements\n');
                    raise RuntimeError("Error creating random polymers");

                bond_a.append(a);
                bond_b.append(b);
                bond_name.append(name);
        else:
            hoomd.context.msg.error('Unexpected argument value for polymer bond\n');
            raise RuntimeError("Error creating random polymers");

        # create the generator
        generator.addGenerator(int(poly['count']), _hoomd.PolymerParticleGenerator(hoomd.context.exec_conf, poly['bond_len'], type_vector, bond_a, bond_b, bond_name, 100, box.dimensions));


    # check that all used types are in the separation list
    for t in types_used:
        if not t in separation:
            hoomd.context.msg.error("No separation radius specified for type " + str(t) + "\n");
            raise RuntimeError("Error creating random polymers");

    # set the separation radii, checking that it is within the minimum bond length
    for t,r in separation.items():
        generator.setSeparationRadius(t, r);
        if 2*r >= min_bond_len:
            hoomd.context.msg.error("Separation radius " + str(r) + " is too big for the minimum bond length of " + str(min_bond_len) + " specified\n");
            raise RuntimeError("Error creating random polymers");

    # generate the particles
    generator.generate();

    # copy over data to snapshot
    snapshot = generator.getSnapshot()

    my_domain_decomposition = _create_domain_decomposition(snapshot._global_box);
    if my_domain_decomposition is not None:
        hoomd.context.current.system_definition = _hoomd.SystemDefinition(snapshot, hoomd.context.exec_conf, my_domain_decomposition);
    else:
        hoomd.context.current.system_definition = _hoomd.SystemDefinition(snapshot, hoomd.context.exec_conf);

    # initialize the system
    hoomd.context.current.system = _hoomd.System(hoomd.context.current.system_definition, 0);

    _perform_common_init_tasks();
    return hoomd.data.system_data(hoomd.context.current.system_definition);

## Initializes the system from a snapshot
#
# \param snapshot The snapshot to initialize the system from
#
# Snapshots temporarily store system %data. Snapshots contain the complete simulation state in a
# single object. They can be used to start or restart a simulation.
#
# Example use cases in which a simulation may be started from a snapshot include user code that generates initial
# particle positions.
#
# **Example:**
# \code
# snapshot = my_system_create_routine(.. parameters ..)
# system = init.read_snapshot(snapshot)
# \endcode
#
# \sa hoomd.data
def read_snapshot(snapshot):
    hoomd.util.print_status_line();

    hoomd.context._verify_init();

    # check if initialization has already occured
    if is_initialized():
        hoomd.context.msg.error("Cannot initialize more than once\n");
        raise RuntimeError("Error initializing");

    # broadcast snapshot metadata so that all ranks have _global_box (the user may have set box only on rank 0)
    snapshot._broadcast(hoomd.context.exec_conf);
    my_domain_decomposition = _create_domain_decomposition(snapshot._global_box);

    if my_domain_decomposition is not None:
        hoomd.context.current.system_definition = _hoomd.SystemDefinition(snapshot, hoomd.context.exec_conf, my_domain_decomposition);
    else:
        hoomd.context.current.system_definition = _hoomd.SystemDefinition(snapshot, hoomd.context.exec_conf);

    # initialize the system
    hoomd.context.current.system = _hoomd.System(hoomd.context.current.system_definition, 0);

    _perform_common_init_tasks();
    return hoomd.data.system_data(hoomd.context.current.system_definition);

## Reads initial system state from an GSD file
#
# \param filename File to read
# \param restart If it exists, read \a restart instead of \a filename
# \param frame Index of the frame to read from the GSD file
# \param time_step (if specified) Time step number to use instead of the one stored in the GSD file
#
# All particles, bonds, angles, dihedrals, impropers, constraints, and box information
# are read from the given GSD file at the given frame index. To read and write GSD files
# outside of hoomd, see http://gsd.readthedocs.org/. dump.gsd writes GSD files.
#
# For restartable jobs, specify the initial condition in \a filename and the restart file in \a restart.
# init.read_gsd will read the restart file if it exists, otherwise it will read \a filename.
##
# If \a time_step is specified, its value will be used as the initial time
# step of the simulation instead of the one read from the GSD file.
#
# The result of init.read_gsd can be saved in a variable and later used to read and/or change particle properties
# later in the script. See hoomd.data for more information.
#
# \sa dump.gsd
def read_gsd(filename, restart = None, frame = 0, time_step = None):
    hoomd.util.print_status_line();

    hoomd.context._verify_init();

    # check if initialization has already occured
    if is_initialized():
        hoomd.context.msg.error("Cannot initialize more than once\n");
        raise RuntimeError("Error initializing");


    reader = _hoomd.GSDReader(hoomd.context.exec_conf, filename, frame);
    snapshot = reader.getSnapshot();
    if time_step is None:
        time_step = reader.getTimeStep();

    # broadcast snapshot metadata so that all ranks have _global_box (the user may have set box only on rank 0)
    snapshot._broadcast(hoomd.context.exec_conf);
    my_domain_decomposition = _create_domain_decomposition(snapshot._global_box);

    if my_domain_decomposition is not None:
        hoomd.context.current.system_definition = _hoomd.SystemDefinition(snapshot, hoomd.context.exec_conf, my_domain_decomposition);
    else:
        hoomd.context.current.system_definition = _hoomd.SystemDefinition(snapshot, hoomd.context.exec_conf);

    # initialize the system
    hoomd.context.current.system = _hoomd.System(hoomd.context.current.system_definition, time_step);

    _perform_common_init_tasks();
    return hoomd.data.system_data(hoomd.context.current.system_definition);

## Performs common initialization tasks
#
# \internal
# Initialization tasks that are performed for every simulation are to
# be done here. For example, setting up communication, registering the
# SFCPackUpdater, initializing the log writer, etc...
def _perform_common_init_tasks():
    # create the sorter
    hoomd.context.current.sorter = hoomd.update.sort();

    # create the default compute.thermo on the all group
    hoomd.util.quiet_status();
    all = hoomd.group.all();
    hoomd.compute._get_unique_thermo(group=all);
    hoomd.util.unquiet_status();

    # set up Communicator, and register it with the System
    if _hoomd.is_MPI_available():
        cpp_decomposition = hoomd.context.current.system_definition.getParticleData().getDomainDecomposition();
        if cpp_decomposition is not None:
            # create the c++ Communicator
            if not hoomd.context.exec_conf.isCUDAEnabled():
                cpp_communicator = _hoomd.Communicator(hoomd.context.current.system_definition, cpp_decomposition)
            else:
                cpp_communicator = _hoomd.CommunicatorGPU(hoomd.context.current.system_definition, cpp_decomposition)

            # set Communicator in C++ System
            hoomd.context.current.system.setCommunicator(cpp_communicator)

## Create a DomainDecomposition object
# \internal
def _create_domain_decomposition(box):
    if not _hoomd.is_MPI_available():
        return None

    # if we are only running on one processor, we use optimized code paths
    # for single-GPU execution
    if hoomd.context.exec_conf.getNRanks() == 1:
        return None

    # okay, we want a decomposition but one isn't set, so make a default one
    if hoomd.context.current.decomposition is None:
        # this is happening transparently to the user, so hush this up
        hoomd.util.quiet_status()
        hoomd.context.current.decomposition = hoomd.comm.decomposition()
        hoomd.util.unquiet_status()

    return hoomd.context.current.decomposition._make_cpp_decomposition(box)
