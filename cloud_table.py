#!/usr/bin/env python
import logging
import subprocess
import sysrsync

from argparse import ArgumentParser
from os import path
from ptable import Table

logger = logging.getLogger(__name__)

transport = 'ZeroMQ'
cloud_env = {
    'NOX_ENV_NAME': 'runtests-cloud',
    'NOX_PASSTHROUGH_OPTS': '',
    'NOX_ENABLE_FROM_FILENAMES': 'true',
    'PATH': '~/.rbenv/shims:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/root/bin',
    'PY_COLORS': '1',
    'RBENV_VERSION': '2.4.2',
# TODO Find out if these are needed for running the tests in docker
#   'SALT_KITCHEN_PLATFORMS': 'var/jenkins/workspace/nox-cloud-platforms.yml',
#   'SALT_KITCHEN_VERIFIER': '/var/jenkins/workspace/nox-verifier.yml',
#   'SALT_KITCHEN_DRIVER': '/var/jenkins/workspace/driver.yml',
}

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    parser = ArgumentParser(description='Wrapper around kitchen-salt')

    setup = parser.add_argument_group('Setup')
    setup.add_argument('-o', '--cloud', type=str, help='SSH username@IP of the AWS instance/cloud creator', required=True, )
    setup.add_argument('-R', '--local-root', type=str, help='full path to the local salt repo root',
                       default=path.expanduser('~/PycharmProjects/salt'))
    setup.add_argument('-r', '--root', type=str, help=' full path to the salt repo root',
                       default=path.expanduser('*/salt'))
    setup.add_argument('platform', type=str, default='py3-centos-7', nargs='?',
                       help='The specific platform to run on.  Run this script with --list to see available platforms')

    tests = parser.add_argument_group('Test Options')
    tests.add_argument('-t', '--test', type=str, action='append', default=[],
                       help='A specific test to run relative to the salt repo root')
    tests.add_argument('-E', '--expensive', action='store_true', help='Perform expensive tests')
    tests.add_argument('-n', '--no-fail', action='store_true', help="Don't stop on failure")

    actions = parser.add_argument_group('Instance Actions')
    actions.add_argument('-l', '--list', action='store_true', help='list the available machines and exit')
    actions.add_argument('-c', '--create', action='store_true', help='Create the named machines and exit')
    actions.add_argument('-C', '--converge', action='store_true', help='Converge the named machines and exit')
    actions.add_argument('-v', '--verify', action='store_true', help='Verify the named machines and exit')
    actions.add_argument('-d', '--destroy', action='store_true', help='Destroy the named machines and exit')
    actions.add_argument('-L', '--login', action='store_true', help='Log into the named machine and exit', default='')
    actions.add_argument('-p', '--preserve', action='store_true', help='Keep the named machines after the operations')

    args = parser.parse_args()
    logger.debug("ARGS: {}".format(args))

    # Grab the IP address from the ssh target
    p = subprocess.Popen('ssh -G ' + args.cloud + "|awk '/^hostname / { print $2 }'", shell=True,
                         stdout=subprocess.PIPE)

    # Sync the local repository with the remote
    sysrsync.run(source=args.local_root,
                 destination=args.root,
                 destination_ssh=args.cloud,
                 options=['-a', '-v', '--delete'],
                 exclusions=['.git', '.idea', '*.swp'],
                 sync_source_contents=True,
                 verbose=True, )

    # TODO Verify correct rbenv is installed
    # TODO install rbenv if needed
    # TODO verify bundle, kitchen, and GemFile are usable. Install missing things
    # TODO verify docker is installed and service running

    # Configure Verification environment
    logger.debug("Expensive tests: {}".format(args.expensive))
    cloud_env['EXPENSIVE_TESTS'] = str(args.expensive)
    if args.expensive:
        cloud_env['NOX_PASSTHROUGH_OPTS'] = '--run-expensive'

    # Set the shell on the cloud host to /bin/sh
    table = Table([args.platform], nofail=args.no_fail, kitchen_cmd=['bundle', 'exec', 'kitchen'],
                  shell='ssh {}'.format(args.cloud, args.root).format(args.cloud),
                  init_cmd=[
                      'bundle install --without ec2 windows macos opennebula vagrant --with docker',
                      'bundle update',
                  ],
                  pre_cmd=[
                      'cd {}'.format(args.root),
                      ';'.join('export {}="{}"'.format(k, v) for k, v in cloud_env.items()),
                  ])
    instance = table.active_machine

    # Add cloud options based on the instance name
    distro, version, pyver = instance.split('-')
    cloud_env['CODECOV_FLAGS'] = '{distro}{version},{py},{transport}'.format(
        distro=distro, version=version, py=pyver, transport=transport
    )
    cloud_env['TEST_SUITE'] = pyver
    cloud_env['TEST_PLATFORM'] = distro
    cloud_env['TEST_TRANSPORT'] = transport

    # If all the flags are false, then we will do all of them
    do_all = all(not flag for flag in [args.create, args.converge, args.verify, args.destroy, args.list, args.login])
    try:
        if do_all or args.create or args.login:
            table.create(instance)
        if do_all or args.converge or args.login:
            table.exec(
                "ssh-agent /bin/bash -c 'ssh-add ~/.ssh/kitchen.pem; bundle exec kitchen converge {}'".format(instance),
                shell=table.process[instance])
        if args.login:
            table.login(instance)
            args.preserve = True
        if do_all or args.verify:
            if args.test:
                for t in args.test:
                    table.verify(instance, t)
            else:
                table.verify(instance)
    finally:
        print(table)
        if args.list:
            exit(0)
        # Cleanup
        if args.destroy:
            table.destroy_all(args.preserve)
        elif do_all and not args.preserve:
            table.destroy_all(True)

    logger.info("DONE!")
