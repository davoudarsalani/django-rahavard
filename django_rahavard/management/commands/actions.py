from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

from datetime import datetime
from getpass import getpass
from json import dumps
from os import path
from signal import SIGINT, signal
from subprocess import run
from time import sleep

from natsort import natsorted
from rahavard import (
    DU_CMD,
    abort,
    add_yearmonthday_firstn_lastn_wipeout,
    colorize,
    get_command,
    get_command_log_file,
    is_allowed,
    keyboard_interrupt_handler,
    log,
    to_tilda,
)


ACTION_OPTIONS = [
    'dumpdata',
    'collectstatic',
    'check-deploy',

    'renew',
    'update',
    'check-trace',

    ## only on log analyzer
    'backup',
    'storage',
    'parse',
    'hourly-parse',
]
BATCH_OPTIONS = [
    'one',
    'two',
]


signal(SIGINT, keyboard_interrupt_handler)


class Command(BaseCommand):
    help = 'Actions'

    def add_arguments(self, parser):
        add_yearmonthday_firstn_lastn_wipeout(parser)

        parser.add_argument(
            '-a',
            '--action',
            default=None,
            type=str,
            help=f'action (options: {",".join(ACTION_OPTIONS)})',
        )

        parser.add_argument(
            '-b',
            '--batch',
            default=None,
            type=str,
            help=f'batch to be parsed (options: {",".join(BATCH_OPTIONS)})',
        )

        parser.add_argument(
            '-o',
            '--only',
            default=[],
            nargs='+',
            type=str,
            help="only (used along with '--action=parse --batch=...')",
        )

        parser.add_argument(
            '-e',
            '--exclude',
            default=[],
            nargs='+',
            type=str,
            help="exclude (used along with '--action=parse --batch=...'). Note: it overrides -o|--only args",
        )

    def handle(self, *args, **kwargs):
        year_months     = kwargs.get('year_months')
        year_month_days = kwargs.get('year_month_days')

        start_year_month     = kwargs.get('start_year_month')
        start_year_month_day = kwargs.get('start_year_month_day')

        end_year_month     = kwargs.get('end_year_month')
        end_year_month_day = kwargs.get('end_year_month_day')

        first_n = kwargs.get('first_n')
        last_n  = kwargs.get('last_n')

        wipe_out = kwargs.get('wipe_out')

        if year_months:     year_months     = natsorted(set(year_months))
        if year_month_days: year_month_days = natsorted(set(year_month_days))

        if start_year_month and end_year_month:
            ## make sure start_year_month precedes end_year_month in time
            if start_year_month >= end_year_month:
                end_year_month = None

        if start_year_month_day and end_year_month_day:
            ## make sure start_year_month_day precedes end_year_month_day in time
            if start_year_month_day >= end_year_month_day:
                end_year_month_day = None

        ## to be used in JUMP_1
        parse_switches = {
            'year_months':          year_months,
            'year_month_days':      year_month_days,
            'start_year_month':     start_year_month,
            'start_year_month_day': start_year_month_day,
            'end_year_month':       end_year_month,
            'end_year_month_day':   end_year_month_day,
            'first_n':              first_n,
            'last_n':               last_n,
            'wipe_out':             wipe_out,
        }

        action  = kwargs.get('action')
        batch   = kwargs.get('batch')
        only    = kwargs.get('only')
        exclude = kwargs.get('exclude')

        #############################################################

        if not action:
            return abort(self, 'no action specified')

        if action not in ACTION_OPTIONS:
            return abort(self, 'invalid action')

        command = get_command(full_path=__file__, drop_extention=True)

        ERROR_FILE = get_command_log_file(f'{command}--{action}')
        ## .../actions--backup.log

        if action in ['dumpdata', 'collectstatic', 'check-deploy']:
            try:
                call_command(action)
            except Exception as exc:
                log(self, command, settings.HOST_NAME, ERROR_FILE, f'{exc!r}')
        ## -----------------------------------
        elif action == 'renew':
            cmd = run(
                'sudo certbot renew',
                shell=True,
                universal_newlines=True,
                capture_output=True,
            )
            cmd_output   = cmd.stdout.strip()
            cmd_error    = cmd.stderr.strip()
            cmd_ext_stts = cmd.returncode  ## 0/1/...
            if not cmd_ext_stts:  ## successful
                print(cmd_output)
            elif cmd_ext_stts:
                log(self, command, settings.HOST_NAME, ERROR_FILE, cmd_error)
        ## -----------------------------------
        elif action == 'update':
            gh_username = input('github username: ')
            gh_token    = getpass('github token: ')

            repo_url = f'https://{gh_username}:{gh_token}@github.com/{gh_username}/{settings.PROJECT_SLUG}.git'
            branch = 'master'

            ## commands
            git_pull       = f'git -C "{settings.PROJECT_DIR}" pull {repo_url} {branch}'
            draw_line      = 'echo "=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-="'
            restart_apache = 'sudo service apache24 restart'

            run(f'{git_pull} && {draw_line} && {restart_apache}', shell=True)
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
            cmd_output   = cmd.stdout.strip()
            cmd_error    = cmd.stderr.strip()
            cmd_ext_stts = cmd.returncode  ## 0/1/...
            if not cmd_ext_stts:  ## successful
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
                    log(self, command, settings.HOST_NAME, ERROR_FILE, cmd_output, echo=False)
                else:
                    print(colorize(self, 'success', 'Everything is safe'))

            elif cmd_ext_stts:
                log(self, command, settings.HOST_NAME, ERROR_FILE, cmd_output)
        ## -----------------------------------
        elif action == 'backup':
            return None
            exit()

            ## check if another instance of rsync is running
            cmd = run(
                'pgrep "rsync"',
                shell=True,
                universal_newlines=True,
                capture_output=True,
            )  ## 4454 (if finds one, otherwise exits with exit status 1)
            cmd_output   = cmd.stdout.strip()
            cmd_error    = cmd.stderr.strip()
            cmd_ext_stts = cmd.returncode  ## 0/1/...

            ## rsync already running
            if not cmd_ext_stts:
                log(self, command, settings.HOST_NAME, ERROR_FILE, 'rsync is already running')
                exit()

            ## rsync already not running
            else:
                if not path.exists(settings.LOGS_DIR):
                    log(self, command, settings.HOST_NAME, ERROR_FILE, f'{to_tilda(settings.LOGS_DIR)} does not exist')
                    exit()

                ## NOTE:
                ##   excptionally added trailing / to settings.LOGS_DIR
                ##   so that only its content is copied into destination
                ##   rather than the directory itself
                logs_dir_slashed = f'{settings.LOGS_DIR}/'
                cmd = run(
                    f'rsync --archive --progress --delete "{logs_dir_slashed}" "{settings.LOGS_BACKUP_DEST}"',
                    shell=True,
                    universal_newlines=True,
                    capture_output=True,
                )
                cmd_output   = cmd.stdout.strip()
                cmd_error    = cmd.stderr.strip()
                cmd_ext_stts = cmd.returncode  ## 0/1/...
                if not cmd_ext_stts:  ## successful
                    print(cmd_output)
                elif cmd_ext_stts:
                    log(self, command, settings.HOST_NAME, ERROR_FILE, cmd_error)
        ## -----------------------------------
        elif action == 'storage':
            aymdhms = datetime.now().strftime('%a %Y-%m-%d %H:%M:%S')

            errors = []

            HOME_STORAGE        = '?'
            LOGS_STORAGE        = '?'
            LOGS_PARSED_STORAGE = '?'
            LOGS_PARSED_STORAGE__TOPS = '?'

            ## HOME_STORAGE
            cmd = run(
                f'cd ~ && {DU_CMD} .',
                shell=True,
                universal_newlines=True,
                capture_output=True,
            )
            cmd_output   = cmd.stdout.strip()
            cmd_error    = cmd.stderr.strip()
            cmd_ext_stts = cmd.returncode  ## 0/1/...
            if not cmd_ext_stts:  ## successful
                try:
                    HOME_STORAGE = cmd_output.split('\t')[0]
                except Exception as exc:
                    errors.append(f'{exc!r}')
            elif cmd_ext_stts:
                errors.append(cmd_error)

            ## LOGS_STORAGE
            cmd = run(
                f'cd {settings.LOGS_DIR} && {DU_CMD} .',
                shell=True,
                universal_newlines=True,
                capture_output=True,
            )
            cmd_output   = cmd.stdout.strip()
            cmd_error    = cmd.stderr.strip()
            cmd_ext_stts = cmd.returncode  ## 0/1/...
            if not cmd_ext_stts:  ## successful
                try:
                    LOGS_STORAGE = cmd_output.split('\t')[0]
                except Exception as exc:
                    errors.append(f'{exc!r}')
            elif cmd_ext_stts:
                errors.append(cmd_error)

            ## LOGS_PARSED_STORAGE
            cmd = run(
                f'cd {settings.LOGS_PARSED_DIR} && {DU_CMD} .',
                shell=True,
                universal_newlines=True,
                capture_output=True,
            )
            cmd_output   = cmd.stdout.strip()
            cmd_error    = cmd.stderr.strip()
            cmd_ext_stts = cmd.returncode  ## 0/1/...
            if not cmd_ext_stts:  ## successful
                try:
                    LOGS_PARSED_STORAGE = cmd_output.split('\t')[0]
                except Exception as exc:
                    errors.append(f'{exc!r}')
            elif cmd_ext_stts:
                errors.append(cmd_error)


            ## LOGS_PARSED_STORAGE__TOPS
            cmd = run(
                f'cd {settings.LOGS_PARSED_DIR} && {DU_CMD} * | sort -rh',
                shell=True,
                universal_newlines=True,
                capture_output=True,
            )
            cmd_output   = cmd.stdout.strip()
            cmd_error    = cmd.stderr.strip()
            cmd_ext_stts = cmd.returncode  ## 0/1/...
            if not cmd_ext_stts:  ## successful
                try:
                    LOGS_PARSED_STORAGE__TOPS = cmd_output
                except Exception as exc:
                    errors.append(f'{exc!r}')
            elif cmd_ext_stts:
                errors.append(cmd_error)


            if errors:
                for error in errors:
                    log(self, command, settings.HOST_NAME, ERROR_FILE, error)
                    sleep(.1)


            dic = {
                'aymdhms': aymdhms,
                'home_section': {},
                'logs_parsed_tops': {},
            }

            ## keep bases only to prevent revealing absolute paths
            ## e.g. in each line:
            ## 5.4G /foo/bar/baz -> 5.4G baz
            LOGS_DIR__ROOT,        LOGS_DIR__BASE        = path.split(settings.LOGS_DIR)
            LOGS_PARSED_DIR__ROOT, LOGS_PARSED_DIR__BASE = path.split(settings.LOGS_PARSED_DIR)
            #
            dic['home_section'][HOME_STORAGE]        = '~'
            dic['home_section'][LOGS_STORAGE]        = LOGS_DIR__BASE
            dic['home_section'][LOGS_PARSED_STORAGE] = LOGS_PARSED_DIR__BASE

            LOGS_PARSED_STORAGE__TOPS = LOGS_PARSED_STORAGE__TOPS.split('\n')  ## ['11G\tmodule', '2.1G\tgeneral', ...]
            LOGS_PARSED_STORAGE__TOPS = dict(map(lambda item: item.split('\t'), LOGS_PARSED_STORAGE__TOPS))  ## {'11G': 'module', '2.1G': 'general', ...}
            #
            dic['logs_parsed_tops'] = LOGS_PARSED_STORAGE__TOPS

            with open(settings.STORAGE_FILE, 'w') as opened:
                dumped = dumps(dic, indent=2)
                opened.write(dumped + '\n')
        ## -----------------------------------
        elif action == 'parse':
            if not batch:
                return abort(self, 'no batch specified')

            if batch not in BATCH_OPTIONS:
                return abort(self, 'invalid batch')

            if batch == 'one':
                rows = [
                    ('move-auto-logs',      False),

                    ('parse-switch',        True),
                    ('parse-windowsserver', True),
                    ('parse-daemon',        True),
                    ('parse-filterlog',     True),
                    ('parse-router',        True),
                    ('parse-routerboard',   True),
                    ('parse-squid',         True),
                    ('parse-useraudit',     True),
                    ('parse-usernotice',    True),
                    ('parse-userwarning',   True),
                    ('parse-vmware',        True),
                ]
            elif batch == 'two':
                rows = [
                    ('move-auto-logs', False),

                    ## NOTE keep above dhcp and dns
                    ('fetch-cidr',   False),
                    ('parse-snort',  True),

                    ## NOTE keep below snort
                    ('parse-dhcp',  True),

                    ## NOTE keep below snort
                    ('fetch-malicious', False),
                    ('parse-dns',       True),

                    # ('rotate-logs', False),
                ]

            ## JUMP_1
            for command_name, uses_parse_switches in rows:
                if not is_allowed(command_name, only, exclude):
                    continue

                try:
                    if uses_parse_switches:
                        call_command(command_name, **parse_switches)
                    else:
                        call_command(command_name)
                except Exception as exc:
                    log(self, command, settings.HOST_NAME, ERROR_FILE, f'{exc!r}')
        ## -----------------------------------
        elif action == 'hourly-parse':
            for command_name in [
                ## NOTE keep above dhcp and dns
                'hourly-parse-snort',

                ## NOTE keep below snort
                'hourly-parse-dhcp',

                ## NOTE keep below snort
                'hourly-parse-dns',

                'hourly-parse-daemon',
                'hourly-parse-filterlog',
                'hourly-parse-router',
                'hourly-parse-routerboard',
                'hourly-parse-squid',
                'hourly-parse-switch',
                'hourly-parse-useraudit',
                'hourly-parse-usernotice',
                'hourly-parse-userwarning',
                'hourly-parse-vmware',
                'hourly-parse-windowsserver',
            ]:
                if not is_allowed(command_name, only, exclude):
                    continue

                try:
                    call_command(command_name)
                except Exception as exc:
                    log(self, command, settings.HOST_NAME, ERROR_FILE, f'{exc!r}')
