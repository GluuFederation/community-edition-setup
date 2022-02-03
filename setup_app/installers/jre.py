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
        self.service_name = 'jre'
        self.needdb = False # we don't need backend connection in this class
        self.install_var = 'installJre'
        self.app_type = AppType.APPLICATION
        self.install_type = InstallOption.MONDATORY
        if not base.snap:
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

        if Config.profile == SetupProfiles.DISA_STIG:
            self.fix_disa_stig_java_security

    def fix_disa_stig_java_security(self):
        # https://github.com/OpenIdentityPlatform/OpenDJ/issues/78
        java_security_fn = os.path.join(Config.jre_home, 'conf/security/java.security')
        if not os.path.exists(java_security_fn):
            java_security_fn = os.path.join(Config.jre_home, 'lib/security/java.security')

        if not os.path.exists(java_security_fn):
            self.logIt("Java security file not found", errorLog=True)
            return

        with open(java_security_fn) as f:
            java_security = f.readlines()

        """
        # remove current fips providers
        provider_n = None
        for i, l in enumerate(java_security[:]):
            ls = l.strip()
            if ls:
                if ls.startswith('fips.provider.1'):
                    provider_n = i
                if ls.startswith('fips.provider.'):
                    java_security.remove(l)

        providers = [
            'fips.provider.1=org.bouncycastle.jcajce.provider.BouncyCastleFipsProvider\n',
            'fips.provider.2=org.bouncycastle.jsse.provider.BouncyCastleJsseProvider fips:BCFIPS\n',
            'fips.provider.3=SunPKCS11 ${java.home}/conf/security/nss.fips.cfg\n',
            'fips.provider.4=SUN\n'
            'fips.provider.5=SunEC\n'
            'fips.provider.6=com.sun.net.ssl.internal.ssl.Provider SunPKCS11-NSS-FIPS\n'
            ]

        providers.reverse()

        # add fips providers
        for p in providers:
            java_security.insert(provider_n, p)
        """

        # fix securerandom.strongAlgorithms and jdk.tls.disabledAlgorithms
        for i, l in enumerate(java_security[:]):
            ls = l.strip()
            if ls:
                if ls.split('=')[0].strip() == 'securerandom.strongAlgorithms':
                    java_security[i] = 'securerandom.strongAlgorithms=NativePRNGBlocking:SUN,DRBG:SUN:BCFIPS\n'

                if ls.split('=')[0].strip() =='jdk.tls.disabledAlgorithms':
                   n = l.find('=')
                   k = l[:n].strip()
                   v = l[n+1:].strip()
                   java_security[i] = k + '=' + 'TLSv1.3, ' + v + '\n'

        with open(java_security_fn, 'w') as w:
            w.write(''.join(java_security))


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
