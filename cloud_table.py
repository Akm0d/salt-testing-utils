#!/usr/bin/env python
import logging
import subprocess

from argparse import ArgumentParser
from os import environ, path, chdir
from table import Table

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
    cloud_env.update(environ)
    logging.basicConfig(level=logging.DEBUG)

    parser = ArgumentParser(description='Wrapper around kitchen-salt')

    setup = parser.add_argument_group('Setup')
    setup.add_argument('-r', '--root', type=str, help='full path to the dev salt repo root',
                       default=path.expanduser('~/PycharmProjects/salt'))
    setup.add_argument('-p', '--platform', type=str, default='py3-centos-7',
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
    # This one is helpful if you are running --verify multiple times without any code changes
    actions.add_argument('-R', '--preserve', action='store_true', help='Keep the named machines after the operations')

    args = parser.parse_args()
    chdir(args.root)
    logger.debug("ARGS: {}".format(args))

    # TODO Verify correct rbenv is installed
    # TODO install rbenv if needed
    # TODO verify bundle, kitchen, and GemFile are usable. Install missing things

    # Run bundle update
    logger.debug("Installing bundle from Gemfile")
    if subprocess.Popen(['bundle', 'install'], env=cloud_env.copy()).wait():
        logger.debug("Updating bundle from Gemfile")
        subprocess.Popen(['bundle', 'update'], env=cloud_env.copy()).wait()

    # TODO verify docker is installed and service running

    # Configure Verification environment
    logger.debug("Expensive tests: {}".format(args.expensive))
    cloud_env['EXPENSIVE_TESTS'] = str(args.expensive)
    if args.expensive:
        cloud_env['NOX_PASSTHROUGH_OPTS'] = '--run-expensive'

    # Set the shell on the cloud host to /bin/sh
    table = Table([args.platform], nofail=args.no_fail, kitchen_cmd=['bundle', 'exec', 'kitchen'],
                  env=cloud_env)
    instance = table.active_machine

    # Add cloud options based on the instance name
    distro, version, pyver = instance.split('-')
    table.env['CODECOV_FLAGS'] = '{distro}{version},{py},{transport}'.format(
        distro=distro, version=version, py=pyver, transport=transport
    )
    table.env['TEST_SUITE'] = pyver
    table.env['TEST_PLATFORM'] = distro
    table.env['TEST_TRANSPORT'] = transport

    # If all the flags are false, then we will do all of them
    do_all = all(not flag for flag in [args.create, args.converge, args.verify, args.destroy, args.list, args.login])
    try:
        if do_all or args.create or args.login:
            table.create()
            table.wait()
        if do_all or args.converge or args.login:
            table.converge()
        table.wait()
        if args.login:
            table.login(instance)
            args.preserve = True
            table.wait()
        if do_all or args.test or args.verify:
            if args.test:
                for t in args.test:
                    table.verify(test=t)
            else:
                table.verify()
            table.wait()
    finally:
        print(table.list)
        if args.list:
            exit(0)
        # Cleanup
        if args.destroy:
            table.destroy()
        elif do_all and not args.preserve:
            table.destroy()
        table.wait()

    logger.info("DONE!")
