# -*- coding: utf-8 -*-
#################################################################################
# EXTERNAL LAYMAN TESTS
#################################################################################
# File:       external.py
#
#             Runs external (non-doctest) test cases.
#
# Copyright:
#             (c) 2009        Sebastian Pipping
#             Distributed under the terms of the GNU General Public License v2
#
# Author(s):
#             Sebastian Pipping <sebastian@pipping.org>
#

from __future__ import print_function
from __future__ import unicode_literals

'''Runs external (non-doctest) test cases.'''

import os
import sys
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET # Python 2.5
#Py3
try:
    import urllib.request as urllib
except ImportError:
    import urllib

from  layman.argsparser       import ArgsParser
from  layman.api              import LaymanAPI
from  layman.db               import DB
from  layman.dbbase           import DbBase
from  layman.compatibility    import fileopen
from  layman.config           import BareConfig, OptionConfig
from  layman.maker            import Interactive
from  layman.output           import Message
from  layman.overlays.overlay import Overlay
from  layman.remotedb         import RemoteDB
from  layman.repoconfmanager  import RepoConfManager
from  layman.utils            import path
from  warnings import filterwarnings, resetwarnings

encoding = sys.getdefaultencoding()

if encoding != 'utf-8':
    reload(sys)
    sys.setdefaultencoding('utf-8')

HERE = os.path.dirname(os.path.realpath(__file__))

class AddDeleteEnableDisableFromConf(unittest.TestCase):

    def test(self):
        tmpdir = tempfile.mkdtemp(prefix='laymantmp_')
        makeconf = os.path.join(tmpdir, 'make.conf')
        reposconf = os.path.join(tmpdir, 'repos.conf')

        make_txt =\
        'PORTDIR_OVERLAY="\n'\
        '$PORTDIR_OVERLAY"'

        # Create the .conf files so layman doesn't
        # complain.
        with fileopen(makeconf, 'w') as f:
            f.write(make_txt)

        with fileopen(reposconf, 'w') as f:
            f.write('')

        my_opts = {
                   'installed' :
                   HERE + '/testfiles/global-overlays.xml',
                   'make_conf' : makeconf,
                   'nocheck'    : 'yes',
                   'storage'   : tmpdir,
                   'repos_conf' : reposconf,
                   'conf_type' : ['make.conf', 'repos.conf'],
                   }

        config = OptionConfig(my_opts)
        config.set_option('quietness', 3)

        a = DB(config)
        config['output'].set_colorize(False)

        conf = RepoConfManager(config, a.overlays)

        # Set up our success tracker.
        success = []

        # Add all the overlays in global_overlays.xml.
        for overlay in a.overlays.keys():
            conf_success = conf.add(a.overlays[overlay])
            if conf_success == False:
                success.append(False)
            else:
                success.append(True)

        # Disable one overlay.
        self.assertTrue(conf.disable(a.overlays['wrobel']))

        # Enable disabled overlay.
        self.assertTrue(conf.enable(a.overlays['wrobel']))

        # Delete all the overlays in global_overlays.xml.
        for overlay in a.overlays.keys():
            self.assertTrue(conf.delete(a.overlays[overlay]))

        # Clean up.
        os.unlink(makeconf)
        os.unlink(reposconf)

        shutil.rmtree(tmpdir)


class AddDeleteDB(unittest.TestCase):
    def test(self):
        repo_name     = 'tar_test_overlay'
        temp_dir_path = tempfile.mkdtemp(prefix='laymantmp_')
        db_file       = os.path.join(temp_dir_path, 'installed.xml')
        make_conf     = os.path.join(temp_dir_path, 'make.conf')
        repo_conf     = os.path.join(temp_dir_path, 'repos.conf')

        tar_source_path = os.path.join(HERE, 'testfiles', 'layman-test.tar.bz2')

        (_, temp_tarball_path) = tempfile.mkstemp()
        shutil.copyfile(tar_source_path, temp_tarball_path)

        # Write overlay collection XML
        xml_text = '''\
<?xml version="1.0" encoding="UTF-8"?>
<repositories xmlns="" version="1.0">
  <repo quality="experimental" status="unofficial">
    <name>%(repo_name)s</name>
    <description>XXXXXXXXXXX</description>
    <owner>
      <email>foo@example.org</email>
    </owner>
    <source type="tar">file://%(temp_tarball_url)s</source>
  </repo>
</repositories>
        '''\
        % {
            'temp_tarball_url': urllib.pathname2url(temp_tarball_path),
            'repo_name': repo_name
          }

        (fd, temp_xml_path) = tempfile.mkstemp()

        my_opts = {'installed'     : temp_xml_path,
                   'conf_type'     : ['make.conf', 'repos.conf'],
                   'db_type'       : 'xml',
                   'nocheck'       : 'yes',
                   'make_conf'     : make_conf,
                   'repos_conf'    : repo_conf,
                   'storage'       : temp_dir_path,
                   'check_official': False}

        with os.fdopen(fd, 'w') as f:
            f.write(xml_text)

        with fileopen(make_conf, 'w') as f:
            f.write('PORTDIR_OVERLAY="$PORTDIR_OVERLAY"\n')

        with fileopen(repo_conf, 'w') as f:
            f.write('')

        config = OptionConfig(options=my_opts)
        config.set_option('quietness', 3)

        a = DB(config)
        config.set_option('installed', db_file)

        # Add an overlay to a fresh DB file.
        b = DB(config)
        b.add(a.select(repo_name))

        # Make sure it's actually installed.
        specific_overlay_path = os.path.join(temp_dir_path, repo_name)
        self.assertTrue(os.path.exists(specific_overlay_path))

        # Check the DbBase to ensure that it's reading the installed.xml.
        c = DbBase(config, paths=[db_file,])
        self.assertEqual(list(c.overlays), ['tar_test_overlay'])

        # Make sure the configs have been written to correctly.
        conf = RepoConfManager(config, b.overlays)
        self.assertEqual(list(conf.overlays), ['tar_test_overlay'])

        # Delete the overlay from the second DB.
        b.delete(b.select(repo_name))
        self.assertEqual(b.overlays, {})

        # Ensure the installed.xml has been cleaned properly.
        c = DbBase(config, paths=[db_file,])
        self.assertEqual(c.overlays, {})

        conf = RepoConfManager(config, b.overlays)
        self.assertEqual(conf.overlays, {})

        # Clean up.
        os.unlink(temp_xml_path)
        os.unlink(temp_tarball_path)
        shutil.rmtree(temp_dir_path)


# Tests archive overlay types (squashfs, tar)
# http://bugs.gentoo.org/show_bug.cgi?id=304547
class ArchiveAddRemoveSync(unittest.TestCase):

    def _create_squashfs_overlay(self):
        repo_name = 'squashfs-test-overlay'
        squashfs_source_path = os.path.join(HERE, 'testfiles', 'layman-test.squashfs')

        # Duplicate test squashfs (so we can delete it after testing)
        (_, temp_squashfs_path) = tempfile.mkstemp()
        shutil.copyfile(squashfs_source_path, temp_squashfs_path)

        # Write overlay collection XML
        xml_text = '''\
<?xml version="1.0" encoding="UTF-8"?>
<repositories xmlns="" version="1.0">
  <repo quality="experimental" status="unofficial">
    <name>%(repo_name)s</name>
    <description>XXXXXXXXXXX</description>
    <owner>
      <email>foo@example.org</email>
    </owner>
    <source type="squashfs">file://%(temp_squashfs_url)s</source>
  </repo>
</repositories>
        '''\
        % {
            'temp_squashfs_url': urllib.pathname2url(temp_squashfs_path),
            'repo_name': repo_name
          }
        print(xml_text)
        return xml_text, repo_name, temp_squashfs_path


    def _create_tar_overlay(self):
        repo_name = 'tar-test-overlay'
        tar_source_path = os.path.join(HERE, 'testfiles', 'layman-test.tar.bz2')

        # Duplicate test tarball (so we can delete it after testing)
        (_, temp_tarball_path) = tempfile.mkstemp()
        shutil.copyfile(tar_source_path, temp_tarball_path)

        # Write overlay collection XML
        xml_text = '''\
<?xml version="1.0" encoding="UTF-8"?>
<repositories xmlns="" version="1.0">
  <repo quality="experimental" status="unofficial">
    <name>%(repo_name)s</name>
    <description>XXXXXXXXXXX</description>
    <owner>
      <email>foo@example.org</email>
    </owner>
    <source type="tar">file://%(temp_tarball_url)s</source>
  </repo>
</repositories>
        '''\
        % {
            'temp_tarball_url': urllib.pathname2url(temp_tarball_path),
            'repo_name': repo_name
          }
        print(xml_text)
        return xml_text, repo_name, temp_tarball_path


    def test(self):
        archives = []
        try:
            from layman.overlays.modules.tar.tar import TarOverlay
            archives.append('tar')
            from layman.overlays.modules.squashfs.squashfs import SquashfsOverlay
            archives.append('squashfs')
        except ImportError:
            pass

        for archive in archives:
            xml_text, repo_name, temp_archive_path = getattr(self,
                                            "_create_%(archive)s_overlay" %
                                            {'archive': archive})()

            (fd, temp_collection_path) = tempfile.mkstemp()
            with os.fdopen(fd, 'w') as f:
                f.write(xml_text)

            # Make playground directory
            temp_dir_path = tempfile.mkdtemp()

            # Make DB from it
            config = BareConfig()
            # Necessary for all mountable overlay types
            layman_inst = LaymanAPI(config=config)
            db = DbBase(config, [temp_collection_path])

            specific_overlay_path = os.path.join(temp_dir_path, repo_name)
            o = db.select(repo_name)

            # Actual testcase
            o.add(temp_dir_path)
            self.assertTrue(os.path.exists(specific_overlay_path))
            # (1/2) Sync with source available
            o.sync(temp_dir_path)
            self.assertTrue(os.path.exists(specific_overlay_path))
            os.unlink(temp_archive_path)
            try:
                # (2/2) Sync with source _not_ available
                o.sync(temp_dir_path)
            except:
                pass
            self.assertTrue(os.path.exists(specific_overlay_path))
            o.delete(temp_dir_path)
            self.assertFalse(os.path.exists(specific_overlay_path))

            # Cleanup
            os.unlink(temp_collection_path)
            os.rmdir(temp_dir_path)


class CLIArgs(unittest.TestCase):

    def test(self):
        # Append cli args to sys.argv with correspoding options:
        sys.argv.append('--config')
        sys.argv.append(HERE + '/../../etc/layman.cfg')

        sys.argv.append('--overlay_defs')
        sys.argv.append('')

        # Test the passed in cli opts on the ArgsParser class:
        a = ArgsParser()
        test_url = 'https://api.gentoo.org/overlays/repositories.xml'
        self.assertTrue(test_url in a['overlays'].split('\n'))

        test_keys = ['auto_sync', 'bzr_addopts', 'bzr_command', 'bzr_postsync',
                     'bzr_syncopts', 'cache', 'check_official', 'clean_archive',
                     'conf_module', 'conf_type', 'config', 'configdir',
                     'custom_news_pkg', 'cvs_addopts', 'cvs_command',
                     'cvs_postsync', 'cvs_syncopts', 'darcs_addopts',
                     'darcs_command', 'darcs_postsync', 'darcs_syncopts',
                     'db_type', 'g-common_command', 'g-common_generateopts',
                     'g-common_postsync', 'g-common_syncopts',
                     'g-sorcery_command', 'g-sorcery_generateopts',
                     'g-sorcery_postsync', 'g-sorcery_syncopts', 'git_addopts',
                     'git_command', 'git_email', 'git_postsync', 'git_syncopts',
                     'git_user', 'gpg_detached_lists', 'gpg_signed_lists',
                     'http_proxy', 'https_proxy', 'installed', 'local_list',
                     'make_conf', 'mercurial_addopts', 'mercurial_command',
                     'mercurial_postsync', 'mercurial_syncopts',
                     'news_reporter', 'nocheck', 'overlay_defs', 'overlays',
                     'protocol_filter', 'quietness', 'repos_conf',
                     'require_repoconfig', 'rsync_command', 'rsync_postsync',
                     'rsync_syncopts', 'squashfs_addopts', 'squashfs_command',
                     'squashfs_postsync', 'squashfs_syncopts', 'storage',
                     'support_url_updates', 'svn_addopts', 'svn_command',
                     'svn_postsync', 'svn_syncopts', 't/f_options',
                     'tar_command', 'tar_postsync', 'umask', 'width']
        # Due to this not being a dict object, the keys() invocation is needed.
        self.assertEqual(sorted(a.keys()), test_keys)


class CreateConfig(unittest.TestCase):

    def make_BareConfig(self):
        a = BareConfig()

        # Test components of the BareConfig class:
        self.test_url = 'https://api.gentoo.org/overlays/repositories.xml'
        assertEqual(a['overlay'], self.test_url)
        self.test_keys =  ['bzr_addopts', 'bzr_command', 'bzr_postsync',
                      'bzr_syncopts', 'cache', 'config', 'configdir',
                      'custom_news_func', 'custom_news_pkg', 'cvs_addopts',
                      'cvs_command', 'cvs_postsync', 'cvs_syncopts',
                      'darcs_addopts', 'darcs_command', 'darcs_postsync',
                      'darcs_syncopts', 'g-common_command',
                      'g-common_generateopts', 'g-common_postsync',
                      'g-common_syncopts', 'git_addopts', 'git_command',
                      'git_email', 'git_postsync', 'git_syncopts', 'git_user',
                      'installed', 'local_list', 'make_conf',
                      'mercurial_addopts', 'mercurial_command',
                      'mercurial_postsync', 'mercurial_syncopts',
                      'news_reporter', 'nocheck', 'nocolor', 'output',
                      'overlay_defs', 'overlays', 'proxy', 'quiet',
                      'quietness', 'rsync_command', 'rsync_postsync',
                      'rsync_syncopts', 'stderr', 'stdin', 'stdout', 'storage',
                      'svn_addopts', 'svn_command', 'svn_postsync',
                      'svn_syncopts', 't/f_options', 'tar_command',
                      'tar_postsync', 'umask', 'verbose', 'width']
        assertEqual(sorted(a), self.test_keys)
        assertEqual(a.get_option('nocheck'), True)


    def make_OptionConfig(self):
        my_opts = {
                   'overlays':
                   ["http://www.gentoo-overlays.org/repositories.xml"]
                  }
        new_defaults = {'configdir': '/etc/test-dir'}

        a = OptionConfig(options=my_opts, defaults=new_defaults)

        # Test components of the OptionConfig class:
        assertEqual(a['overlays'], self.test_url)
        assertEqual(a['configdir'], my_opts['configdir'])
        assertEqual(sorted(a), self.test_keys)


    def test(self):
        for i in ['BareConfig', 'OptionConfig']:
            getattr(self, 'make_%s' % i)


class FetchRemoteList(unittest.TestCase):

    def test(self):
        tmpdir = tempfile.mkdtemp(prefix='laymantmp_')
        cache = os.path.join(tmpdir, 'cache')

        my_opts = {
                   'overlays': ['file://'\
                                + HERE + '/testfiles/global-overlays.xml'],
                   'db_type': 'xml',
                   'cache': cache,
                   'nocheck': 'yes',
                   'proxy': None,
                   'quietness': 3
                  }

        config = OptionConfig(my_opts)

        api = LaymanAPI(config)
        self.assertTrue(api.fetch_remote_list())

        filename = api._get_remote_db().filepath(config['overlays']) + '.xml'

        with fileopen(filename, 'r') as b:
            description = b.readlines()[19]
            self.assertEqual(description, '      A collection of ebuilds from '\
                                          'Gunnar Wrobel [wrobel@gentoo.org].\n')
            for line in b.readlines():
                print(line, end='')

        # Check if we get available overlays.
        available = api.get_available()
        self.assertEqual(available, ['wrobel', 'wrobel-stable'])

        
        # Test the info of an overlay.
        info = api.get_info_str(['wrobel'], verbose=True, local=False)
        test_info = 'wrobel\n~~~~~~\nSource  : https://overlays.gentoo.org'\
                    '/svn/dev/wrobel\nContact : nobody@gentoo.org\nType    '\
                    ': Subversion; Priority: 10\nQuality : experimental\n\n'\
                    'Description:\n  Test\n'

        info = info['wrobel'][0].decode('utf-8')
        self.assertEqual(info, test_info)

        os.unlink(filename)
        shutil.rmtree(tmpdir)


class FormatBranchCategory(unittest.TestCase):
    def _run(self, number):
        #config = {'output': Message()}
        config = BareConfig()

        # Discuss renaming files to "branch-%d.xml"
        filename1 = os.path.join(HERE, 'testfiles',
                'subpath-%d.xml' % number)

        # Read, write, re-read, compare
        os1 = DbBase(config, [filename1])
        filename2 = tempfile.mkstemp()[1]
        os1.write(filename2)
        os2 = DbBase(config, [filename2])
        os.unlink(filename2)
        self.assertTrue(os1 == os2)

        # Pass original overlays
        return os1

    def test(self):
        os1 = self._run(1)
        os2 = self._run(2)

        # Same content from old/layman-global.txt
        #   and new/repositories.xml format?
        self.assertTrue(os1 == os2)


class MakeOverlayXML(unittest.TestCase):

    def test(self):
        temp_dir_path = tempfile.mkdtemp()
        my_opts = {
                   'overlays': ['file://'\
                        + HERE + '/testfiles/global-overlays.xml'],
                   'nocheck': 'yes',
                   'proxy': None,
                   'quietness': 3,
                  }

        config = OptionConfig(my_opts)

        ovl_dict = {
                    'name': 'wrobel',
                    'description': ['Test'],
                    'owner': [{'name': 'nobody', 'email': 'nobody@gentoo.org'}],
                    'status': 'official',
                    'source': [['https://overlays.gentoo.org/svn/dev/wrobel',
                                 'svn', '']],
                    'priority': '10',
                   }

        a = Overlay(config=config, ovl_dict=ovl_dict, ignore=config['ignore'])
        ovl = (ovl_dict['name'], a)
        path = temp_dir_path + '/overlay.xml'
        create_overlay_xml = Interactive(config=config)

        create_overlay_xml(overlay_package=ovl, path=path)
        self.assertTrue(os.path.exists(path))

        with fileopen(path, 'r') as xml:
            test_line = '    <source type="svn">'\
                        'https://overlays.gentoo.org/svn/dev/wrobel</source>\n'
            self.assertTrue(test_line in xml.readlines())
            for line in xml.readlines():
                print(line, end='')

        shutil.rmtree(temp_dir_path)


class OverlayObjTest(unittest.TestCase):

    def objattribs(self):
        document = ET.parse(HERE + '/testfiles/global-overlays.xml')
        overlays = document.findall('overlay') + document.findall('repo')
        output = Message()
        ovl_a = Overlay({'output': output, 'db_type': 'xml'}, xml=overlays[0])
        self.assertEqual(ovl_a.name, 'wrobel')
        self.assertEqual(ovl_a.is_official(), True)
        url = ['https://overlays.gentoo.org/svn/dev/wrobel']
        self.assertEqual(list(ovl_a.source_uris()), url)
        self.assertEqual(ovl_a.owners[0]['email'], 'nobody@gentoo.org')
        self.assertEqual(ovl_a.descriptions, ['Test'])
        self.assertEqual(ovl_a.priority, 10)

        ovl_b = Overlay({'output': output, 'db_type': 'xml'}, xml=overlays[1])
        self.assertEqual(ovl_b.is_official(), False)


    def getinfostr(self):
        document = ET.parse(HERE + '/testfiles/global-overlays.xml')
        overlays = document.findall('overlay') + document.findall('repo')
        output = Message()

        ovl = Overlay({'output': output, 'db_type': 'xml'}, xml=overlays[0])
        test_infostr = 'wrobel\n~~~~~~\nSource  : '\
                       'https://overlays.gentoo.org/svn/dev/wrobel\nContact '\
                       ': nobody@gentoo.org\nType    : Subversion; Priority: '\
                       '10\nQuality : experimental\n\nDescription:\n  Test\n'
        self.assertEqual(ovl.get_infostr().decode('utf-8'), test_infostr)
        print(ovl.get_infostr().decode('utf-8'))


    def getshortlist(self):
        document = ET.parse(HERE + '/testfiles/global-overlays.xml')
        overlays = document.findall('overlay') + document.findall('repo')
        output = Message()

        ovl = Overlay({'output': output, 'db_type': 'xml'}, xml=overlays[0])
        test_short_list = 'wrobel                    [Subversion] '\
                          '(https://o.g.o/svn/dev/wrobel         )'
        self.assertEqual(ovl.short_list(80).decode('utf-8'), test_short_list)
        print(ovl.short_list(80).decode('utf-8'))


    def test(self):
        self.objattribs()
        self.getinfostr()
        self.getshortlist()


class PathUtil(unittest.TestCase):

    def test(self):
        self.assertEqual(path([]), '')
        self.assertEqual(path(['a']), 'a')
        self.assertEqual(path(['a', 'b']), 'a/b')
        self.assertEqual(path(['a/', 'b']), 'a/b')
        self.assertEqual(path(['/a/', 'b']), '/a/b')
        self.assertEqual(path(['/a', '/b/']), '/a/b')
        self.assertEqual(path(['/a/', 'b/']), '/a/b')
        self.assertEqual(path(['/a/','/b/']), '/a/b')
        self.assertEqual(path(['/a/','/b','c/']), '/a/b/c')


class Unicode(unittest.TestCase):
    def _overlays_bug(self, number):
        config = BareConfig()
        filename = os.path.join(HERE, 'testfiles', 'overlays_bug_%d.xml'\
                                                    % number)
        o = DbBase(config, [filename])
        for verbose in (True, False):
            for t in o.list(verbose=verbose):
                print(t[0].decode('utf-8'))
                print()

    def test_184449(self):
        self._overlays_bug(184449)

    def test_286290(self):
        self._overlays_bug(286290)


class ReadWriteSelectListDbBase(unittest.TestCase):

    def list_db(self):
        output = Message()
        config = {
                  'output': output,
                  'db_type': 'xml',
                  'svn_command': '/usr/bin/svn',
                  'rsync_command':'/usr/bin/rsync'
                 }
        db = DbBase(config, [HERE + '/testfiles/global-overlays.xml', ])

        test_info = ('wrobel\n~~~~~~\nSource  : '\
                     'https://overlays.gentoo.org/svn/dev/wrobel\nContact : '\
                     'nobody@gentoo.org\nType    : Subversion; Priority: 10\n'\
                     'Quality : experimental\n\nDescription:\n  Test\n',
                     'wrobel-stable\n~~~~~~~~~~~~~\nSource  : '\
                     'rsync://gunnarwrobel.de/wrobel-stable\nContact : '\
                     'nobody@gentoo.org\nType    : Rsync; Priority: 50\n'\
                     'Quality : experimental\n\nDescription:\n  A collection '\
                     'of ebuilds from Gunnar Wrobel [wrobel@gentoo.org].\n')

        info = db.list(verbose=True)

        for i in range(0, len(info)):
            self.assertEqual(info[i][0].decode('utf-8'), test_info[i])
            print(info[i][0].decode('utf-8'))

        test_info = ('wrobel                    [Subversion] '\
                     '(https://o.g.o/svn/dev/wrobel         )',
                     'wrobel-stable             [Rsync     ] '\
                     '(rsync://gunnarwrobel.de/wrobel-stable)')

        info = db.list(verbose=False, width=80)
        for i in range(0, len(info)):
            self.assertEqual(info[i][0].decode('utf-8'), test_info[i])
            print(info[i][0].decode('utf-8'))

    def read_db(self):
        output = Message()
        # First test if XML databasing works.
        config = {'output': output,
                  'db_type': 'xml',}
        db = DbBase(config, [HERE + '/testfiles/global-overlays.xml', ])
        keys = sorted(db.overlays)
        self.assertEqual(keys, ['wrobel', 'wrobel-stable'])

        url = ['rsync://gunnarwrobel.de/wrobel-stable']
        self.assertEqual(list(db.overlays['wrobel-stable'].source_uris()), url)

        # Test JSON databasing after.
        config['db_type'] = 'json'
        db = DbBase(config, [HERE + '/testfiles/global-overlays.json', ])
        keys = sorted(db.overlays)
        self.assertEqual(keys, ['twitch153', 'wrobel-stable'])

        url = ['git://github.com/twitch153/ebuilds.git']
        self.assertEqual(list(db.overlays['twitch153'].source_uris()), url)


    def select_db(self):
        output = Message()
        config = {'output': output,
                  'db_type': 'xml',}
        db = DbBase(config, [HERE + '/testfiles/global-overlays.xml', ])
        url = ['rsync://gunnarwrobel.de/wrobel-stable']
        self.assertEqual(list(db.select('wrobel-stable').source_uris()), url)

        config['db_type'] = 'json'
        db = DbBase(config, [HERE + '/testfiles/global-overlays.json', ])
        url = ['git://github.com/twitch153/ebuilds.git']
        self.assertEqual(list(db.select('twitch153').source_uris()), url)


    def write_db(self):
        tmpdir = tempfile.mkdtemp(prefix='laymantmp_')
        test_xml = os.path.join(tmpdir, 'test.xml')
        test_json = os.path.join(tmpdir, 'test.json')
        config = BareConfig()

        a = DbBase(config, [HERE + '/testfiles/global-overlays.xml', ])
        b = DbBase({'output': Message(), 'db_type': 'xml'}, [test_xml,])

        b.overlays['wrobel-stable'] = a.overlays['wrobel-stable']
        b.write(test_xml)

        c = DbBase({'output': Message(), 'db_type': 'xml'}, [test_xml,])
        keys = sorted(c.overlays)
        self.assertEqual(keys, ['wrobel-stable'])

        config.set_option('db_type', 'json')
        a = DbBase(config, [HERE + '/testfiles/global-overlays.json', ])
        b = DbBase({'output': Message(), 'db_type': 'json'}, [test_json,])

        b.overlays['twitch153'] = a.overlays['twitch153']
        b.write(test_json)

        c = DbBase({'output': Message(), 'db_type': 'json'}, [test_json,])
        keys = sorted(c.overlays)
        self.assertEqual(keys, ['twitch153'])

        # Clean up:
        os.unlink(test_xml)
        os.unlink(test_json)
        shutil.rmtree(tmpdir)


    def test(self):
        self.list_db()
        self.read_db()
        self.select_db()
        self.write_db()


class RemoteDBCache(unittest.TestCase):
    def test(self):
        tmpdir = tempfile.mkdtemp(prefix='laymantmp_')
        cache = os.path.join(tmpdir, 'cache')
        my_opts = {
                   'overlays' :
                   ['file://' + HERE + '/testfiles/global-overlays.xml'],
                   'cache' : cache,
                   'nocheck'    : 'yes',
                   'proxy' : None
                  }
        config = OptionConfig(my_opts)
        db = RemoteDB(config)
        self.assertEqual(db.cache(), (True, True))

        db_xml = fileopen(db.filepath(config['overlays']) + '.xml')

        test_line = '      A collection of ebuilds from Gunnar Wrobel '\
                    '[wrobel@gentoo.org].\n'
        self.assertEqual(db_xml.readlines()[19], test_line)

        for line in db_xml.readlines():
            print(line, end='')

        db_xml.close()
        keys = sorted(db.overlays)
        self.assertEqual(keys, ['wrobel', 'wrobel-stable'])

        shutil.rmtree(tmpdir)


if __name__ == '__main__':
    filterwarnings('ignore')
    unittest.main()
    resetwarnings()
