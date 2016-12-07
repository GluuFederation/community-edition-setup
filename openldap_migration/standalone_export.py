import os
import os.path
import logging
import shutil
import traceback
import subprocess
import re

# configure logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)-8s %(name)s %(message)s',
                    filename='standalone_export.log',
                    filemode='w')
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(levelname)-8s %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)


class SetupOpenLDAP(object):

    def __init__(self):
        self.miniSetupFile = os.path.abspath(__file__)
        self.miniSetupFolder = os.path.dirname(self.miniSetupFile)
        self.setupFolder = os.path.dirname(self.miniSetupFolder)
        self.templateFolder = os.path.join(self.setupFolder, 'templates')
        self.outputFolder = os.path.join(self.setupFolder, 'output')
        self.backupFolder = os.path.join(self.miniSetupFolder, 'opendj_export')
        self.backupLdifFolder = os.path.join(self.backupFolder, 'ldif')
        self.standaloneExport = os.path.join(self.miniSetupFolder, 'standalone_export')

        self.cmd_mkdir = '/bin/mkdir'
        self.ldif_export = "/opt/opendj/bin/export-ldif"

        self.ip = None
        self.inumOrg = None
        self.inumOrgFN = None
        self.orgName = None
        self.ldapPass = None

        self.certFolder = '/etc/certs'
        self.openldapBaseFolder = '/opt/symas'
        self.openldapBinFolder = '/opt/symas/bin'
        self.openldapConfFolder = '/opt/symas/etc/openldap'
        self.openldapCnConfig = '%s/slapd.d' % self.openldapConfFolder
        self.openldapRootUser = "cn=directory manager,o=gluu"
        self.user_schema = '%s/user.schema' % self.outputFolder
        self.openldapKeyPass = None
        self.openldapTLSCACert = '%s/openldap.pem' % self.certFolder
        self.openldapTLSCert = '%s/openldap.crt' % self.certFolder
        self.openldapTLSKey = '%s/openldap.key' % self.certFolder
        self.openldapPassHash = None
        self.openldapSlapdConf = '%s/slapd.conf' % self.outputFolder
        self.openldapSymasConf = '%s/symas-openldap.conf' % self.outputFolder
        self.slaptest = '%s/slaptest' % self.openldapBinFolder
        self.openldapDataDir = '/opt/gluu/data'
        self.o_gluu = '%s/o_gluu.ldif' % self.miniSetupFolder
        self.o_gluu_temp = '%s/o_gluu.temp' % self.miniSetupFolder
        self.o_site = '%s/o_site.ldif' % self.miniSetupFolder
        self.o_site_temp = '%s/o_site.temp' % self.miniSetupFolder

        self.attrs = 1000
        self.objclasses = 1000

    def copyFile(self, infile, destfolder):
        try:
            shutil.copy(infile, destfolder)
            logging.debug("copied %s to %s" % (infile, destfolder))
        except:
            logging.error("error copying %s to %s" % (infile, destfolder))
            logging.error(traceback.format_exc())

    def renderTemplate(self, filePath, templateFolder, outputFolder):
        logging.debug("Rendering template %s" % filePath)
        fn = os.path.split(filePath)[-1]
        f = open(os.path.join(templateFolder, fn))
        template_text = f.read()
        f.close()
        newFn = open(os.path.join(outputFolder, fn), 'w+')
        newFn.write(template_text % self.__dict__)
        newFn.close()

    def render_templates(self):
        # 1. slapd.conf
        cmd = os.path.join(self.openldapBinFolder, "slappasswd") + " -s " \
            + self.ldapPass
        self.openldapPassHash = os.popen(cmd).read().strip()
        self.renderTemplate(self.openldapSlapdConf, self.templateFolder,
                            self.outputFolder)
        # 2. symas-openldap.conf
        self.renderTemplate(self.openldapSymasConf, self.templateFolder,
                            self.outputFolder)

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

    def export_opendj(self):
        logging.info("Exporting all the data from OpenDJ")
        command = [self.ldif_export, '-n', 'userRoot', '-l', self.o_gluu_temp]
        self.run(command)
        command = [self.ldif_export, '-n', 'site', '-l', self.o_site_temp]
        self.run(command)

    def get_old_properties(self):
        # grab the old inumOrgFN
        logging.info('Scanning setup.properties.last for data')
        with open('/install/community-edition-setup/setup.properties.last') as ofile:
            for line in ofile:
                if 'inumOrgFN=' in line:
                    self.inumOrgFN = line.split('=')[-1].strip()
                elif 'inumOrg=' in line:
                    self.inumOrg = line.split('=')[-1].strip()
                elif 'orgName=' in line:
                    self.orgName = line.split('=')[-1].strip()
                elif 'ldapPass=' in line:
                    self.ldapPass = line.split('=')[-1].strip()
        # Get the IP of the standalone server
        self.ip = raw_input("Enter the IP address of the standalone OpendLDAP server: ").strip()

    def clean_ldif_data(self):
        with open(self.o_gluu_temp, 'r') as infile:
            with open(self.o_gluu, 'w') as outfile:
                for line in infile:
                    outfile.write(line.replace("lastModifiedTime", "oxLastAccessTime"))

        with open(self.o_site_temp, 'r') as infile:
            with open(self.o_site, 'w') as outfile:
                for line in infile:
                    outfile.write(line.replace("lastModifiedTime", "oxLastAccessTime"))

    def convert_schema(self, f):
        infile = open(f, 'r')
        output = ""

        for line in infile:
            if re.match('^dn:', line) or re.match('^objectClass:', line) or \
                    re.match('^cn:', line):
                continue
            # empty lines and the comments are copied as such
            if re.match('^#', line) or re.match('^\s*$', line):
                pass
            elif re.match('^\s\s', line):  # change the space indendation to tabs
                line = re.sub('^\s\s', '\t', line)
            elif re.match('^\s', line):
                line = re.sub('^\s', '\t', line)
            # Change the keyword for attributetype
            elif re.match('^attributeTypes:\s', line, re.IGNORECASE):
                line = re.sub('^attributeTypes:', '\nattributetype', line, 1,
                              re.IGNORECASE)
                oid = 'oxAttribute:' + str(self.attrs+1)
                line = re.sub('\s[\d]+\s', ' '+oid+' ', line, 1, re.IGNORECASE)
                self.attrs += 1
            # Change the keyword for objectclass
            elif re.match('^objectClasses:\s', line, re.IGNORECASE):
                line = re.sub('^objectClasses:', '\nobjectclass', line, 1,
                              re.IGNORECASE)
                oid = 'oxObjectClass:' + str(self.objclasses+1)
                line = re.sub('ox-[\w]+-oid', oid, line, 1, re.IGNORECASE)
                self.objclasses += 1
            else:
                logging.warning("Skipping Line: {}".format(line.strip()))
                line = ""

            output += line

        infile.close()
        return output

    def __update_user_schema(self, infile, outfile):
        with open(infile, 'r') as olduser:
            with open(outfile, 'w') as newuser:
                for line in olduser:
                    if 'SUP top' in line:
                        line = line.replace('SUP top', 'SUP gluuPerson')
                    newuser.write(line)

    def create_user_schema(self):
        logging.info('Converting custom attributes to OpenLDAP schema')
        schema_99 = '/opt/opendj/config/schema/99-user.ldif'
        schema_100 = '/opt/opendj/config/schema/100-user.ldif'
        new_user = '%s/new_99.ldif' % self.miniSetupFolder

        outfile = open('%s/user.schema' % self.outputFolder, 'w')
        output = ""

        if os.path.isfile(schema_99):
            output = self.convert_schema(schema_100)
            self.__update_user_schema(schema_99, new_user)
            output = output + "\n" + self.convert_schema(new_user)
        else:
            # If there is no 99-user file, then the schema def is in 100-user
            self.__update_user_schema(schema_100, new_user)
            output = self.convert_schema(new_user)

        outfile.write(output)
        outfile.close()

    def pack_files(self):
        logging.info("Moving files")
        self.run([self.cmd_mkdir, '-p', self.standaloneExport])
        # OpenLDAP configurations
        self.copyFile(self.openldapSlapdConf, self.standaloneExport)
        self.copyFile(self.openldapSymasConf, self.standaloneExport)
        # Schema Files
        self.copyFile(self.user_schema, self.standaloneExport)
        self.copyFile("%s/static/openldap/gluu.schema" % self.setupFolder, self.standaloneExport)
        self.copyFile("%s/static/openldap/custom.schema" % self.setupFolder, self.standaloneExport)
        # Processed LDIF data
        self.copyFile(self.o_gluu, self.standaloneExport)
        self.copyFile(self.o_site, self.standaloneExport)
        logging.info("Export complete. All the required files for a standalone OpenLDAP server are in in the folder `standalone_export`")


if __name__ == '__main__':
    setup = SetupOpenLDAP()
    setup.get_old_properties()
    setup.create_user_schema()
    setup.render_templates()
    setup.export_opendj()
    setup.clean_ldif_data()
    setup.pack_files()
