#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

# src directory

import sys
import platform

subdirs = [
    'schema'
]

if platform.system() != 'Windows':
    subdirs += ['api-lib']

include = ['#/controller/src', '#/build/include', '#src/contrail-common', '#controller/lib']

libpath = ['#/build/lib']

libs = ['boost_system', 'boost_thread', 'log4cplus']
if sys.platform.startswith('win'):
    libs.append('contrail-windows')
else:
    libs.append('pthread')

common = DefaultEnvironment().Clone()

if common['OPT'] == 'production' or common.UseSystemTBB():
    libs.append('tbb')
else:
    libs.append('tbb_debug')

common.Append(LIBPATH = libpath)
common.Prepend(LIBS = libs)

if not sys.platform.startswith('win'):
    common.Append(CCFLAGS = '-Wall -Werror -Wsign-compare')

if not sys.platform.startswith('darwin'):
    if platform.system().startswith('Linux'):
       if not platform.linux_distribution()[0].startswith('XenServer'):
          common.Append(CCFLAGS = ['-Wno-unused-local-typedefs'])
if sys.platform.startswith('freebsd'):
    common.Append(CCFLAGS = ['-Wno-unused-local-typedefs'])
common.Append(CPPPATH = include)
common.Append(CCFLAGS = [common['CPPDEFPREFIX'] + 'RAPIDJSON_NAMESPACE=contrail_rapidjson'])

BuildEnv = common.Clone()

if sys.platform.startswith('linux'):
    BuildEnv.Append(CCFLAGS = ['-DLINUX'])
elif sys.platform.startswith('darwin'):
    BuildEnv.Append(CCFLAGS = ['-DDARWIN'])

if sys.platform.startswith('freebsd'):
    BuildEnv.Prepend(LINKFLAGS = ['-lprocstat'])


BuildEnv['INSTALL_DOC_PKG'] = BuildEnv['INSTALL_DOC'] + '/contrail-docs/html'
BuildEnv['INSTALL_MESSAGE_DOC'] = BuildEnv['INSTALL_DOC_PKG'] + '/messages'


for dir in subdirs:
    BuildEnv.SConscript(dir + '/SConscript',
                         exports='BuildEnv',
                         variant_dir=BuildEnv['TOP'] + '/' + dir,
                         duplicate=0)
