/*
Highly Optimized Object-Oriented Molecular Dynamics (HOOMD) Open
Source Software License
Copyright (c) 2008 Ames Laboratory Iowa State University
All rights reserved.

Redistribution and use of HOOMD, in source and binary forms, with or
without modification, are permitted, provided that the following
conditions are met:

* Redistributions of source code must retain the above copyright notice,
this list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright
notice, this list of conditions and the following disclaimer in the
documentation and/or other materials provided with the distribution.

* Neither the name of the copyright holder nor the names HOOMD's
contributors may be used to endorse or promote products derived from this
software without specific prior written permission.

Disclaimer

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDER AND
CONTRIBUTORS ``AS IS''  AND ANY EXPRESS OR IMPLIED WARRANTIES,
INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. 

IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS  BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF
THE POSSIBILITY OF SUCH DAMAGE.
*/

// $Id$
// $URL$
// Maintainer: joaander

#ifdef WIN32
#pragma warning( push )
#pragma warning( disable : 4103 4244 )
#endif

#include <boost/python.hpp>
using namespace boost::python;

#include "Updater.h"

/*! \file Updater.cc
	\brief Defines a base class for all updaters
*/

/*! \param sysdef System this compute will act on. Must not be NULL.
	\post The Updater is constructed with the given particle data and a NULL profiler.
*/
Updater::Updater(boost::shared_ptr<SystemDefinition> sysdef) : m_sysdef(sysdef), m_pdata(m_sysdef->getParticleData()), exec_conf(m_pdata->getExecConf())
	{
	// sanity check
	assert(m_sysdef);
	assert(m_pdata);
	}
		
/*! It is useful for the user to know where computation time is spent, so all Updaters
	should profile themselves. This method sets the profiler for them to use.
	This method does not need to be called, as Updaters will not profile themselves
	on a NULL profiler
	\param prof Pointer to a profiler for the compute to use. Set to NULL 
		(boost::shared_ptr<Profiler>()) to stop the 
		analyzer from profiling itself.
	\note Derived classes MUST check if m_prof is set before calling any profiler methods.
*/
void Updater::setProfiler(boost::shared_ptr<Profiler> prof)
	{
	m_prof = prof;
	}

//! Wrapper class to expose pure virtual method to python
class UpdaterWrap: public Updater, public wrapper<Updater>
	{
	public:
		//! Forwards construction on to the base class
		/*! \param sysdef parameter to forward to the base class constructor
		*/
		UpdaterWrap(boost::shared_ptr<SystemDefinition> sysdef) : Updater(sysdef) { }
		
		//! Hanldes pure virtual Updater::update()
		/*! \param timestep parameter to forward to Updater::update()
		*/
		void update(unsigned int timestep)
			{
			this->get_override("update")(timestep);
			}
	};
	
void export_Updater()
	{
	class_<UpdaterWrap, boost::shared_ptr<UpdaterWrap>, boost::noncopyable>("Updater", init< boost::shared_ptr<SystemDefinition> >())
		.def("update", pure_virtual(&Updater::update))
		.def("setProfiler", &Updater::setProfiler)
		;
	}

#ifdef WIN32
#pragma warning( pop )
#endif
