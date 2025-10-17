from django.conf import settings
from django.core.management.commands import dumpdata
# from django.core.management.base import CommandError

from datetime import datetime
from os import path, makedirs, remove
from time import sleep

from natsort import natsorted
from rahavard import (
    contains_ymd,
    get_list_of_files,
    to_tilda,
)


## https://stackoverflow.com/a/37755287/
class Command(dumpdata.Command):
    help = 'My Customized Version of the Original dumpdata Command'

    ## https://stackoverflow.com/a/78204755/
    def __init__(self, *args, **kwargs):
        kwargs['no_color'] = not kwargs.get('force_color', False)
        super().__init__(*args, **kwargs)

    def handle(self, *args, **options):

        ## dump --------------

        print('>>> Running customized dumpdata\n')

        if not path.exists(settings.FIXTURES_DIR):
            print(f'creating {settings.FIXTURES_DIR}')
            makedirs(settings.FIXTURES_DIR)

        ## include app slug (if any) in output_file
        apps_string = ''
        if args:
            if len(args) == 1:
                apps_string = '--app-'
            else:
                apps_string = '--apps-'

            for _ in args:
                apps_string = f'{apps_string}{_}-'
            apps_string = apps_string.rstrip('-')

        ymdhms = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        extension = 'json'

        ## JUMP_1
        output_file = f'{settings.FIXTURES_DIR}/{settings.HOST_NAME}-{ymdhms}{apps_string}.{extension}'
        print(f'dumping to: {to_tilda(output_file)}')

        options['format'] = extension
        options['indent'] = 2
        options['output'] = output_file
        options['skip_checks'] = True
        options['use_natural_foreign_keys'] = True
        options['use_natural_primary_keys'] = True
        options['verbosity'] = 3
        options['exclude'] = [
            'admin',
            'messages',
            'sessions',

            ## commented because we also need
            ## auth.group and contenttypes.contenttype models
            ## in the fixtures
            # 'auth',
            # 'contenttypes',
        ]

        super().handle(*args, **options)


        ## rotate --------------

        print('getting list of already present fixtures')
        fixtures = get_list_of_files(directory=settings.FIXTURES_DIR, extension=extension)
        fixtures = natsorted([
            _ for _ in fixtures
            if all([
                ## exclude non-fixtures
                ## by making sure file names match pattern in JUMP_1
                settings.HOST_NAME in _,
                contains_ymd(_),
            ])
        ])
        print(f'  count: {len(fixtures)}')

        ## 24: crontab is configured to generate fixtures every hour
        ##     giving us 24 fixtures a day
        ## 90: backup fixtures for 90 days
        LAST_FIXTURES_TO_SKIP = 24 * 90  ## last n fixtures to skip removing

        to_be_removed = fixtures[:-LAST_FIXTURES_TO_SKIP]

        if to_be_removed:
            to_be_removed__len = len(to_be_removed)
            print(f'{to_be_removed__len} to be removed:')
            for idx, tbr in enumerate(to_be_removed, start=1):
                print(f' {idx}/{to_be_removed__len}: removing {tbr}')
                remove(tbr)
                sleep(.1)
