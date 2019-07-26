#!/usr/bin/env python
import logging
import subprocess
from time import sleep

import pexpect
from argparse import ArgumentParser
from os import chdir, environ, path
from typing import List, Dict

logger = logging.getLogger(__name__)

PS1 = 'AWAITING NEXT COMMAND: '


class Table:
    def __init__(self, machines: List[str] = None, nofail: bool = False, kitchen_cmd: List[str] = None,
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
                                           logfile=open('{}tablesh.log'.format(self.log_base), 'wb+')), pre_cmd + init_cmd)
        logger.debug('Initialized local shell')

        self.nofail = nofail
        self.list = set(self.exec(' '.join(self.kitchen_cmd + ['list', '-b'])).split())
        self.process = dict()
        if not machines:
            machines = ['']
        for m in machines:
            found = False
            for l in self.list:
                if m in l:
                    self.process[l] = self.init_shell(pexpect.spawn(shell, env=environ.copy(),
                                                      logfile=open('{}{}.log'.format(self.log_base, l), 'wb+')), pre_cmd)
                    found = True
            if not found:
                self.process[m] = self.init_shell(pexpect.spawn(shell, env=environ.copy(),
                                                  logfile=open('{}{}.log'.format(self.log_base, m), 'wb+')), pre_cmd)
        self.wait()
        self.active_machine = set(self.process.keys()).copy().pop()
        logger.debug("Table Ready")

    def __str__(self):
        return self.exec(' '.join(self.kitchen_cmd + ['list']))

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
        for machine, process in self.process.items():
            process.sendline('')
            process.expect(PS1)

    def create(self, machine: str = ''):
        logger.debug('Creating machine {}'.format(machine if machine else 'ALL'))
        self.exec(' '.join(self.kitchen_cmd + ['create', machine]), shell=self.process[machine])

    def create_all(self):
        for m in self.process.keys():
            self.create(m)
        self.wait()

    def converge(self, machine: str = ''):
        logger.debug('Converging machine {}'.format(machine if machine else 'ALL'))
        self.exec(' '.join(self.kitchen_cmd + ['converge', machine]), shell=self.process[machine])

    def converge_all(self):
        for m in self.process.keys():
            self.converge(m)
        self.wait()

    def login(self, machine: str):
        logger.debug('Logging into machine {}'.format(machine if machine else 'ALL'))
        self.exec(' '.join(self.kitchen_cmd + ['login', machine]), shell=self.process[machine])
        print(PS1, end='')
        self.process[machine].interact()

    def verify(self, machine: str = '', test: str = ''):
        logger.debug(
            'Running tests in {} on {}'.format(test if test else 'salt://tests', machine if machine else 'ALL'))
        environ['KITCHEN_TESTS'] = test
        logger.debug("Environment: {}".format(environ))

        self.exec(';'.join('export {}="{}"'.format(k, v) for k, v in environ.items()), shell=self.process[machine])
        self.exec(' '.join(self.kitchen_cmd + ['verify', machine]), shell=self.process[machine])

    def verify_all(self, test: str = ''):
        for m in self.process.keys():
            self.verify(machine=m, test=test)
        self.wait()

    def destroy(self, machine: str = ''):
        logger.debug('Destroying machine {}'.format(machine if machine else 'ALL'))
        self.exec(' '.join(self.kitchen_cmd + ['destroy', machine]), shell=self.process[machine])

    def destroy_all(self, thorough=False):
        if thorough:
            self.exec(' '.join(self.kitchen_cmd + ['destroy']))
        else:
            for m in self.process.keys():
                self.destroy(m)
            self.wait()


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    parser = ArgumentParser(description='Wrapper around kitchen-salt')
    parser.add_argument('-r', '--root', type=str, help=' full path to the salt repo root',
                        default=path.expanduser('~/PycharmProjects/salt'))
    parser.add_argument('machine', type=str, help='The specific platforms to run on', default=[], nargs='*')
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

    table = Table(args.machine, nofail=args.no_fail)
    # If all the flags are false, then we will do all of them
    do_all = all(not flag for flag in [args.create, args.converge, args.verify, args.destroy, args.list, args.login])
    try:
        if do_all or args.create:
            table.create_all()
        if do_all or args.converge:
            table.converge_all()
        if args.login:
            table.login(table.active_machine)
            args.preserve = True
        if do_all or args.verify:
            if args.test:
                for t in args.test:
                    table.verify_all(t)
            else:
                table.verify_all()
    finally:
        print(table)
        if args.list:
            exit(0)
        # Cleanup
        if (do_all and not args.preserve) or (
                args.destroy and not any(flag for flag in [args.create, args.converge, args.verify, args.list])):
            table.destroy_all()

    logger.info("DONE!")
