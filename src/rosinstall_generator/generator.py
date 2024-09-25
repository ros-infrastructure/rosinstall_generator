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

import copy
import logging
import os

from catkin_pkg.package import InvalidPackage, parse_package_string
from catkin_pkg.packages import find_packages_allowing_duplicates

from rospkg import RosPack
from rospkg.environment import ROS_PACKAGE_PATH

from rosinstall_generator.distro import get_distro
from rosinstall_generator.distro import generate_rosinstall as distro_generate_rosinstall
from rosinstall_generator.distro import get_recursive_dependencies
from rosinstall_generator.distro import get_recursive_dependencies_on
from rosinstall_generator.distro import get_package_names
from rosinstall_generator.distro import _generate_rosinstall


logger = logging.getLogger('rosinstall_generator')

ARG_ALL_PACKAGES = 'ALL'
ARG_CURRENT_ENVIRONMENT = 'RPP'


def _split_special_keywords(names):
    non_keyword_names = set(names)
    keywords = set([])
    if ARG_ALL_PACKAGES in names:
        non_keyword_names.remove(ARG_ALL_PACKAGES)
        keywords.add(ARG_ALL_PACKAGES)
    if ARG_CURRENT_ENVIRONMENT in names:
        non_keyword_names.remove(ARG_CURRENT_ENVIRONMENT)
        keywords.add(ARG_CURRENT_ENVIRONMENT)
    return non_keyword_names, keywords


def _classify_repo_names(distro_name, repo_names):
    names = set([])
    unknown_names = set([])
    if repo_names:
        distro = get_cached_distro(distro_name)
        for repo_name in repo_names:
            if repo_name in distro.repositories:
                names.add(repo_name)
            else:
                unknown_names.add(repo_name)
    return names, unknown_names


def _get_packages_for_repos(distro_name, repo_names, source=False):
    package_names = set([])
    unreleased_repo_names = set([])
    ros_distro = get_cached_distro(distro_name)
    for repo_name in repo_names:
        if source:
            if not ros_distro.repositories[repo_name].source_repository:
                continue
            # Returns a mapping of package names to package XML strings in particular repo.
            source_package_xmls = ros_distro.get_source_repo_package_xmls(repo_name)
        if source and source_package_xmls:
            package_names.update(source_package_xmls.keys())
        else:
            release_repo = ros_distro.repositories[repo_name].release_repository
            if release_repo and release_repo.version:
                package_names.update(release_repo.package_names)
            else:
                unreleased_repo_names.add(repo_name)
    return package_names, unreleased_repo_names


def _classify_names(distro_name, names, source=False):
    unknown_names = set(names or [])

    package_names = set([])
    variant_names = set([])

    # identify packages
    if unknown_names:
        ros_distro = get_cached_distro(distro_name)
        packages = ros_distro.source_packages if source and ros_distro.source_packages else ros_distro.release_packages
        for name in unknown_names:
            if name in packages:
                package_names.add(name)
        unknown_names -= package_names

    return Names(package_names), unknown_names


def generate_rosinstall_for_repos(repos, version_tag=True, tar=False):
    rosinstall_data = []
    for repo in repos.values():
        if version_tag:
            version = repo.release_repository.version.split('-')[0]
            vcs_type = repo.release_repository.type
        else:
            version = repo.source_repository.version
            vcs_type = repo.source_repository.type
        rosinstall_data += _generate_rosinstall(repo.name, repo.source_repository.url, version, tar=tar, vcs_type=vcs_type)
    return rosinstall_data


class Names(object):
    '''
    Stores package names.
    '''

    def __init__(self, package_names):
        self.package_names = set(package_names)

    def update(self, other):
        self.package_names.update(other.package_names)


def _expand_keywords(distro_name, keywords):
    names = set([])
    if ARG_ALL_PACKAGES in keywords:
        ros_distro = get_cached_distro(distro_name)
        released_package_names, _ = get_package_names(ros_distro)
        names.update(released_package_names)
    if ARG_CURRENT_ENVIRONMENT in keywords:
        names.update(_get_packages_in_environment())
    return names


_packages_in_environment = None


def _get_packages_in_environment():
    global _packages_in_environment
    if _packages_in_environment is None:
        if ROS_PACKAGE_PATH not in os.environ or not os.environ[ROS_PACKAGE_PATH]:
            raise RuntimeError("The environment variable '%s' must be set when using '%s'" % (ROS_PACKAGE_PATH, ARG_CURRENT_ENVIRONMENT))
        _packages_in_environment = RosPack().list()
    return _packages_in_environment


def _get_package_names(path):
    return set([pkg.name for _, pkg in find_packages_allowing_duplicates(path).items()])


_cached_distro = None


def get_cached_distro(distro_name):
    global _cached_distro
    if _cached_distro is None:
        _cached_distro = get_distro(distro_name)
    return _cached_distro


def generate_rosinstall(distro_name, names,
    from_paths=None, repo_names=None,
    deps=False, deps_up_to=None, deps_depth=None, deps_only=False,
    wet_only=False, dry_only=False, catkin_only=False, non_catkin_only=False,
    excludes=None, exclude_paths=None,
    flat=False,
    tar=False,
    upstream_version_tag=False, upstream_source_version=False):

    # classify package names
    names, pkg_keywords = _split_special_keywords(names)

    # find packages recursively in include paths
    if from_paths:
        include_names_from_path = set([])
        [include_names_from_path.update(_get_package_names(from_path)) for from_path in from_paths]
        logger.debug("The following packages found in '--from-path' will be considered: %s" % ', '.join(sorted(include_names_from_path)))
        names.update(include_names_from_path)

    # Allow special keywords in repos
    repo_names, repo_keywords = _split_special_keywords(repo_names or [])
    if set(repo_keywords).difference(set([ARG_ALL_PACKAGES])):
        raise RuntimeError('The only keyword supported by repos is %r' % (ARG_ALL_PACKAGES))

    if ARG_ALL_PACKAGES in repo_keywords:
        ros_distro = get_cached_distro(distro_name)
        repo_names = ros_distro.repositories.keys()

    # expand repository names into package names
    repo_names, unknown_repo_names = _classify_repo_names(distro_name, repo_names)
    if unknown_repo_names:
        logger.warn('The following unknown repositories will be ignored: %s' % (', '.join(sorted(unknown_repo_names))))
    package_names, unreleased_repo_names = _get_packages_for_repos(distro_name, repo_names, source=upstream_source_version)
    names.update(package_names)
    if unreleased_repo_names and not upstream_version_tag and not upstream_source_version:
        logger.warn('The following unreleased repositories will be ignored: %s' % ', '.join(sorted(unreleased_repo_names)))
    if unreleased_repo_names and (deps or deps_up_to) and (upstream_version_tag or upstream_source_version):
        logger.warn('The dependencies of the following unreleased repositories are unknown and will be ignored: %s' % ', '.join(sorted(unreleased_repo_names)))
    has_repos = ((repo_names - unreleased_repo_names) and (upstream_version_tag or upstream_source_version)) or (unreleased_repo_names and upstream_source_version)

    names, unknown_names = _classify_names(distro_name, names, source=upstream_source_version)
    if unknown_names:
        logger.warn('The following unreleased packages will be ignored: %s' % (', '.join(sorted(unknown_names))))
    if pkg_keywords:
        expanded_names, unknown_names = _classify_names(distro_name, _expand_keywords(distro_name, pkg_keywords), source=upstream_source_version)
        if unknown_names:
            logger.warn('The following unreleased packages from the %s will be ignored: %s' % (ROS_PACKAGE_PATH, ', '.join(sorted(unknown_names))))
        names.update(expanded_names)
    if not names.package_names and not has_repos:
        raise RuntimeError('No packages left after ignoring unreleased')
    if names.package_names:
        logger.debug('Packages: %s' % ', '.join(sorted(names.package_names)))
    if unreleased_repo_names:
        logger.debug('Unreleased repositories: %s' % ', '.join(sorted(unreleased_repo_names)))

    # classify deps-up-to
    deps_up_to_names, deps_keywords = _split_special_keywords(deps_up_to or [])
    deps_up_to_names, unknown_names = _classify_names(distro_name, deps_up_to_names, source=upstream_source_version)
    if unknown_names:
        logger.warn("The following unreleased '--deps-up-to' packages will be ignored: %s" % (', '.join(sorted(unknown_names))))
    if deps_keywords:
        expanded_names, unknown_names = _classify_names(distro_name, _expand_keywords(distro_name, deps_keywords), source=upstream_source_version)
        if unknown_names:
            logger.warn("The following unreleased '--deps-up-to' packages from the %s will be ignored: %s" % (ROS_PACKAGE_PATH, ', '.join(sorted(unknown_names))))
        deps_up_to_names.update(expanded_names)
    if deps_up_to:
        logger.debug('Dependencies up to: %s' % ', '.join(sorted(deps_up_to_names.package_names)))

    # classify excludes
    exclude_names, excludes_keywords = _split_special_keywords(excludes or [])
    if exclude_paths:
        exclude_names_from_path = set([])
        [exclude_names_from_path.update(_get_package_names(exclude_path)) for exclude_path in exclude_paths]
        logger.debug("The following packages found in '--exclude-path' will be excluded: %s" % ', '.join(sorted(exclude_names_from_path)))
        exclude_names.update(exclude_names_from_path)
    exclude_names, unknown_names = _classify_names(distro_name, exclude_names, source=upstream_source_version)
    if unknown_names:
        logger.warn("The following unreleased '--exclude' packages will be ignored: %s" % (', '.join(sorted(unknown_names))))
    if excludes_keywords:
        expanded_names, unknown_names = _classify_names(distro_name, _expand_keywords(distro_name, excludes_keywords), source=upstream_source_version)
        exclude_names.update(expanded_names)
    if excludes:
        logger.debug('Excluded packages: %s' % ', '.join(sorted(exclude_names.package_names)))

    result = copy.deepcopy(names)

    # remove excluded names from the list of names
    result.package_names -= exclude_names.package_names
    if not result.package_names and not has_repos:
        raise RuntimeError('No packages left after applying the exclusions')

    if result.package_names:
        logger.debug('Packages: %s' % ', '.join(sorted(result.package_names)))

    # extend the names with recursive dependencies
    if deps or deps_up_to:
        # add dependencies
        if result.package_names:
            ros_distro = get_cached_distro(distro_name)
            _, unreleased_package_names = get_package_names(ros_distro)
            excludes = exclude_names.package_names | deps_up_to_names.package_names | set(unreleased_package_names)
            result.package_names |= get_recursive_dependencies(ros_distro, result.package_names, excludes=excludes,
                    limit_depth=deps_depth, source=upstream_source_version)
            logger.debug('Packages including dependencies: %s' % ', '.join(sorted(result.package_names)))

    # intersect result with recursive dependencies on
    if deps_up_to:
        # intersect with dependencies on
        if deps_up_to_names.package_names:
            ros_distro = get_cached_distro(distro_name)
            # depends on do not include the names since they are excluded to stop recursion asap
            package_names = get_recursive_dependencies_on(ros_distro, deps_up_to_names.package_names, excludes=names.package_names,
                    limit=result.package_names, source=upstream_source_version)
            # keep all names which are already in the result set
            package_names |= result.package_names & names.package_names
            result.package_names = package_names
        else:
            result.package_names.clear()
        logger.debug('Packages after intersection: %s' % ', '.join(sorted(result.package_names)))

    # exclude passed in names
    if deps_only:
        result.package_names -= set(names.package_names)

    # exclude packages based on build type
    if catkin_only or non_catkin_only:
        ros_distro = get_cached_distro(distro_name)
        for pkg_name in list(result.package_names):
            pkg_xml = ros_distro.get_release_package_xml(pkg_name)
            try:
                pkg = parse_package_string(pkg_xml)
            except InvalidPackage as e:
                logger.warn("The package '%s' has an invalid manifest and will be ignored: %s" % (pkg_name, e))
                result.package_names.remove(pkg_name)
                continue
            build_type = ([e.content for e in pkg.exports if e.tagname == 'build_type'][0]) if 'build_type' in [e.tagname for e in pkg.exports] else 'catkin'
            if catkin_only ^ (build_type == 'catkin'):
                result.package_names.remove(pkg_name)

    # get rosinstall data
    rosinstall_data = []
    if result.package_names or has_repos:
        ros_distro = get_cached_distro(distro_name)
        if upstream_version_tag or upstream_source_version:
            # determine repositories based on package names and passed in repository names
            repos = {}
            for pkg_name in result.package_names:
                if upstream_source_version and ros_distro.source_packages:
                    pkg = ros_distro.source_packages[pkg_name]
                    repos[pkg.repository_name] = ros_distro.repositories[pkg.repository_name]
                else:
                    pkg = ros_distro.release_packages[pkg_name]
                    if pkg.repository_name not in repos:
                        repo = ros_distro.repositories[pkg.repository_name]
                        release_repo = repo.release_repository
                        assert not upstream_version_tag or release_repo.version is not None, "Package '%s' in repository '%s' does not have a release version" % (pkg_name, pkg.repository_name)
                        repos[pkg.repository_name] = repo
            # If asked to get upstream development then the release state doesn't matter
            if upstream_source_version:
                repo_names = repo_names.union(unreleased_repo_names)
            for repo_name in repo_names:
                if repo_name not in repos:
                    repos[repo_name] = ros_distro.repositories[repo_name]
            # ignore repos which lack information
            repos_without_source = [repo_name for repo_name, repo in repos.items() if not repo.source_repository]
            if repos_without_source:
                logger.warn('The following repositories with an unknown upstream will be ignored: %s' % ', '.join(sorted(repos_without_source)))
                [repos.pop(repo_name) for repo_name in repos_without_source]
            if upstream_version_tag:
                repos_without_release = [repo_name for repo_name, repo in repos.items() if not repo.release_repository or not repo.release_repository.version]
                if repos_without_release:
                    logger.warn('The following repositories without a release will be ignored: %s' % ', '.join(sorted(repos_without_release)))
                    [repos.pop(repo_name) for repo_name in repos_without_release]
            logger.debug('Generate rosinstall entries for repositories: %s' % ', '.join(sorted(repos.keys())))
            rosinstall_data += generate_rosinstall_for_repos(repos, version_tag=upstream_version_tag, tar=tar)
        else:
            logger.debug('Generate rosinstall entries for packages: %s' % ', '.join(sorted(result.package_names)))
            rosinstall_data += distro_generate_rosinstall(ros_distro, result.package_names, flat=flat, tar=tar)
    else:
        logger.warn('No packages or repos found')
    return rosinstall_data


def sort_rosinstall(rosinstall_data):
    def _rosinstall_key(item):
        key = list(item.keys())[0]
        return item[key]['local-name']
    return sorted(rosinstall_data, key=_rosinstall_key)
