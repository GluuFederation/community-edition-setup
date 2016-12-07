import sys
import os
import logging
import shutil
import traceback
import subprocess
# configure logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)-8s %(name)s %(message)s',
                    filename='setup_standalone.log',
                    filemode='w')
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(levelname)-8s %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)


class SetupStandalone(object):
    def __init__(self, backup_folder):
        self.cmd_mkdir = '/bin/mkdir'
        self.certsFolder = "/etc/certs"
        self.openldapDataDir = "/opt/gluu/data"
        self.openldapConfFolder = "/opt/symas/etc/openldap/"
        self.openldapBinFolder = "/opt/symas/bin"
        self.openldapCnConfig = "/opt/symas/etc/openldap/slapd.d/"

        self.openldapSlapdConf = os.path.join(backup_folder, "slapd.conf")
        self.openldapSymasConf = os.path.join(backup_folder, "symas-openldap.conf")
        self.gluuSchema = os.path.join(backup_folder, "gluu.schema")
        self.customSchema = os.path.join(backup_folder, "custom.schema")
        self.userSchema = os.path.join(backup_folder, "user.schema")
        self.o_gluu = os.path.join(backup_folder, 'o_gluu.ldif')
        self.o_site = os.path.join(backup_folder, 'o_site.ldif')
        self.slaptest = os.path.join(self.openldapBinFolder, 'slaptest')

    def copyFile(self, infile, destfolder):
        try:
            shutil.copy(infile, destfolder)
            logging.debug("copied %s to %s" % (infile, destfolder))
        except:
            logging.error("error copying %s to %s" % (infile, destfolder))
            logging.error(traceback.format_exc())

    # args = command + args, i.e. ['ls', '-ltr']
    def run(self, args, cwd=None, env=None):
        logging.debug('Running: %s' % ' '.join(args))
        try:
            p = subprocess.Popen(args, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, cwd=cwd, env=env)
            output, err = p.communicate()
            if output:
                logging.debug(output)
            if err:
                logging.error(err)
        except:
            logging.error("Error running command : %s" % " ".join(args))
            logging.error(traceback.format_exc())

    def deploy(self):
        logging.info("Configuring OpenLDAP")
        # 0. Create the data dir
        if not os.path.isdir(self.openldapDataDir):
            self.run([self.cmd_mkdir, '-p', self.openldapDataDir])
        # 1. Copy the conf files to
        logging.info("Copying OpenLDAP config files")
        self.copyFile(self.openldapSlapdConf, self.openldapConfFolder)
        self.copyFile(self.openldapSymasConf, self.openldapConfFolder)
        # 2. Copy the schema files into place
        logging.info("Copying OpenLDAP Schema files")
        self.copyFile(self.gluuSchema, "/opt/gluu/")
        self.copyFile(self.customSchema, "/opt/gluu/")
        self.copyFile(self.userSchema, "/opt/gluu/")
        # 3. Populate the data
        logging.info("Importing LDIF files into OpenLDAP")
        cmd = os.path.join(self.openldapBinFolder, 'slapadd')
        config = os.path.join(self.openldapConfFolder, 'slapd.conf')

        # Import the base.ldif
        self.run([cmd, '-c', '-b', 'o=gluu', '-f', config, '-l', self.o_gluu])
        self.run([cmd, '-c', '-b', 'o=site', '-f', config, '-l', self.o_site])

        # Generate the cn=config directory
        self.run([self.cmd_mkdir, '-p', self.openldapCnConfig])
        self.run([self.slaptest, '-f', self.openldapSlapdConf, '-F', self.openldapCnConfig])


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print "Usage: python setup_standalone.py <path_to_backup_folder>"
        print "Example:\n python setup_standalone.py /root/standalone_export/"
    else:
        setup = SetupStandalone(sys.argv[1])
        setup.deploy()
