// Copyright (c) 2009-2019 The Regents of the University of Michigan
// This file is part of the HOOMD-blue project, released under the BSD 3-Clause License.


// Maintainer: joaander

#include "ActiveVicsekForceComputeGPU.h"
#include "ActiveVicsekForceComputeGPU.cuh"
#include "ActiveForceComputeGPU.cuh"

#include <vector>
namespace py = pybind11;
using namespace std;

/*! \file ActiveForceComputeGPU.cc
    \brief Contains code for the ActiveForceComputeGPU class
*/

/*! \param seed required user-specified seed number for random number generator.
    \param f_list An array of (x,y,z) tuples for the active force vector for each individual particle.
    \param orientation_link if True then forces and torques are applied in the particle's reference frame. If false, then the box reference fra    me is used. Only relevant for non-point-like anisotropic particles.
    /param orientation_reverse_link When True, the particle's orientation is set to match the active force vector. Useful for
    for using a particle's orientation to log the active force vector. Not recommended for anisotropic particles
    \param rotation_diff rotational diffusion constant for all particles.
    \param constraint specifies a constraint surface, to which particles are confined,
    such as update.constraint_ellipsoid.
*/
ActiveVicsekForceComputeGPU::ActiveVicsekForceComputeGPU(std::shared_ptr<SystemDefinition> sysdef,
                                        std::shared_ptr<ParticleGroup> group,
                                        std::shared_ptr<NeighborList> nlist,
			                Scalar r_dist,
			                Scalar coupling,
                                        int seed,
                                        pybind11::list f_lst,
                                        pybind11::list t_lst,
                                        bool orientation_link,
                                        bool orientation_reverse_link,
                                        Scalar rotation_diff)
        : ActiveVicsekForceCompute(sysdef, group, nlist, r_dist, coupling,  seed, f_lst, t_lst, orientation_link, orientation_reverse_link, rotation_diff), m_block_size(256)
    {
    if (!m_exec_conf->isCUDAEnabled())
        {
        m_exec_conf->msg->error() << "Creating a ActiveForceComputeGPU with no GPU in the execution configuration" << endl;
        throw std::runtime_error("Error initializing ActiveForceComputeGPU");
        }

    unsigned int N = m_pdata->getNGlobal();
    unsigned int group_size = m_group->getNumMembersGlobal();
    GPUArray<Scalar3> tmp_f_activeVec(N, m_exec_conf);
    GPUArray<Scalar3> tmp_t_activeVec(N, m_exec_conf);
    GPUArray<Scalar> tmp_f_activeMag(N, m_exec_conf);
    GPUArray<Scalar> tmp_t_activeMag(N, m_exec_conf);
    GPUArray<unsigned int> tmp_groupTags(group_size, m_exec_conf);

        {
        ArrayHandle<Scalar3> old_f_activeVec(m_f_activeVec, access_location::host);
        ArrayHandle<Scalar3> old_t_activeVec(m_t_activeVec, access_location::host);
        ArrayHandle<Scalar> old_f_activeMag(m_f_activeMag, access_location::host);
        ArrayHandle<Scalar> old_t_activeMag(m_t_activeMag, access_location::host);

        ArrayHandle<Scalar3> f_activeVec(tmp_f_activeVec, access_location::host);
        ArrayHandle<Scalar3> t_activeVec(tmp_t_activeVec, access_location::host);
        ArrayHandle<Scalar> f_activeMag(tmp_f_activeMag, access_location::host);
        ArrayHandle<Scalar> t_activeMag(tmp_t_activeMag, access_location::host);
        ArrayHandle<unsigned int> groupTags(tmp_groupTags, access_location::host);

        // for each of the particles in the group
        for (unsigned int i = 0; i < group_size; i++)
            {
            unsigned int tag = m_group->getMemberTag(i);
            groupTags.data[i] = tag;
            f_activeMag.data[tag] = old_f_activeMag.data[i];
            f_activeVec.data[tag] = old_f_activeVec.data[i];

            t_activeMag.data[tag] = old_t_activeMag.data[i];
            t_activeVec.data[tag] = old_t_activeVec.data[i];

            }

        last_computed = 10;
        }

    m_f_activeVec.swap(tmp_f_activeVec);
    m_f_activeMag.swap(tmp_f_activeMag);
    m_t_activeVec.swap(tmp_t_activeVec);
    m_t_activeMag.swap(tmp_t_activeMag);
    m_groupTags.swap(tmp_groupTags);

    }


void ActiveVicsekForceComputeGPU::addManifold(std::shared_ptr<Manifold> manifold)
	{
	m_manifold = manifold;
	m_constraint = true;
	}

/*! This function sets appropriate active forces and torques on all active particles.
*/
void ActiveVicsekForceComputeGPU::setForces()
    {
    //  array handles
    ArrayHandle<Scalar3> d_f_actVec(m_f_activeVec, access_location::device, access_mode::read);
    ArrayHandle<Scalar> d_f_actMag(m_f_activeMag, access_location::device, access_mode::read);
    ArrayHandle<Scalar4> d_force(m_force, access_location::device, access_mode::overwrite);

    ArrayHandle<Scalar3> d_t_actVec(m_t_activeVec, access_location::device, access_mode::read);
    ArrayHandle<Scalar> d_t_actMag(m_t_activeMag, access_location::device, access_mode::read);
    ArrayHandle<Scalar4> d_torque(m_torque, access_location::device, access_mode::overwrite);

    ArrayHandle<Scalar4> d_orientation(m_pdata->getOrientationArray(), access_location::device, access_mode::readwrite);
    ArrayHandle<unsigned int> d_rtag(m_pdata->getRTags(), access_location::device, access_mode::read);
    ArrayHandle<unsigned int> d_groupTags(m_groupTags, access_location::device, access_mode::read);

    // sanity check
    assert(d_force.data != NULL);
    assert(d_f_actVec.data != NULL);
    assert(d_f_actMag.data != NULL);
    assert(d_t_actVec.data != NULL);
    assert(d_t_actMag.data != NULL);
    assert(d_orientation.data != NULL);
    assert(d_rtag.data != NULL);
    assert(d_groupTags.data != NULL);
    bool orientationLink = (m_orientationLink == true);
    bool orientationReverseLink = (m_orientationReverseLink == true);
    unsigned int group_size = m_group->getNumMembers();
    unsigned int N = m_pdata->getN();
    EvaluatorConstraintManifold manifoldGPU (m_manifold->returnL(), m_manifold->returnR(), m_manifold->returnSurf());

    m_exec_conf->beginMultiGPU();

    gpu_compute_active_force_set_forces(group_size,
                                     d_rtag.data,
                                     d_groupTags.data,
                                     d_force.data,
                                     d_torque.data,
                                     d_orientation.data,
                                     d_f_actVec.data,
                                     d_f_actMag.data,
                                     d_t_actVec.data,
                                     d_t_actMag.data,
                                     manifoldGPU,
                                     m_constraint,
                                     orientationLink,
                                     orientationReverseLink,
                                     N,
                                     m_block_size);

    if(m_exec_conf->isCUDAErrorCheckingEnabled())
        CHECK_CUDA_ERROR();

    m_exec_conf->endMultiGPU();
    }

/*! This function applies rotational diffusion to all active particles. The angle between the torque vector and
 * force vector does not change
    \param timestep Current timestep
*/
void ActiveVicsekForceComputeGPU::rotationalDiffusion(unsigned int timestep)
    {
    //  array handles
    ArrayHandle<Scalar3> d_f_actVec(m_f_activeVec, access_location::device, access_mode::readwrite);
    ArrayHandle<Scalar3> d_t_actVec(m_t_activeVec, access_location::device, access_mode::readwrite);
    ArrayHandle<Scalar4> d_pos(m_pdata -> getPositions(), access_location::device, access_mode::read);
    ArrayHandle<Scalar4> d_force(m_force, access_location::device, access_mode::overwrite);
    ArrayHandle<Scalar4> d_torque(m_torque, access_location::device, access_mode::overwrite);
    ArrayHandle<unsigned int> d_rtag(m_pdata->getRTags(), access_location::device, access_mode::read);
    ArrayHandle<unsigned int> d_groupTags(m_groupTags, access_location::device, access_mode::read);

    ArrayHandle<unsigned int> d_n_neigh(m_nlist->getNNeighArray(), access_location::device, access_mode::read);
    ArrayHandle<unsigned int> d_nlist(m_nlist->getNListArray(), access_location::device, access_mode::read);
    ArrayHandle<unsigned int> d_head_list(m_nlist->getHeadList(), access_location::device, access_mode::read);
    ArrayHandle<Scalar3> d_f_actVec_backup(m_f_activeVec, access_location::device, access_mode::read);

    assert(d_pos.data != NULL);

    bool is2D = (m_sysdef->getNDimensions() == 2);
    unsigned int group_size = m_group->getNumMembers();
    EvaluatorConstraintManifold manifoldGPU (m_manifold->returnL(), m_manifold->returnR(), m_manifold->returnSurf());

    BoxDim box = m_pdata->getBox();

    m_exec_conf->beginMultiGPU();

    gpu_compute_active_vicsek_force_rotational_diffusion(group_size,
                                                d_rtag.data,
                                                d_groupTags.data,
                                                d_pos.data,
                                                d_force.data,
                                                d_torque.data,
                                                d_f_actVec.data,
                                                d_f_actVec_backup.data,
                                                d_t_actVec.data,
                                                d_n_neigh.data,
                                                d_nlist.data,
                                                d_head_list.data,
                                                box,
                                     		manifoldGPU,
                                     		m_constraint,
                                                is2D,
                                                m_rotationConst,
                                                timestep,
                                       	        m_r_dist_sq,
                                       	        m_coupling*m_deltaT,
                                                m_seed,
                                                m_block_size);

    if(m_exec_conf->isCUDAErrorCheckingEnabled())
        CHECK_CUDA_ERROR();

    m_exec_conf->endMultiGPU();
    }

/*! This function sets an ellipsoid surface constraint for all active particles. Torque is not considered here
*/
void ActiveVicsekForceComputeGPU::setConstraint()
    {
    //  array handles
    ArrayHandle<Scalar3> d_f_actVec(m_f_activeVec, access_location::device, access_mode::readwrite);
    ArrayHandle<Scalar3> d_t_actVec(m_t_activeVec, access_location::device, access_mode::readwrite);
    ArrayHandle<Scalar4> d_pos(m_pdata -> getPositions(), access_location::device, access_mode::read);
    ArrayHandle<Scalar4> d_force(m_force, access_location::device, access_mode::overwrite);
    ArrayHandle<Scalar4> d_torque(m_torque, access_location::device, access_mode::overwrite);
    ArrayHandle<unsigned int> d_rtag(m_pdata->getRTags(), access_location::device, access_mode::read);
    ArrayHandle<unsigned int> d_groupTags(m_groupTags, access_location::device, access_mode::read);

    assert(d_pos.data != NULL);

    unsigned int group_size = m_group->getNumMembers();
    EvaluatorConstraintManifold manifoldGPU (m_manifold->returnL(), m_manifold->returnR(), m_manifold->returnSurf());

    m_exec_conf->beginMultiGPU();

    gpu_compute_active_force_set_constraints(group_size,
                                             d_rtag.data,
                                             d_groupTags.data,
                                             d_pos.data,
                                             d_force.data,
                                             d_torque.data,
                                             d_f_actVec.data,
                                             d_t_actVec.data,
                                     	     manifoldGPU,
                                     	     m_constraint,
                                             m_block_size);

    if(m_exec_conf->isCUDAErrorCheckingEnabled())
        CHECK_CUDA_ERROR();

    m_exec_conf->endMultiGPU();
    }

//void ActiveVicsekForceComputeGPU::setMeanVelocity(unsigned int timestep)
//    {
//
//	std::cout << "start nlist"<< std::endl;
//        m_nlist->compute(timestep);
//	std::cout << "end nlist"<< std::endl;
//
//
//	std::cout << "access forces"<< std::endl;
//        ArrayHandle<Scalar3> d_f_actVec(m_f_activeVec, access_location::device, access_mode::readwrite);
//
//        // access the neighbor list
//        ArrayHandle<unsigned int> d_n_neigh(m_nlist->getNNeighArray(), access_location::device, access_mode::read);
//        ArrayHandle<unsigned int> d_nlist(m_nlist->getNListArray(), access_location::device, access_mode::read);
//        ArrayHandle<unsigned int> d_head_list(m_nlist->getHeadList(), access_location::device, access_mode::read);
//        ArrayHandle<Scalar3> d_f_actVec_backup(m_f_activeVec, access_location::device, access_mode::read);
//    	ArrayHandle<unsigned int> d_rtag(m_pdata->getRTags(), access_location::device, access_mode::read);
//    	ArrayHandle<unsigned int> d_groupTags(m_groupTags, access_location::device, access_mode::read);
//        ArrayHandle<Scalar4> d_pos(m_pdata->getPositions(), access_location::device, access_mode::read);
//
//    	unsigned int group_size = m_group->getNumMembers();
//
//	std::cout << "forces accessed"<< std::endl;
//
//        BoxDim box = m_pdata->getBox();
//
//	std::cout << "start loop"<< std::endl;
//
//        m_exec_conf->beginMultiGPU();
//
//        gpu_compute_active_vicsek_force_set_mean_velocity(group_size,
//                                             	 d_rtag.data,
//                                             	 d_groupTags.data,
//                                                 d_f_actVec.data,
//                                                 d_f_actVec_backup.data,
//                                                 d_n_neigh.data,
//                                                 d_nlist.data,
//                                                 d_head_list.data,
//                                                 d_pos.data,
//                                                 box,
//                                         	 m_r_dist_sq,
//                                                 m_block_size);
//
//        if(m_exec_conf->isCUDAErrorCheckingEnabled())
//            CHECK_CUDA_ERROR();
//
//        m_exec_conf->endMultiGPU();
//
//	std::cout << "end loop"<< std::endl;
//
//    }

void export_ActiveVicsekForceComputeGPU(py::module& m)
    {
    py::class_< ActiveVicsekForceComputeGPU, std::shared_ptr<ActiveVicsekForceComputeGPU> >(m, "ActiveVicsekForceComputeGPU", py::base<ActiveVicsekForceCompute>())
        .def(py::init<  std::shared_ptr<SystemDefinition>,
                        std::shared_ptr<ParticleGroup>,
                        std::shared_ptr<NeighborList>,
                        Scalar,
                        Scalar,
                        int,
                        pybind11::list,
                        pybind11::list,
                        bool,
                        bool,
                        Scalar >())
    .def("addManifold", &ActiveVicsekForceComputeGPU::addManifold)
    ;
    }