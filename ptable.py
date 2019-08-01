#!/usr/bin/env python
import logging
import pexpect

from argparse import ArgumentParser
from os import chdir, environ, path
from sys import stdout
from time import sleep
from typing import List, Dict

logger = logging.getLogger(__name__)

PS1 = 'AWAITING NEXT COMMAND: '


class Table:
    def __init__(self, platform: str = None, nofail: bool = False, kitchen_cmd: List[str] = None,
                 shell: str = 'sh', env: Dict[str, str] = None, pre_cmd: List[str] = None, init_cmd: List[str] = None):
        logger.debug("Setting Table")
        if env:
            environ.update(env)
        if not pre_cmd:
            pre_cmd = []
        if not init_cmd:
            init_cmd = []
        self.log_base = '/var/log/table/'
        self.kitchen_cmd = kitchen_cmd if kitchen_cmd else ['kitchen']
        self.local_shell = self.init_shell(pexpect.spawn(shell, env=environ.copy(),
                                                         logfile=stdout.buffer),
                                           pre_cmd + init_cmd)
        logger.debug('Initialized local shell')

        self.nofail = nofail
        self.list = set(self.exec(' '.join(self.kitchen_cmd + ['list', '-b'])).split())

        self.platform = None
        # Handle a partial or incomplete platform name
        for l in self.list:
            if platform in l:
                self.process = self.init_shell(pexpect.spawn(shell, env=environ.copy(),
                                                             logfile=stdout.buffer), pre_cmd)
                self.platform = l
        if not self.platform:
            self.process = self.init_shell(pexpect.spawn(shell, env=environ.copy(),
                                                         logfile=stdout.buffer), pre_cmd)
            self.platform = platform

        self.wait()
        logger.debug("Table Ready")

    def __str__(self):
        return self.exec(' '.join(self.kitchen_cmd + ['list', self.platform]))

    def init_shell(self, shell: pexpect.pty_spawn, pre_cmd: List[str]):
        shell.sendline('export PS1="{}"'.format(PS1))
        shell.expect('.*')
        shell.sendline('')
        shell.expect_exact(PS1)
        shell.expect_exact(PS1)

        if pre_cmd:
            logger.debug('executing pre commands')
            for cmd in pre_cmd:
                self.exec(cmd, shell=shell)
        return shell

    def exec(self, command: str = '', shell: pexpect.pty_spawn = None) -> str:
        logger.debug("Executing command: {}".format(command))
        if not shell:
            shell = self.local_shell
        shell.expect('.*')
        shell.sendline('')
        shell.expect_exact(PS1, timeout=1)
        shell.sendline(command)
        shell.expect('\n')
        sleep(1)
        shell.expect_exact(PS1, timeout=None)
        result = str(shell.before.decode()).strip()
        logger.debug("v" * 80)
        logger.debug("Result:\n{}".format(result))
        logger.debug("." * 80)
        return result

    def wait(self):
        """
        Wait for all subprocesses to finish, on fail, give an error and quit
        """
        self.process.sendline('')
        self.process.expect(PS1)

    def create(self):
        logger.debug('Creating machine {}'.format(self.platform))
        self.exec(' '.join(self.kitchen_cmd + ['create', self.platform]), shell=self.process)

    def converge(self):
        logger.debug('Converging machine {}'.format(self.platform))
        self.exec(' '.join(self.kitchen_cmd + ['converge', self.platform]), shell=self.process)

    def login(self):
        logger.debug('Logging into machine {}'.format(self.platform))
        self.exec(' '.join(self.kitchen_cmd + ['login', self.platform]), shell=self.process)
        print(PS1, end='')
        self.process.interact()

    def verify(self, test: str = ''):
        logger.debug(
            'Running tests in {} on {}'.format(test if test else 'salt://tests', self.platform))
        environ['KITCHEN_TESTS'] = test
        # TODO Add option or try/except for the following environment variables
        environ['DONT_DOWNLOAD_ARTEFACTS'] = '1'
        # environ['ONLY_DOWNLOAD_ARTEFACTS'] = '1'
        logger.debug("Environment: {}".format(environ))

        self.exec(';'.join('export {}="{}"'.format(k, v) for k, v in environ.items()), shell=self.process)
        self.exec(' '.join(self.kitchen_cmd + ['verify', self.platform]), shell=self.process)

    def destroy(self):
        logger.debug('Destroying machine {}'.format(self.platform))
        self.exec(' '.join(self.kitchen_cmd + ['destroy', self.platform]), shell=self.process)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    parser = ArgumentParser(description='Wrapper around kitchen-salt')
    parser.add_argument('-r', '--root', type=str, help=' full path to the salt repo root',
                        default=path.expanduser('~/PycharmProjects/salt'))
    parser.add_argument('platform', type=str, help='The specific platforms to run on', default=[], nargs='*')
    parser.add_argument('-t', '--test', type=str, action='append', default=[],
                        help='A specific test to run relative to the salt repo root')
    parser.add_argument('-l', '--list', action='store_true', help='list the available machines and exit')
    parser.add_argument('-c', '--create', action='store_true', help='Create the named machines and exit')
    parser.add_argument('-E', '--expensive', action='store_true', help='Perform expensive tests')
    parser.add_argument('-C', '--converge', action='store_true', help='Converge the named machines and exit')
    parser.add_argument('-L', '--login', action='store_true', help='Log into the named machine and exit', default='')
    parser.add_argument('-v', '--verify', action='store_true', help='Verify the named machines and exit')
    parser.add_argument('-d', '--destroy', action='store_true', help='Destroy the named machines and exit')
    parser.add_argument('-n', '--no-fail', action='store_true', help="Don't stop on failure")
    parser.add_argument('-p', '--preserve', action='store_true', help='Keep the named machines after the operations')
    args = parser.parse_args()
    logger.debug("ARGS: {}".format(args))

    # Change working directory to the salt root
    logger.debug("cd {}".format(args.root))
    chdir(args.root)

    # Configure Verification environment
    logger.debug("Expensive tests: {}".format(args.expensive))
    environ['EXPENSIVE_TESTS'] = str(args.expensive)
    # FIXME Does this work on a nox branch?
    if args.expensive:
        environ['NOX_PASSTHROUGH_OPTS'] = '--run-expensive'

    table = Table(args.platform, nofail=args.no_fail)
    # If all the flags are false, then we will do all of them
    do_all = all(not flag for flag in [args.create, args.converge, args.verify, args.destroy, args.list, args.login])
    try:
        if do_all or args.create:
            table.create()
        if do_all or args.converge:
            table.create()
        if args.login:
            table.login()
            args.preserve = True
        if do_all or args.verify:
            if args.test:
                for t in args.test:
                    table.verify(t)
            else:
                table.verify()
    finally:
        print(table)
        if args.list:
            exit(0)
        # Cleanup
        if (do_all and not args.preserve) or (
                args.destroy and not any(flag for flag in [args.create, args.converge, args.verify, args.list])):
            table.destroy_all()

    logger.info("DONE!")
