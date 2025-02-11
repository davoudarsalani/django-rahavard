from django.core.management.commands import check
# from django.core.management.base import CommandError


## https://stackoverflow.com/a/37755287/
class Command(check.Command):
    help = 'My Customized Version of the Original check Command'

    ## https://stackoverflow.com/a/78204755/
    def __init__(self, *args, **kwargs):
        kwargs['no_color'] = not kwargs.get('force_color', False)
        super().__init__(*args, **kwargs)

    def handle(self, *args, **options):
        print('>>> Running customized check')

        options['deploy'] = True
        options['verbosity'] = 3

        super().handle(*args, **options)
