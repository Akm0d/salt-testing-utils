#!/usr/bin/env python
import logging
import subprocess

from argparse import ArgumentParser
from os import chdir, environ, path
from tqdm import trange
from typing import List, Dict

logger = logging.getLogger(__name__)


class Table:
    class KitchenList(set):
        def __init__(self, kitchen_cmd: List[str] = None, env: Dict[str, str] = None, platform: str = None):
            self.platform = platform if platform else ''
            self.env = env
            self.kitchen_cmd = kitchen_cmd if kitchen_cmd else ['kitchen']
            set.__init__(self, {x.decode() for x in
                                subprocess.check_output(self.kitchen_cmd + ['list', '-b', self.platform], stderr=subprocess.PIPE, env=self.env.copy()).split()})
            logger.debug('Fetching list')

        def __str__(self):
            return subprocess.check_output(self.kitchen_cmd + ['list', self.platform], env=self.env.copy()).decode()

    def __init__(self, machines: List[str] = None, nofail: bool = False, kitchen_cmd: List[str] = None,
                 env: Dict[str, str] = None):
        self.platform = ' '.join(machines)
        self.env = env if env else environ
        self.nofail = nofail
        self.list = self.KitchenList(kitchen_cmd, self.env.copy(), platform=self.platform)
        self.process = dict()
        self.kitchen_cmd = kitchen_cmd if kitchen_cmd else ['kitchen']
        if not machines:
            machines = ['']
        for m in machines:
            found = False
            for l in self.list:
                if m in l:
                    self.process[l] = subprocess.Popen(['echo', 'Initialized', l], env=self.env.copy())
                    found = True
            if not found:
                self.process[m] = subprocess.Popen(['echo', 'Initialized', m], env=env.copy())
        self.wait()
        self.active_machine = machines[0] if len(self.process) > 1 else set(self.process.keys()).copy().pop()

    def wait(self):
        """
        Wait for all subprocesses to finish, on fail, give an error and quit
        """
        progress = trange(len(self.process))
        while any(process.poll() is None for process in self.process.values()):
            count = 0
            for machine, process in self.process.items():
                # The return code should be None or 0, otherwise there is a problem
                if not self.nofail:
                    assert not process.poll(), "'{}' Failed with code {}".format(machine, process.returncode)

                if process.poll() is not None:
                    count += 1
            if progress.n != count:
                progress.n = count
                progress.refresh()

        # Double check that all the processes are cleaned up and successful
        if self.nofail:
            assert all(process.wait() is not None for process in self.process.values())
        else:
            assert all(process.wait() == 0 for process in self.process.values())
            progress.n = len(self.process)
            progress.refresh()

        progress.close()

    def create(self, machine: str = ''):
        if not machine:
            machine = self.active_machine
        logger.debug('Creating machine {}'.format(machine if machine else 'ALL'))
        assert self.process[machine].returncode is not None, "'{}' Process is not finished".format(machine)
        self.process[machine] = subprocess.Popen(self.kitchen_cmd + ['create', machine], env=self.env.copy(), )

    def create_all(self):
        for m in self.process.keys():
            self.create(m)
        self.wait()

    def converge(self, machine: str = ''):
        if not machine:
            machine = self.active_machine
        logger.debug('Converging machine {}'.format(machine if machine else 'ALL'))
        assert self.process[machine].returncode is not None, "'{}' Process is not finished".format(machine)
        self.process[machine] = subprocess.Popen(self.kitchen_cmd + ['converge', machine], env=self.env.copy())

    def converge_all(self):
        for m in self.process.keys():
            self.converge(m)
        self.wait()

    def login(self, machine: str):
        if not machine:
            machine = self.active_machine
        logger.debug('Logging into machine {}'.format(machine if machine else 'ALL'))
        assert self.process[machine].returncode is not None, "'{}' Process is not finished".format(machine)
        cmd = self.kitchen_cmd + ['login', machine]
        logger.debug('CMD: ' + ' '.join(cmd))
        blocked_call = subprocess.Popen(cmd, env=self.env.copy())
        blocked_call.wait()

    def verify(self, machine: str = '', test: str = ''):
        if not machine:
            machine = self.active_machine
        logger.debug(
            'Running tests in {} on {}'.format(test if test else 'salt://tests', machine if machine else 'ALL'))
        assert self.process[machine].returncode is not None, "'{}' Process is not finished".format(machine)
        self.env['KITCHEN_TESTS'] = test
        self.process[machine] = subprocess.Popen(self.kitchen_cmd + ['verify', machine], env=self.env.copy())

    def verify_all(self, test: str = ''):
        for m in self.process.keys():
            self.verify(machine=m, test=test)
        self.wait()

    def destroy(self, machine: str = ''):
        if not machine:
            machine = self.active_machine
        logger.debug('Destroying machine {}'.format(machine if machine else 'ALL'))
        assert self.process[machine].returncode is not None, "'{}' Process is not finished".format(machine)
        self.process[machine] = subprocess.Popen(self.kitchen_cmd + ['destroy', machine], env=self.env.copy())

    def destroy_all(self):
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

    table = Table(args.machine, nofail=args.no_fail, env=environ)
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
        print(table.list)
        if args.list:
            exit(0)
        # Cleanup
        if (do_all and not args.preserve) or (
                args.destroy and not any(flag for flag in [args.create, args.converge, args.verify, args.list])):
            table.destroy_all()

    logger.info("DONE!")
