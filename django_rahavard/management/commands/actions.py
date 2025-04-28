from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

from getpass import getpass
from signal import SIGINT, signal
from subprocess import run
from time import sleep

from rahavard import (
    abort,
    colorize,
    get_command,
    get_command_log_file,
    keyboard_interrupt_handler,
    save_log,
)


ACTION_OPTIONS = [
    'dumpdata',
    'collectstatic',
    'check-deploy',

    'renew',
    'update',
    'check-trace',
]


signal(SIGINT, keyboard_interrupt_handler)


class Command(BaseCommand):
    help = 'Actions'

    def add_arguments(self, parser):
        parser.add_argument(
            '-a',
            '--action',
            default=None,
            type=str,
            help=f'action (options: {",".join(ACTION_OPTIONS)})',
        )

    def handle(self, *args, **kwargs):
        action = kwargs.get('action')

        if not action:
            return abort(self, 'no action specified')

        if action not in ACTION_OPTIONS:
            return abort(self, 'invalid action')

        command  = get_command(full_path=__file__, drop_extention=True)
        log_file = get_command_log_file(f'{command}--{action}')
        ## .../actions--renew.log

        if action in ['dumpdata', 'collectstatic', 'check-deploy']:
            try:
                call_command(action)
            except Exception as exc:
                save_log(self, command, settings.HOST_NAME, log_file, f'action={action}: {exc!r}')
        ## -----------------------------------
        elif action == 'renew':
            cmd = run(
                'sudo certbot renew',
                shell=True,
                universal_newlines=True,
                capture_output=True,
            )
            cmd_ext_stts = cmd.returncode  ## 0/1/...
            cmd_output   = cmd.stdout.strip()
            cmd_error    = cmd.stderr.strip()

            if cmd_ext_stts == 0:  ## successful
                print(cmd_output)
            elif cmd_ext_stts:
                save_log(self, command, settings.HOST_NAME, log_file, cmd_error)
        ## -----------------------------------
        elif action == 'update':
            gh_username = input('github username: ').strip()
            gh_token    = getpass('github token: ').strip()

            repo_url = f'https://{gh_username}:{gh_token}@github.com/{gh_username}/{settings.PROJECT_SLUG}.git'
            branch = 'master'

            tuples = [
                ('Fetching...',            f'git -C {settings.PROJECT_DIR} fetch {repo_url} {branch}'),
                ('Pulling...',             f'git -C {settings.PROJECT_DIR} pull  {repo_url} {branch}'),
                ('Restarting apache24...', 'sudo service apache24 restart'),
            ]

            for index, (description, cmd) in enumerate(tuples, start=1):
                print(f'{index}/{len(tuples)} {description}')
                run(cmd, shell=True)
                print('-_'*30)
                sleep(.1)

        ## -----------------------------------
        elif action == 'check-trace':
            cmd = run(
                ## --connect-timeout and --max-time:
                ## https://unix.stackexchange.com/a/94612
                f'curl -v -X TRACE --connect-timeout 20 --max-time 60 {settings.TARCE_URL} 2>&1',
                shell=True,
                universal_newlines=True,
                capture_output=True,
            )
            cmd_ext_stts = cmd.returncode  ## 0/1/...
            cmd_output   = cmd.stdout.strip()
            cmd_error    = cmd.stderr.strip()

            if cmd_ext_stts == 0:  ## successful
                # print(cmd_output)

                ## NOTE 1. although the above cmd has finished successfully,
                ##         we still have to look for the sensitive information
                ##      2. the line containing the sensitive information looks like this, if
                ##         a. it's secure:
                ##            < Server: Apache
                ##         b. it's NOT secure:
                ##            < Server: Apache/1.2.33 (FreeBSD) OpenSSL/1.2.33 mod_wsgi/1.2.33 Python/1.2
                if any([
                    'Server: Apache/' in cmd_output,
                    'OpenSSL/'        in cmd_output,
                    'mod_wsgi/'       in cmd_output,
                    'Python/'         in cmd_output,
                    '(FreeBSD)'       in cmd_output,
                ]):
                    print(colorize(self, 'error', cmd_output))
                    save_log(self, command, settings.HOST_NAME, log_file, cmd_output, echo=False)
                else:
                    print(colorize(self, 'success', 'Everything is safe'))

            elif cmd_ext_stts:
                save_log(self, command, settings.HOST_NAME, log_file, cmd_output)
