# Software License Agreement (BSD License)
#
# Copyright (c) 2013, Open Source Robotics Foundation, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Open Source Robotics Foundation, Inc. nor
#    the names of its contributors may be used to endorse or promote
#    products derived from this software without specific prior
#    written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from __future__ import print_function

import argparse
import logging
import os
import sys
import yaml

from rosinstall_generator.generator import ARG_ALL_PACKAGES, ARG_CURRENT_ENVIRONMENT, generate_rosinstall, sort_rosinstall


def _existing_directory(path):
    if not os.path.isdir(path):
        raise argparse.ArgumentTypeError("'%s' is not an existing directory" % path)
    return path


def main(argv=sys.argv[1:]):
    distro_name = os.environ['ROS_DISTRO'] if 'ROS_DISTRO' in os.environ else None
    parser = argparse.ArgumentParser(
        description='Generate a .rosinstall file for a set of packages.')
    parser.add_argument('--debug', action='store_true', default=False,
        help='Print debug information about fetching the ROS distribution files to stderr')
    parser.add_argument('--verbose', action='store_true', default=False,
        help='Print verbose information to stderr')
    parser.add_argument('--rosdistro', required=distro_name is None, default=distro_name,
        help='The ROS distro (default: environment variable ROS_DISTRO if defined)')
    parser.add_argument('package_names', nargs='*', metavar='pkgname',
        help="catkin package names, rosbuild stack names or variant names. Use '%s' to specify all packages available in the current environment. Use '%s' to specify all release packages (only usable as a single argument)." % (ARG_CURRENT_ENVIRONMENT, ARG_ALL_PACKAGES))
    parser.add_argument('--from-path', type=_existing_directory, nargs='*',
        help="Add a set of catkin packages found recursively under the given path as if they would have been passed as 'package_names'.")
    parser.add_argument('--repos', nargs='*', metavar='reponame',
        help="Repository names containing catkin packages. Use '%s' to specify all release packages (only usable as a single argument)." % ARG_ALL_PACKAGES)

    group = parser.add_mutually_exclusive_group()
    group.add_argument('--upstream', action='store_true', default=False,
        help='Fetch the release tag of catkin packages from the upstream repo instead of the gbp. Note that this implies always fetching the whole repository which might contain additional (unreleased) packages.')
    group.add_argument('--upstream-development', action='store_true', default=False,
        help='Fetch the development version of catkin packages from the upstream repo instead of the gbp. Be aware that the development version might not even be intended to build between releases. Note that this implies always fetching the whole repository which might contain additional (unreleased) packages.')

    group = parser.add_mutually_exclusive_group()
    group.add_argument('--deps', action='store_true', default=False,
        help='Include recursive dependencies')
    group.add_argument('--deps-up-to', nargs='*',
        help="A set of packages which will limit the recursive dependencies to packages which (in-)directly depend on a package in this set. Use '%s' to specify all packages available in the current environment." % ARG_CURRENT_ENVIRONMENT)

    # implies either --deps or --deps-up-to
    parser.add_argument('--deps-depth', type=int, metavar='N',
        help='Limit recursive dependencies to a specific level (not supported on Groovy).')
    parser.add_argument('--deps-only', action='store_true', default=False,
        help='Include only the recursive dependencies but not the specified packages')

    group = parser.add_mutually_exclusive_group()
    group.add_argument('--wet-only', action='store_true', default=False,
        help='Only include catkin packages')
    group.add_argument('--dry-only', action='store_true', default=False,
        help='Only include rosbuild stacks')
    group.add_argument('--catkin-only', action='store_true', default=False,
        help="Only wet packages with build type 'catkin'")
    group.add_argument('--non-catkin-only', action='store_true', default=False,
        help="Only wet packages with build type other than 'catkin'")

    parser.add_argument('--exclude', nargs='*',
        help="Exclude a set of packages (also skips further recursive dependencies). Use '%s' to specify all packages available in the current environment." % ARG_CURRENT_ENVIRONMENT)
    parser.add_argument('--exclude-path', type=_existing_directory, nargs='*',
        help='Exclude a set of catkin packages found recursively under the given path (also skips further recursive dependencies).')

    parser.add_argument('--flat', action='store_true', default=False,
        help='Use a flat folder structure without a parent folder names after the repository containing the catkin packages')

    parser.add_argument('--tar', action='store_true', default=False,
        help='Use tarballs instead of repositories for catkin packages (rosbuild stacks are always tarballs)')

    parser.add_argument('--format', choices=('rosinstall', 'repos'), default='rosinstall',
        help='Output the repository information in .rosinstall or .repos format')

    args = parser.parse_args(argv)

    # check for invalid combinations
    if args.rosdistro == 'groovy' and args.deps_depth:
        parser.error("Option '--deps-depth N' is not available for the ROS distro 'groovy'")
    if args.rosdistro != 'groovy':
        if args.dry_only:
            parser.error("For the ROS distro '%s' there are no rosbuild released packages so '--dry-only' is not a valid option" % args.rosdistro)
        args.wet_only = True

    if not args.package_names and not args.from_path and not args.repos:
        parser.error('Either some package names must be specified, some --from-path or some repository names using --repos')

    if ARG_ALL_PACKAGES in args.package_names and (len(args.package_names) > 1 or args.repos):
        parser.error("When using '%s' as a package name no other names can be specified" % ARG_ALL_PACKAGES)

    if not args.deps and not args.deps_up_to:
        if args.deps_depth:
            parser.error("Option '--deps-depth N' can only be used together with either '--deps' or '--deps-up-to'")
        if args.deps_only:
            parser.error("Option '--deps-only' can only be used together with either '--deps' or '--deps-up-to'")

    if args.deps_depth is not None and args.deps_depth < 1:
        parser.error("The argument 'N' to the option '--deps-depth ' must be a positive integer")

    if args.catkin_only or args.non_catkin_only:
        args.wet_only = True

    # pass all logging output to stderr
    logger = logging.getLogger('rosinstall_generator')
    logger.addHandler(logging.StreamHandler(sys.stderr))

    verbose_level = logging.DEBUG if args.verbose else logging.INFO
    logger.setLevel(verbose_level)

    debug_level = logging.DEBUG if args.debug else logging.INFO
    logger = logging.getLogger('rosinstall_generator.dry')
    logger.setLevel(debug_level)
    logger = logging.getLogger('rosinstall_generator.wet')
    logger.setLevel(debug_level)

    if '--rosdistro' not in argv:
        print('Using ROS_DISTRO: %s' % args.rosdistro, file=sys.stderr)

    try:
        rosinstall_data = generate_rosinstall(args.rosdistro, args.package_names,
            from_paths=args.from_path,
            repo_names=args.repos,
            deps=args.deps, deps_up_to=args.deps_up_to, deps_depth=args.deps_depth, deps_only=args.deps_only,
            wet_only=args.wet_only, dry_only=args.dry_only, catkin_only=args.catkin_only, non_catkin_only=args.non_catkin_only,
            excludes=args.exclude, exclude_paths=args.exclude_path,
            flat=args.flat,
            tar=args.tar,
            upstream_version_tag=args.upstream, upstream_source_version=args.upstream_development)
    except RuntimeError as e:
        if args.debug:
            raise
        print(str(e), file=sys.stderr)
        return 1
    if args.format == 'rosinstall':
        rosinstall_data = sort_rosinstall(rosinstall_data)
    elif args.format == 'repos':
        # convert data into .repos format
        repos_data = {}
        for data in rosinstall_data:
            assert len(data) == 1
            type_ = list(data.keys())[0]
            repo_data = data[type_]
            assert repo_data['local-name'] not in repos_data, 'Multiple entries with the local-name: ' + repo_data['local-name']
            repos_data[repo_data['local-name']] = {
                'type': type_,
                'url': repo_data['uri'],
            }
            if 'version' in repo_data and type_ != 'tar':
                repos_data[repo_data['local-name']]['version'] = repo_data['version']
        rosinstall_data = {'repositories': repos_data}
    else:
        assert False, 'Unhandled format: ' + args.format
    print(yaml.safe_dump(rosinstall_data, default_flow_style=False))
    return 0
