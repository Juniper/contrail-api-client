# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License. You may obtain
#  a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#  WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#  License for the specific language governing permissions and limitations
#  under the License.
#

try:  # for pip >= 10
    from pip._internal.req import parse_requirements
except ImportError:  # for pip <= 9.0.3
    from pip.req import parse_requirements
from setuptools import setup, find_packages


setup(
    name='contrail-api-client',
    description="Contrail VNC Configuration API client library",
    long_description=open('README.md').read(),
    license='Apache-2',
    author='OpenContrail',
    author_email='dev@lists.opencontrail.org',
    url='http://www.opencontrail.org/documentation/api/r4.1/',
    version=open('version.info', 'r+').read().strip('\n').strip('\t'),
    classifiers=[
        'Intended Audience :: Information Technology',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX :: Linux',
        'Development Status :: 5 - Production/Stable',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
    ],
    packages=find_packages(),
    install_requires=[str(req.req) for req in parse_requirements('requirements.txt', session='hack')],
    tests_require=[str(req.req) for req in parse_requirements('test-requirements.txt', session='hack')],
    package_data={'etc/contrail/': ['vnc_api_lib.ini']},
    keywords='contrail vnc api client library',
    test_suite="vnc_api.tests",
)
