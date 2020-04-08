# -*- mode: python; -*-

#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

# repository root directory
import os
import sys
import rules

# Add local protoc binary path 
os.environ["PATH"] += os.pathsep + './bin'

conf = Configure(DefaultEnvironment(ENV = os.environ))
env = rules.SetupBuildEnvironment(conf)
env['api_repo_path'] = '#'
SConscript(dirs=[ '.'])

