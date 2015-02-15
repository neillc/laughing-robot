'''

Bower Registry API_URL
https://docs.google.com/document/d/17Nzv7onwsFYQU2ompvzNI9cCBczVHntWMiAn4zDip1w

Two modes of operation - one to populate the cache, the other to install 
packages.

Populate Cache:
   Given a list of package specifications either on the command line or in 
   bower.json.
   
   Query bower to find the location of the packages git repo
   
   Clone the repo into the cache if it's not already there.
   
   If it is do a git pull to update?
   
   Extract a zip archive of the specified version into the cache
   
Install a package:
   Use the cache if available
   
   If the package is not in the cache try and add it to the cache
   
   If there is no cache clone the repo to /tmp/bower.py and extract the zip 
   file
   
   Extract the contents of the zip file to <PROJECT_DIR>/bower_templates
   
Use argparse as much as possible for command line shenannigans.
Use pythongit rather than the github api
Options to be more or less verbose



'''

#TODO: Something to test pall ackage specs

import argparse
import os
import re
import sys
import zipfile
import tempfile
import shutil
import json
import logging

import git
from git.util import RemoteProgress
import requests

from bowerlib.github import GitHubRepos

log = logging.getLogger(__name__)


# http://stackoverflow.com/questions/19069093/what-is-the-official-bower-registry-url
API_URL = "https://bower.herokuapp.com"


def locate_component_dir():
    component_dir = 'bower_components'
    if not os.path.exists(component_dir):
        os.makedirs(component_dir)
    return component_dir

class Progess(RemoteProgress):
    def update(self, op_code, cur_count, max_count=None, message=''):
        log.debug('%s %s %s %s', op_code, cur_count, max_count, message)

class InvalidPackageSpecification(Exception):
    def __init__(self, spec):
        self.spec = spec

class Cache(object):
    def __init__(self, config):
        self.location = config.cache_location
        self.url = config.cache_url
        self.is_writeable = False

        if self.location and os.path.isdir(self.location):
            self.use_filesystem = True

            self.is_writeable = os.access(self.location, os.W_OK)

            metadata_path = os.path.join(self.location, '.METADATA')

            if os.path.isfile(metadata_path):
                self.metadata = json.load(open(metadata_path, 'r'))
            else:
                self.metadata = {}

    def contains_package(self, package):
        print(package)
        if self.use_filesystem:
            if os.path.isfile(package):
                return True
        else:
            req = requests.head(self.url + '/' + package)

            if req == 0:
                return True

            return False
    def load(self, package):
        log.error('Don\'t know how to load packages')

class Package(object):
    def __init__(self, name, version, config, cache=None):
        self.name = name
        self.version = version
        self.config = config
        self.cache = cache

    def install(self):
        # Is it already installed
        installation_dir = os.path.join(self.config.component_dir, self.name)
        if os.path.isdir(installation_dir):
            installed_version = json.load(
                open(
                    os.path.join(installation_dir, 'bower.json')
                )
                )['version']
            if installed_version == self.version:
                log.info('Version %s of package %s is aready installed', self.version, self.name)
                return

        if self.cache:
            if self.is_cached():
                # install from cache via either url or location
                log.info('Installing version %s of %s from cache', self.version, self.name)
            else:
                if self.cache.is_writeable:
                    log.info('Loading %s into cache', self.name)
                    # load into cache if cache is writable
                    self.cache.load(self)
                else:
                    log.info('Installing version %s of %s without cache', self.version, self.name)
                    dest = '/tmp/bower.py'
                    self.fetch(dest=dest)
                    self.repo = git.Repo(os.path.join(dest, self.name))

                    try:
                        if self.version in self.repo.tags:
                            tag = self.repo.tags[self.version]
                        elif 'v' + self.version in self.repo.tags: # Thanks angular
                            tag = self.repo.tags['v' + self.version]
                        else:
                            raise IndexError

                        archive_name = os.path.join(
                            '/tmp/bower.py',
                            '{0}.{1}.zip'.format(self.name, self.version)
                        )

                        archive = open(archive_name, 'wb')
                        #archive = zipfile.ZipFile(archive_name, 'w') #TODO Later
                        self.repo.archive(archive, format='zip', treeish=tag)
                        archive.close()
                    except IndexError:
                        log.error('Version %s of package %s not found', self.version, self.name)
                        log.debug(self.repo.tags)
        else:
            # Don't bother with caching just install it
            log.info('Installing version %s of %s without cache', self.version, self.name)

    def is_cached(self):
        return False

    def add_to_cache(self):
        log.info('Package {0} added to cache', self.name)

    def clear(self):
        log.info('Package {0} removed from cache')
    def get_bower_metadata(self):
        # TODO caching - make sure we only hit bower once
        response = requests.get(API_URL + '/packages/' + self.name)
        if response.status_code != 200:
            logging.error('could not find package %s', self.name)
            sys.exit(1)

        try:
            result = response.json()
        except ValueError:
            fn = '/tmp/bower-py-json.txt'
            with open(fn, 'wb') as f:
                f.write(response.raw.read())
            log.exception('error parsing JSON (see %s)', fn)
            sys.exit(1)

        self.metadata = result
        log.info('found repository {}'.format(result['url']))


    def fetch(self, dest):
        self.get_bower_metadata()

        dest = os.path.join(dest, self.name)

        if not os.path.isdir(dest):
            self.repo = git.repo.Repo.clone_from(self.metadata['url'], dest, Progess())
            log.info('Repo successfully cloned')

class Project:
    def __init__(self, name):
        self.name = name

    def find(self, version=None):
        '''Fetch the remote metadata blob for the named package.
        '''
        response = requests.get(API_URL + '/packages/' + self.name)
        if response.status_code != 200:
            logging.error('could not find package %s', self.name)
            sys.exit(1)

        try:
            result = response.json()
        except ValueError:
            fn = '/tmp/bower-py-json.txt'
            with open(fn, 'wb') as f:
                f.write(response.raw.read())
            log.exception('error parsing JSON (see %s)', fn)
            sys.exit(1)

        log.info('found repository {}'.format(result['url']))

        #Do not assume guthub - do not use github api :(
        assert result['url'].startswith('git://github.com')
        return GitHubRepos(result['url']).find(version)

    def fetch(self, version=None):
        url = self.find(version)
        if url is None:
            sys.exit(1)
        log.info('downloading from {}'.format(url))
        response = requests.get(url, stream=True)
        with tempfile.TemporaryFile() as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
            f.seek(0)
            component_dir = locate_component_dir()
            dest_path = os.path.join(component_dir, self.name)
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path)

            contents = zipfile.ZipFile(f)
            bower_json = contents.namelist()[0] + 'bower.json'
            if bower_json in contents.namelist():
                meta = json.loads(contents.read(bower_json).decode('utf8'))
            else:
                meta = {}
            for name in contents.namelist():
                # ASSUMPTION: the zip files are created on Unix by github
                # thus paths are unix separated and follow consistent structure
                if name[-1] == '/':
                    continue
                assert name[0] != '/'
                assert not name.startswith('..')
                dest_name = '/'.join(name.split('/')[1:])

                if any(dest_name.split('/')[0] == ignore_path
                       for ignore_path in meta.get('ignore', [])):
                    continue

                source = contents.open(name)
                dest_name = os.path.join(dest_path, dest_name)
                if not os.path.exists(os.path.dirname(dest_name)):
                    os.makedirs(os.path.dirname(dest_name))
                target = open(dest_name, "wb")
                with source, target:
                    shutil.copyfileobj(source, target)

class CommandHandler(object):
    def process(self):
        log.error('Command %s is not implemented', sys.argv[1])

class InstallCommand(CommandHandler):
    def process(self):
        print(sys.argv)
        if len(sys.argv) > 2:
            Project(sys.argv[2]).fetch(sys.argv[3] if len(sys.argv) > 3 else None)
        else:
            try:
                bower_file = open('bower.json')
                bower_data = bower_file.read()
                bower_json = json.loads(bower_data)
                for dependency in bower_json['dependencies']:
                    print(dependency, bower_json['dependencies'][dependency])
                    Project(dependency).fetch(bower_json['dependencies'][dependency])
            except FileNotFoundError:
                log.error('No bower.json found')
                sys.exit(1)
            except KeyError:
                log.error('No dependencies found in bower.json')
                sys.exit(1)

class CacheCommand(CommandHandler):
    def process(self):
        log.debug('cache')
        log.debug(sys.argv)

        if len(sys.argv) > 2:
            cmd = sys.argv[2]

            if cmd == 'list':
                pass
            elif cmd == 'clean':
                pass
            elif cmd == 'build':
                pass
            else:
                log.error('Cache subcomand {0}')

class Config(object):
    def __init__(self, args):

        if not args.config:
            # look for ~/.config/bip/config.json
            config_fname = os.path.expanduser('~/.config/bip/config.json')
            if os.path.exists(config_fname):
                log.debug('User specific config file found')
            else:
                config_fname = '/etc/bip/config.json'
                if os.path.exists(config_fname):
                    log.debug('System bip confg file found')
                else:
                    config_fname = None

            if config_fname:
                config_file = open(config_fname)

                try:
                    config_details = json.load(config_file)
                except:
                    debug.error('Could not parse config file %s', config_fname)
                    raise

                config_file.close()
            else:
                config_details = {
                    'quiet':False,
                    'verbose':False,
                    'cache_location':'bip/var/cache',
                    'cache_url':'bip/var/cache',
                    'offline':False
                }
        else:
            try:
                config_details = json.load(open(args.config))
            except FileNotFoundError:
                log.error('The specified config file (%s) could not be opened', args.config)
                sys.exit(1)
            except ValueError:
                log.error('The specified config file (%s) is not valid json', args.config)
                sys.exit(1)

        for key in config_details:
            self.__setattr__(key, config_details[key])

        self.logging_level = logging.WARNING

        if args.quiet:
            self.logging_level = logging.ERROR

        if args.verbose:
            self.logging_level = logging.INFO

        if args.debug:
            self.logging_level = logging.DEBUG

        self.component_dir = locate_component_dir()

    def __repr__(self):
        return """Config:
        cache_location: {cache_location}
        cache_url: {cache_url}
        verbose: {verbose}
        quiet: {quiet}
        offline: {offline}
        """.format(
            cache_location=self.cache_location,
            cache_url=self.cache_url,
            verbose='True' if self.verbose else 'False',
            quiet='True' if self.quiet else 'False',
            offline='True' if self.offline else 'False'
            )



def main():
    # config file
    # default cache location
    # offline mode?
    # quiet mode?
    def cache_clean(args):
        print(args)

    def cmd_nyi(args):
        log.error('this command is not yet implemented')
        log.debug(args)

    def cmd_config_show(args):
        print(config)

    def cmd_install(args):
        re_spec = re.compile('^([a-zA-Z]+[\\da-zA-z_\\-\\.]*)==(\\d+\\.\\d+\\.\\d+)$')

        for package in args.name:
            match = re_spec.match(package)
            if match:
                name, version = match.groups()
                package = Package(name, version, args.config, cache=args.cache)
                package.install()
            else:
                log.error('Invalid package specification %s', package)
                log.info(
                    'Package specifications must be of the form name==version'
                    ' where version is a full version number like 2.0.0')


    def get_parser():
        def get_cache_parser(subparsersmsg):
            parser_cache = subparsers.add_parser('cache', help='manage bip\'s cache')
            subparser_cache = parser_cache.add_subparsers()
            parser_cache_clean = subparser_cache.add_parser('clean', help="Clean bip's cache")
            parser_cache_clean.add_argument('name', nargs='*')
            parser_cache_clean.set_defaults(func=cache_clean)

        def get_config_parser(subparsers):
            parser_config = subparsers.add_parser('config', help='show config details')
            subparsers = parser_config.add_subparsers()
            parser_show = subparsers.add_parser('show', help="Clean bip's cache")
            parser_show.set_defaults(func=cmd_config_show)

        def get_install_parser(subparsers):
            parser_config = subparsers.add_parser('install', help='install a package')
            parser_config.add_argument(
                '-F',
                '--force-latest',
                help='Force latest version on conflict. Not implemented'
            )
            parser_config.add_argument(
                '-p',
                '--production',
                help='Do not install project devDependencies. Not implemented'
            )
            parser_config.add_argument(
                '-S',
                '--save',
                help='Save installed packages into the project’s '
                'bower.json dependencies. Not implemented'
            )
            parser_config.add_argument(
                '-D',
                '--save-dev',
                help='Save installed packages into the project’s '
                'bower.json devDependencies. Not implemented'
            )
            parser_config.add_argument(
                'name',
                nargs='+',
                help='A list of packages to install'
            )
            parser_config.set_defaults(func=cmd_install)

        parser = argparse.ArgumentParser(
            description='A python re-implementation of bower'
        )
        parser.add_argument(
            '--config',
            help='Location of the bip config file'
        )
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            '--cache_location',
            help='Location of bip\'s cache - for storing things in the cache'
        )
        group.add_argument(
            '--cache_url',
            help='Location of bip\'s cache - for retrieving things from the cache. Can be a URL'
        )
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Show no progress information'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show lots of progress information'
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            default=False,
            help='Show debug information'
        )
        parser.add_argument(
            '--version',
            action='version',
            version='%(prog)s 0.0.1'
        )
        subparsers = parser.add_subparsers(help='subcommand help')

        get_cache_parser(subparsers)
        get_config_parser(subparsers)
        get_install_parser(subparsers)

        return parser

    parser = get_parser()
    args = parser.parse_args()

    config = Config(args)
    cache = Cache(config)

    logging.basicConfig(level=config.logging_level)
    args.cache = cache
    args.config = config
    args.func(args)

if __name__ == '__main__':
    main()