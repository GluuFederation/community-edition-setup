import os
import glob
import shutil

from pathlib import Path

from setup_app import paths
from setup_app.utils import base
from setup_app.static import AppType, InstallOption, SetupProfiles
from setup_app.config import Config
from setup_app.utils.setup_utils import SetupUtils
from setup_app.installers.base import BaseInstaller

class JreInstaller(BaseInstaller, SetupUtils):

    def __init__(self):
        setattr(base.current_app, self.__class__.__name__, self)
        self.service_name = 'jre'
        self.needdb = False # we don't need backend connection in this class
        self.install_var = 'installJre'
        self.app_type = AppType.APPLICATION
        self.install_type = InstallOption.MANDATORY
        self.register_progess()

        self.open_jdk_archive_link = 'https://github.com/AdoptOpenJDK/openjdk11-binaries/releases/download/jdk-11.0.4%2B11/OpenJDK11U-jdk_x64_linux_hotspot_11.0.4_11.tar.gz'


    def install(self):

        if not Config.use_existing_java:
            # we need to call download_files() unless it called by base installer
            if not Config.downloadWars:
                self.download_files()

            self.logIt("Installing server JRE {} ...".format(os.path.basename(self.jreArchive)))

            try:
                self.logIt("Extracting %s into /opt/" % os.path.basename(self.jreArchive))
                self.run([paths.cmd_tar, '-xzf', self.jreArchive, '-C', '/opt/', '--no-xattrs', '--no-same-owner', '--no-same-permissions'])
            except:
                self.logIt("Error encountered while extracting archive %s" % self.jreArchive)

            if Config.java_type == 'jdk':
                jreDestinationPath = max(glob.glob('/opt/jdk-11*'))
            else:
                jreDestinationPath = max(glob.glob('/opt/amazon-corretto-*'))

            self.run([paths.cmd_ln, '-sf', jreDestinationPath, Config.jre_home])
            self.run([paths.cmd_chmod, '-R', "755", "%s/bin/" % jreDestinationPath])
            self.run([paths.cmd_chown, '-R', 'root:root', jreDestinationPath])
            self.run([paths.cmd_chown, '-h', 'root:root', Config.jre_home])

            if not os.path.exists('/opt/jre/jre'):
                self.run([paths.cmd_mkdir, '-p', '/opt/jre/jre'])
                self.run([paths.cmd_ln, '-s', '/opt/jre/lib', '/opt/jre/jre/lib'])

            if Config.java_type == 'jre':
                for jsfn in Path('/opt/jre').rglob('java.security'):
                    self.run([paths.cmd_sed, '-i', '/^#crypto.policy=unlimited/s/^#//', jsfn._str])


    def download_files(self):
        jre_arch_list = glob.glob(os.path.join(Config.distAppFolder, 'amazon-corretto-*.tar.gz'))

        if not jre_arch_list:
            self.logIt("JRE packgage not found in {}. Will download jdk".format(Config.distAppFolder))
            Config.java_type = 'jdk'
        else:
            Config.java_type = 'jre'

        if Config.java_type != 'jre':
            jdk_fn = os.path.basename(self.open_jdk_archive_link)       
            self.logIt("Downloading " + jdk_fn, pbar=self.service_name)
            self.jreArchive = os.path.join(Config.distAppFolder, jdk_fn)
            base.download(self.open_jdk_archive_link, self.jreArchive)
        else:
            self.jreArchive = max(jre_arch_list)
