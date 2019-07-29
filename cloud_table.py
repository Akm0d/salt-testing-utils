#!/usr/bin/env python
import logging
import subprocess
import sysrsync

from argparse import ArgumentParser
from os import path
from ptable import Table

logger = logging.getLogger(__name__)

cloud_env = {
    'NOX_ENV_NAME': 'runtests-cloud',
    'NOX_PASSTHROUGH_OPTS': '',
    'NOX_ENABLE_FROM_FILENAMES': 'false',
    'SALT_KITCHEN_PLATFORMS': 'var/jenkins/workspace/nox-cloud-platforms.yml',
    'SALT_KITCHEN_VERIFIER': '/var/jenkins/workspace/nox-verifier.yml',
    'SALT_KITCHEN_DRIVER': '/var/jenkins/workspace/driver.yml',
    'GOLDEN_IMAGES_CI_BRANCH': 'develop',
    'PATH': '~/.rbenv/shims:/usr/local/rbenv/shims:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/root/bin:/root/bin',
    'RBENV_VERSION': '2.4.2',
    'TEST_SUITE': 'py3',
    'TEST_PLATFORM': 'centos-7',
    'CODECOV_FLAGS': 'centos7,py3',
    'PY_COLORS': '1',
    'FORCE_FULL': 'true',
}

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    parser = ArgumentParser(description='Wrapper around kitchen-salt')
    parser.add_argument('-o', '--cloud', type=str, help='Name of the AWS instance cloud creator', required=True)
    parser.add_argument('-R', '--local-root', type=str, help='full path to the local salt repo root',
                        default=path.expanduser('~/PycharmProjects/salt'))
    parser.add_argument('-r', '--root', type=str, help=' full path to the salt repo root',
                        default=path.expanduser('*/salt'))
#   parser.add_argument('machine', type=str, help='The specific platforms to run on', default=[], nargs='*')
    parser.add_argument('-t', '--test', type=str, action='append', default=[],
                        help='A specific test to run relative to the salt repo root')
    parser.add_argument('-l', '--list', action='store_true', help='list the available machines and exit')
    parser.add_argument('-c', '--create', action='store_true', help='Create the named machines and exit')
    parser.add_argument('-E', '--expensive', action='store_true', help='Perform expensive tests')
    parser.add_argument('-C', '--converge', action='store_true', help='Converge the named machineggjjjkjs and exit')
    parser.add_argument('-L', '--login', action='store_true', help='Log into the named machine and exit', default='')
    parser.add_argument('-v', '--verify', action='store_true', help='Verify the named machines and exit')
    parser.add_argument('-d', '--destroy', action='store_true', help='Destroy the named machines and exit')
    parser.add_argument('-n', '--no-fail', action='store_true', help="Don't stop on failure")
    parser.add_argument('-p', '--preserve', action='store_true', help='Keep the named machines after the operations')
    args = parser.parse_args()
    logger.debug("ARGS: {}".format(args))

    p = subprocess.Popen('ssh -G ' + args.cloud + "|awk '/^hostname / { print $2 }'", shell=True,
                         stdout=subprocess.PIPE)

    instance='py3-centos-7'

    # Sync the local repository with the remote
    sysrsync.run(source=args.local_root,
                 destination=args.root,
                 destination_ssh=args.cloud,
                 options=['-a', '-v', '--delete'],
                 exclusions=['.git', '.idea', '*.swp'],
                 sync_source_contents=True,
                 verbose=True, )

    # Configure Verification environment
    logger.debug("Expensive tests: {}".format(args.expensive))
    cloud_env['EXPENSIVE_TESTS'] = str(args.expensive)
    # FIXME Does this work on a nox branch?
    if args.expensive:
        cloud_env['NOX_PASSTHROUGH_OPTS'] = '--run-expensive'

    # Set the shell on the cloud host to /bin/sh
    table = Table(['py3-centos-7'], nofail=args.no_fail, kitchen_cmd=['bundle', 'exec', 'kitchen'],
                  shell='ssh {}'.format(args.cloud, args.root).format(args.cloud),
                  init_cmd=[
                      'bundle install --with ec2 windows --without docker macos opennebula vagrant',
                      'bundle update',
                  ],
                  pre_cmd=[
                      'cd {}'.format(args.root),
                      ';'.join('export {}="{}"'.format(k, v) for k, v in cloud_env.items()),
                  ])

    # If all the flags are false, then we will do all of them
    do_all = all(not flag for flag in [args.create, args.converge, args.verify, args.destroy, args.list, args.login])
    try:
        if do_all or args.create or args.login:
            table.create(instance)
        if do_all or args.converge or args.login:
            table.exec("ssh-agent /bin/bash -c 'ssh-add ~/.ssh/kitchen.pem; bundle exec kitchen converge {}'".format(instance),
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
