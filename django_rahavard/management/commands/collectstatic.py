from django.conf import settings
from django.contrib.staticfiles.management.commands import collectstatic
# from django.core.management.base import CommandError


## https://stackoverflow.com/a/37755287/
class Command(collectstatic.Command):
    help = 'My Customized Version of the Original collectstatic Command'

    ## https://stackoverflow.com/a/78204755/
    def __init__(self, *args, **kwargs):
        kwargs['no_color'] = not kwargs.get('force_color', False)
        super().__init__(*args, **kwargs)

    def handle(self, *args, **options):
        print('>>> Running customized collectstatic\n')

        ## on remote, static and staticfiles directories are constantly changing
        ## so there may be important files present in staticfiles directory 
        ## but absent in static directory
        ## for example 'uploads' or 'dl' directory
        ## so, if we clear staticfiles
        ## only when we are on local machine
        ## everything is safe
        if settings.DEBUG:
            options['clear'] = True

        options['interactive'] = False
        options['ignore_patterns'] = [
            'dl/*',
        ]
        options['verbosity'] = 3

        super().handle(*args, **options)


###############################

## method 2
## the disadvantage with this method is I couldn't find a way to pass args.
## e.g. the command 'manage.py collectstatic --dry-run wont work'

# from django.core.management import call_command
# from django.core.management.base import BaseCommand, CommandError

## https://stackoverflow.com/a/75189544/
# class Command(BaseCommand):
#     help = 'My Customized Version of the Original collectstatic Command'

#     def handle(self, *args, **kwargs):
#         call_command(
#             'collectstatic',
#             ignore_patterns=['dl/*'],
#             clear=True,
#             interactive=False,
#             **kwargs,
#         )
