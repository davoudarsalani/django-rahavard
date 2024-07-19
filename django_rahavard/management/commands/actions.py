from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

from datetime import datetime
from getpass import getpass
from json import dumps
from os import listdir, path, remove, stat, walk
from shutil import rmtree
from signal import SIGINT, signal
from subprocess import run
from time import sleep, time

from natsort import natsorted
from rahavard import (
    DU_CMD,
    MAX_FAKE_LOGS,
    SECONDS_PER_DAY,
    abort,
    add_yearmonthday_firstn_lastn_wipeout,
    colorize,
    contains_ymd,
    is_ymd,
    get_command,
    get_list_of_files,
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
            '-d',
            '--demo',
            default=False,
            action='store_true',
            help="whether it is for demo (used along with '--action=parse --batch=...')",
        )

        parser.add_argument(
            '-c',
            '--clean-demo',
            default=False,
            action='store_true',
            help="remove everything and re-create logs before parsing (used along with '--action=parse --batch=... --demo')",
        )

        parser.add_argument(
            '-o',
            '--only',
            default=[],
            nargs='+',
            type=str,
            help="only (used along with '--action=parse --batch=... [--demo]')",
        )

        parser.add_argument(
            '-e',
            '--exclude',
            default=[],
            nargs='+',
            type=str,
            help="exclude (used along with '--action=parse --batch=... [--demo]'). Note: it overrides -o|--only args",
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

        action     = kwargs.get('action')
        batch      = kwargs.get('batch')
        demo       = kwargs.get('demo')
        clean_demo = kwargs.get('clean_demo')
        only       = kwargs.get('only')
        exclude    = kwargs.get('exclude')

        #############################################################

        if not action:
            return abort(self, 'no action specified')

        if action not in ACTION_OPTIONS:
            return abort(self, 'invalid action')

        command = get_command(full_path=__file__, drop_extention=True)

        ERROR_FILE = f'{settings.PROJECT_DIR}/{command}-error-{action}'
        ## .../PROJECT_SLUG/actions-error-backup

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
                opened.write(dumped)
        ## -----------------------------------
        elif action == 'parse':
            if not batch:
                return abort(self, 'no batch specified')

            if batch not in BATCH_OPTIONS:
                return abort(self, 'invalid batch')

            ## prepare logs for demo
            if all([
                settings.IS_DEMO,  ## to make sure we are on demo server
                demo,
                batch == 'one',
            ]):
                if clean_demo  :
                    ## STEP 1
                    if path.exists(settings.LOGS_DIR):
                        try:
                            print(colorize(self, 'removing', f'removing {to_tilda(settings.LOGS_DIR)}'))
                            rmtree(settings.LOGS_DIR)
                        except Exception as exc:
                            log(self, command, settings.HOST_NAME, ERROR_FILE, f'{exc!r}')

                    ## STEP 2
                    if path.exists(settings.LOGS_PARSED_DIR):
                        try:
                            print(colorize(self, 'removing', f'removing directories inside {to_tilda(settings.LOGS_PARSED_DIR)} (except country)'))
                            for d in listdir(settings.LOGS_PARSED_DIR):  ## d is base (e.g. daemon)
                                if d == 'country':
                                    continue

                                d_fullpath = f'{settings.LOGS_PARSED_DIR}/{d}'
                                if path.exists(d_fullpath):
                                    print(d_fullpath)
                                    rmtree(d_fullpath)
                        except Exception as exc:
                            log(self, command, settings.HOST_NAME, ERROR_FILE, f'{exc!r}')
                else:
                    time_now = time()  ## 1719724664.241052
                    time_n_days_ago = time_now - (MAX_FAKE_LOGS * SECONDS_PER_DAY)  ## 1718515129.1077092

                    ## STEP 1
                    source_logs = get_list_of_files(directory=settings.LOGS_DIR, extension='log')
                    if source_logs:
                        print(colorize(self, 'removing', f'removing logs older than {MAX_FAKE_LOGS} days'))
                        for source_log in source_logs:
                            ## https://stackoverflow.com/q/12485666/
                            file_stamp = stat(source_log).st_mtime  ## 1717757735.0
                            if file_stamp < time_n_days_ago:
                                print(colorize(self, 'removing', f'  removing {to_tilda(source_log)}'))
                                remove(source_log)

                    ## STEP 2
                    if path.exists(settings.LOGS_PARSED_DIR):
                        print(colorize(self, 'removing', f'removing directories inside {to_tilda(settings.LOGS_PARSED_DIR)} older than {MAX_FAKE_LOGS} days'))

                        for root, dirs, files in walk(settings.LOGS_PARSED_DIR, topdown=False):
                            ## root = .../dhcp
                            ## dirs = [] or ['2024-06-04', '2024-05-24', ...]
                            ## files = []

                            for d in dirs:
                                if not is_ymd(d):
                                    continue

                                d_fullpath = f'{root}/{d}'

                                if any([
                                    not path.isdir(d_fullpath),
                                    not contains_ymd(d_fullpath),  ## to prevent deletion of .../dns directory
                                ]):
                                    continue

                                ## https://stackoverflow.com/a/39456407/
                                dir_stamp = path.getmtime(d_fullpath)  ## 1719253780.286523
                                if dir_stamp < time_n_days_ago:
                                    print(colorize(self, 'removing', f'  removing {to_tilda(d_fullpath)}'))
                                    rmtree(d_fullpath)

                try:
                    call_command('create-fake-logs')
                except Exception as exc:
                    log(self, command, settings.HOST_NAME, ERROR_FILE, f'{exc!r}')


            ## JUMP_1
            try:
                if batch == 'one':
                    ## NOTE do NOT if -> elif
                    if is_allowed('parse-switch',        only, exclude): call_command('parse-switch',        **parse_switches)
                    if is_allowed('parse-windowsserver', only, exclude): call_command('parse-windowsserver', **parse_switches)
                    if is_allowed('parse-daemon',        only, exclude): call_command('parse-daemon',        **parse_switches)
                    if is_allowed('parse-filterlog',     only, exclude): call_command('parse-filterlog',     **parse_switches)
                    if is_allowed('parse-router',        only, exclude): call_command('parse-router',        **parse_switches)
                    if is_allowed('parse-routerboard',   only, exclude): call_command('parse-routerboard',   **parse_switches)
                    if is_allowed('parse-squid',         only, exclude): call_command('parse-squid',         **parse_switches)
                    if is_allowed('parse-useraudit',     only, exclude): call_command('parse-useraudit',     **parse_switches)
                    if is_allowed('parse-userwarning',   only, exclude): call_command('parse-userwarning',   **parse_switches)
                    if is_allowed('parse-vmware',        only, exclude): call_command('parse-vmware',        **parse_switches)
                elif batch == 'two':
                    ## NOTE do NOT if -> elif
                    if is_allowed('fetch-malicious',     only, exclude): call_command('fetch-malicious')                  ## NOTE keep above dns
                    if is_allowed('parse-snort',         only, exclude): call_command('parse-snort',   **parse_switches)  ## <--,-- NOTE keep above dhcp and dns
                    if is_allowed('update-snort',        only, exclude): call_command('update-snort')                     ## <--'
                    if is_allowed('parse-dhcp',          only, exclude): call_command('parse-dhcp',    **parse_switches)  ## <--,-- NOTE keep below snort
                  # if is_allowed('update-dhcp',         only, exclude): call_command('update-dhcp')                      ## <--'
                    if is_allowed('parse-dns',           only, exclude): call_command('parse-dns',     **parse_switches)  ## NOTE keep below snort and malicious
                    if is_allowed('update-dns',          only, exclude): call_command('update-dns')
                    if is_allowed('parse-general',       only, exclude): call_command('parse-general', **parse_switches)
                    ## -----------------
                  # if is_allowed('rotate',              only, exclude): call_command('rotate')
            except Exception as exc:
                log(self, command, settings.HOST_NAME, ERROR_FILE, f'{exc!r}')
