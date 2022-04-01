import os
import glob
import shutil
import ssl
import json
import ldap3
import sys

from setup_app import paths
from setup_app.static import AppType, InstallOption
from setup_app.config import Config
from setup_app.utils import base
from setup_app.static import InstallTypes, BackendTypes, SetupProfiles
from setup_app.utils.setup_utils import SetupUtils
from setup_app.installers.base import BaseInstaller

class OpenDjInstaller(BaseInstaller, SetupUtils):

    def __init__(self):
        setattr(base.current_app, self.__class__.__name__, self)
        self.service_name = 'opendj'
        self.pbar_text = "Installing OpenDJ"
        self.needdb = False # we don't need backend connection in this class
        self.app_type = AppType.SERVICE
        self.install_type = InstallOption.OPTONAL
        self.install_var = 'ldap_install'
        self.register_progess()

        self.openDjIndexJson = os.path.join(Config.install_dir, 'static/opendj/index.json')
        self.openDjSchemaFolder = os.path.join(Config.ldapBaseFolder, 'config/schema')
        self.openDjschemaFiles = glob.glob(os.path.join(Config.install_dir, 'static/opendj/*.ldif'))

        self.opendj_service_centos7 = os.path.join(Config.install_dir, 'static/opendj/systemd/opendj.service')
        self.ldapDsconfigCommand = os.path.join(Config.ldapBinFolder, 'dsconfig')
        self.ldapDsCreateRcCommand = os.path.join(Config.ldapBinFolder, 'create-rc-script')

        if Config.profile == SetupProfiles.DISA_STIG:
            Config.ldap_setup_properties += '.' + Config.opendj_truststore_format.lower()
        self.opendj_trusstore_setup_key_fn = os.path.join(Config.outputFolder, 'opendj.keystore.pin')


        self.opendj_pck11_setup_key_fn = '/root/.keystore.pin'
        self.opendj_admin_truststore_fn = os.path.join(Config.ldapBaseFolder, 'config', 'admin-truststore')
        self.opendj_key_store_password_fn = os.path.join(Config.ldapBaseFolder, 'config', 'keystore.pin')




    def install(self):
        self.logIt("Running OpenDJ Setup")

        if not base.snap:
            Config.pbar.progress(self.service_name, "Extracting OpenDJ", False)
            self.extractOpenDJ()

        self.createLdapPw()

        Config.pbar.progress(self.service_name, "Installing OpenDJ", False)
        if Config.ldap_install == InstallTypes.LOCAL:
            self.install_opendj()
            Config.pbar.progress(self.service_name, "Setting up OpenDJ service", False)
            self.setup_opendj_service()
            Config.pbar.progress(self.service_name, "Preparing OpenDJ schema", False)
            self.prepare_opendj_schema()

        # it is time to bind OpenDJ
        self.dbUtils.bind()

        if Config.ldap_install:
            Config.pbar.progress(self.service_name, "Creating OpenDJ backends", False)
            self.create_backends()
            Config.pbar.progress(self.service_name, "Configuring OpenDJ", False)
            self.configure_opendj()
            Config.pbar.progress(self.service_name, "Exporting OpenDJ certificate", False)
            self.export_opendj_public_cert()
            Config.pbar.progress(self.service_name, "Creating OpenDJ indexes", False)
            self.index_opendj()

            ldif_files = []

            if Config.mappingLocations['default'] == 'ldap':
                ldif_files += Config.couchbaseBucketDict['default']['ldif']

            ldap_mappings = self.getMappingType('ldap')

            for group in ldap_mappings:
                ldif_files +=  Config.couchbaseBucketDict[group]['ldif']

            Config.pbar.progress(self.service_name, "Importing base ldif files to OpenDJ", False)
            if Config.ldif_base not in ldif_files:
                self.dbUtils.import_ldif([Config.ldif_base], force=BackendTypes.LDAP)

            self.dbUtils.import_ldif(ldif_files)

            Config.pbar.progress(self.service_name, "OpenDJ post installation", False)
            if Config.ldap_install == InstallTypes.LOCAL:
                self.post_install_opendj()


    def extractOpenDJ(self):

        opendj_archive = max(glob.glob(os.path.join(Config.distFolder, 'app/opendj-*4*.zip')))

        try:
            self.logIt("Unzipping %s in /opt/" % opendj_archive)
            self.run([paths.cmd_unzip, '-n', '-q', '%s' % (opendj_archive), '-d', '/opt/' ])
        except:
            self.logIt("Error encountered while doing unzip %s -d /opt/" % (opendj_archive))

        realLdapBaseFolder = os.path.realpath(Config.ldapBaseFolder)
        self.run([paths.cmd_chown, '-R', 'ldap:ldap', realLdapBaseFolder])

        if Config.ldap_install == InstallTypes.REMOTE:
            self.run([paths.cmd_ln, '-s', '/opt/opendj/template/config/', '/opt/opendj/config'])

    def create_user(self):
        self.createUser('ldap', Config.ldap_user_home)
        self.addUserToGroup('gluu', 'ldap')
        self.addUserToGroup('adm', 'ldap')

    def install_opendj(self):
        self.logIt("Running OpenDJ Setup")

        Config.templateRenderingDict['opendj_pck11_setup_key_fn'] = self.opendj_pck11_setup_key_fn
        Config.templateRenderingDict['opendj_trusstore_setup_key_fn'] = self.opendj_trusstore_setup_key_fn
        self.renderTemplateInOut(Config.ldap_setup_properties, Config.templateFolder, Config.outputFolder)

        setupPropsFN = os.path.join(Config.ldapBaseFolder, os.path.basename(Config.ldap_setup_properties))
        shutil.copy(
                os.path.join(Config.outputFolder, os.path.basename(Config.ldap_setup_properties)),
                setupPropsFN
                )

        self.run([paths.cmd_chown, 'ldap:ldap', setupPropsFN])

        self.generate_opendj_certs()

        self.fix_opendj_java_properties()

        if Config.profile == SetupProfiles.DISA_STIG:
            self.fix_opendj_config()
            opendj_fapolicyd_rules = [
                    'allow perm=any uid=ldap : dir={}'.format(Config.jre_home),
                    'allow perm=any uid=ldap : dir={}'.format(Config.ldapBaseFolder),
                    '# give access to opendj server',
                    ]

            self.apply_fapolicyd_rules(opendj_fapolicyd_rules)


        if Config.profile == SetupProfiles.DISA_STIG:
            # Restore SELinux Context
            self.run(['restorecon', '-rv', os.path.join(Config.ldapBaseFolder, 'bin')])

        self.run([paths.cmd_chown, 'root:gluu', Config.certFolder])
        self.run([paths.cmd_chown, 'root:gluu', Config.opendj_trust_store_fn])
        self.run([paths.cmd_chmod, '660', Config.opendj_trust_store_fn])


    def generate_opendj_certs(self):

        if Config.profile == SetupProfiles.DISA_STIG:
            self.writeFile(self.opendj_trusstore_setup_key_fn, Config.opendj_truststore_pass)

            provider_path = '{}:{}'.format(Config.bc_fips_jar, Config.bcpkix_fips_jar)
            keystore = Config.opendj_trust_store_fn if Config.opendj_truststore_format.upper() == 'BCFKS' else 'NONE'

            # Generate keystore

            cmd_server_cert_gen = [
                Config.cmd_keytool, '-genkey',
                '-alias', 'server-cert',
                '-keyalg', 'rsa',
                '-dname', 'CN={},O=OpenDJ RSA Self-Signed Certificate'.format(Config.hostname),
                '-keystore', keystore,
                '-storetype', Config.opendj_truststore_format.upper(),
                '-validity', '3650',
                ]

            if Config.opendj_truststore_format.upper() == 'PKCS11':
                cmd_server_cert_gen += [
                    '-storepass', 'changeit',
                       ]
            else:
                cmd_server_cert_gen += [
                     '-providername', 'BCFIPS',
                     '-provider', 'org.bouncycastle.jcajce.provider.BouncyCastleFipsProvider',
                     '-providerpath',  provider_path,
                     '-keypass:file', self.opendj_trusstore_setup_key_fn,
                     '-storepass:file', self.opendj_trusstore_setup_key_fn,
                     '-keysize', '2048',
                     '-sigalg', 'SHA256WITHRSA',
                        ]

            self.run(cmd_server_cert_gen)


            cmd_server_selfcert_gen = [
                Config.cmd_keytool, '-selfcert',
                '-alias', 'server-cert',
                '-keystore', keystore,
                '-storetype', Config.opendj_truststore_format.upper(),
                '-validity', '3650',
                ]

            if Config.opendj_truststore_format.upper() == 'PKCS11':
                cmd_server_selfcert_gen += [
                    '-storepass', 'changeit'
                    ]

            else:
                cmd_server_selfcert_gen += [
                    '-providername', 'BCFIPS',
                    '-provider', 'org.bouncycastle.jcajce.provider.BouncyCastleFipsProvider',
                    '-providerpath', provider_path,
                    '-storepass:file', self.opendj_trusstore_setup_key_fn,
                    ]

            self.run(cmd_server_selfcert_gen)


            cmd_admin_cert_gen = [
                    Config.cmd_keytool, '-genkey', 
                    '-alias', 'admin-cert', 
                    '-keyalg', 'rsa', 
                    '-dname', 'CN={},O=Administration Connector RSA Self-Signed Certificate'.format(Config.hostname), 
                    '-keystore', keystore, 
                    '-storetype', Config.opendj_truststore_format.upper(),
                    '-validity', '3650',
                    ]


            if Config.opendj_truststore_format.upper() == 'PKCS11':
                cmd_admin_cert_gen += [
                    '-storepass', 'changeit',
                       ]
            else:
                cmd_admin_cert_gen += [
                     '-providername', 'BCFIPS',
                     '-provider', 'org.bouncycastle.jcajce.provider.BouncyCastleFipsProvider',
                     '-providerpath',  provider_path,
                     '-keypass:file', self.opendj_trusstore_setup_key_fn,
                     '-storepass:file', self.opendj_trusstore_setup_key_fn,
                     '-keysize', '2048',
                     '-sigalg', 'SHA256WITHRSA',
                        ]
            self.run(cmd_admin_cert_gen)

            cmd_admin_selfcert_gen = [
                    Config.cmd_keytool, '-selfcert',
                    '-alias', 'admin-cert',
                    '-keystore', keystore,
                    '-storetype', Config.opendj_truststore_format.upper(),
                    '-validity', '3650',
                    ]

            if Config.opendj_truststore_format.upper() == 'PKCS11':
                cmd_admin_selfcert_gen += [
                    '-storepass', 'changeit'
                    ]

            else:
                cmd_admin_selfcert_gen += [
                    '-providername', 'BCFIPS',
                    '-provider', 'org.bouncycastle.jcajce.provider.BouncyCastleFipsProvider',
                    '-providerpath', provider_path,
                    '-storepass:file', self.opendj_trusstore_setup_key_fn,
                    ]

            self.run(cmd_admin_selfcert_gen)

        ldapSetupCommand = os.path.join(os.path.dirname(Config.ldapBinFolder), 'setup')

        setupCmd = [ldapSetupCommand,
                    '--no-prompt',
                    '--cli',
                    '--propertiesFilePath',
                    setupPropsFN,
                    '--acceptLicense',
                    '--doNotStart'
                    ]

        self.run(setupCmd,
                  cwd='/opt/opendj',
                  env={'OPENDJ_JAVA_HOME': Config.jre_home}
                  )

        if Config.profile == SetupProfiles.DISA_STIG and Config.opendj_truststore_format.upper() == 'BCFKS':
            self.run([Config.cmd_keytool, '-importkeystore',
                    '-destkeystore', 'NONE',
                    '-deststoretype', 'PKCS11',
                    '-deststorepass', 'changeit',
                    '-srckeystore', '/opt/opendj/config/truststore',
                    '-srcstoretype', 'JKS',
                    '-srcstorepass:file', '/opt/opendj/config/keystore.pin',
                    '-noprompt'
                    ])

    def post_install_opendj(self):
        try:
            os.remove(os.path.join(Config.ldapBaseFolder, 'opendj-setup.properties'))
        except:
            self.logIt("Error deleting OpenDJ properties. Make sure %s/opendj-setup.properties is deleted" % Config.ldapBaseFolder)

        self.enable()

    def create_backends(self):
        backends = [
                    ['create-backend', '--backend-name', 'metric', '--set', 'base-dn:o=metric', '--type %s' % Config.ldap_backend_type, '--set', 'enabled:true', '--set', 'db-cache-percent:20'],
                    ]

        if Config.mappingLocations['site'] == 'ldap':
            backends.append(['create-backend', '--backend-name', 'site', '--set', 'base-dn:o=site', '--type %s' % Config.ldap_backend_type, '--set', 'enabled:true', '--set', 'db-cache-percent:20'])


        if Config.profile == SetupProfiles.DISA_STIG:
            dsconfigCmd = [
                            self.ldapDsconfigCommand,
                            '--no-prompt',
                            '--hostname',
                            Config.ldap_hostname,
                            '--port',
                            Config.ldap_admin_port,
                            '--bindDN',
                            '"%s"' % Config.ldap_binddn,
                            '--bindPasswordFile', Config.ldapPassFn,
                            ]
            if Config.opendj_truststore_format.upper() == 'PKCS11':
                dsconfigCmd += [
                            '--trustStorePath', self.opendj_admin_truststore_fn,
                            '--keyStorePassword', self.opendj_key_store_password_fn,
                            ]
        else:
            dsconfigCmd = [
                            self.ldapDsconfigCommand,
                            '--trustAll',
                            '--no-prompt',
                            '--hostname',
                            Config.ldap_hostname,
                            '--port',
                            Config.ldap_admin_port,
                            '--bindDN',
                            '"%s"' % Config.ldap_binddn,
                            '--bindPasswordFile',
                            Config.ldapPassFn
                            ]

        for changes in backends:
            cwd = os.path.join(Config.ldapBinFolder)
            self.run(' '.join(dsconfigCmd + changes), shell=True, cwd=cwd, env={'OPENDJ_JAVA_HOME': Config.jre_home})

        # rebind after creating backends
        self.dbUtils.ldap_conn.unbind()
        self.dbUtils.ldap_conn.bind()

    def configure_opendj(self):
        self.logIt("Configuring OpenDJ")

        opendj_config = [
                ('ds-cfg-backend-id=userRoot,cn=Backends,cn=config', 'ds-cfg-db-cache-percent', '70', ldap3.MODIFY_REPLACE),
                ('cn=config', 'ds-cfg-single-structural-objectclass-behavior','accept', ldap3.MODIFY_REPLACE),
                ('cn=config', 'ds-cfg-reject-unauthenticated-requests', 'true', ldap3.MODIFY_REPLACE),
                ('cn=Default Password Policy,cn=Password Policies,cn=config', 'ds-cfg-allow-pre-encoded-passwords', 'true', ldap3.MODIFY_REPLACE),
                ('cn=Default Password Policy,cn=Password Policies,cn=config', 'ds-cfg-default-password-storage-scheme', 'cn=Salted SHA-512,cn=Password Storage Schemes,cn=config', ldap3.MODIFY_REPLACE),
                ('cn=File-Based Audit Logger,cn=Loggers,cn=config', 'ds-cfg-enabled', 'true', ldap3.MODIFY_REPLACE),
                ('cn=LDAP Connection Handler,cn=Connection Handlers,cn=config', 'ds-cfg-enabled', 'false', ldap3.MODIFY_REPLACE),
                ('cn=JMX Connection Handler,cn=Connection Handlers,cn=config', 'ds-cfg-enabled', 'false', ldap3.MODIFY_REPLACE),
                ('cn=Access Control Handler,cn=config', 'ds-cfg-global-aci', '(targetattr!="userPassword||authPassword||debugsearchindex||changes||changeNumber||changeType||changeTime||targetDN||newRDN||newSuperior||deleteOldRDN")(version 3.0; acl "Anonymous read access"; allow (read,search,compare) userdn="ldap:///anyone";)', ldap3.MODIFY_DELETE),        
            ]

        if (not Config.listenAllInterfaces) and (Config.ldap_install == InstallTypes.LOCAL):
            opendj_config.append(('cn=LDAPS Connection Handler,cn=Connection Handlers,cn=config', 'ds-cfg-listen-address', '127.0.0.1', ldap3.MODIFY_REPLACE))
            opendj_config.append(('cn=Administration Connector,cn=config', 'ds-cfg-listen-address', '127.0.0.1', ldap3.MODIFY_REPLACE))

        for dn, attr, val, change_type in opendj_config:
            self.logIt("Changing OpenDJ Configuration for {}".format(dn))
            self.dbUtils.ldap_conn.modify(
                    dn, 
                     {attr: [change_type, val]}
                    )
        #Create uniqueness for attrbiutes
        for cn, attr in (('Unique mail address', 'mail'), ('Unique uid entry', 'uid')):
            self.logIt("Creating OpenDJ uniqueness for {}".format(attr))
            self.dbUtils.ldap_conn.add(
                'cn={},cn=Plugins,cn=config'.format(cn),
                attributes={
                        'objectClass': ['top', 'ds-cfg-plugin', 'ds-cfg-unique-attribute-plugin'],
                        'ds-cfg-java-class': ['org.opends.server.plugins.UniqueAttributePlugin'],
                        'ds-cfg-enabled': ['true'],
                        'ds-cfg-plugin-type': ['postoperationadd', 'postoperationmodify', 'postoperationmodifydn', 'postsynchronizationadd', 'postsynchronizationmodify', 'postsynchronizationmodifydn', 'preoperationadd', 'preoperationmodify', 'preoperationmodifydn'],
                        'ds-cfg-type': [attr],
                        'cn': [cn],
                        'ds-cfg-base-dn': ['o=gluu']
                        }
                )


    def export_opendj_public_cert(self):
        # Load password to acces OpenDJ truststore
        self.logIt("Getting OpenDJ certificate")

        opendj_cert = ssl.get_server_certificate((Config.ldap_hostname, Config.ldaps_port))
        with open(Config.opendj_cert_fn,'w') as w:
            w.write(opendj_cert)

        # Convert OpenDJ certificate to PKCS12
        self.logIt("Importing OpenDJ certificate to truststore")
        self.run([Config.cmd_keytool,
                  '-importcert',
                  '-noprompt',
                  '-alias',
                  'server-cert',
                  '-file',
                  Config.opendj_cert_fn,
                  '-keystore',
                  "NONE" if Config.opendj_truststore_format.upper() == 'PKCS11' else Config.opendj_trust_store_fn,
                  '-storetype',
                  Config.opendj_truststore_format.upper(),
                  '-storepass',
                  Config.opendj_truststore_pass
                  ])

        # Import OpenDJ certificate into java truststore
        self.logIt("Import OpenDJ certificate")

        self.run([Config.cmd_keytool, "-import", "-trustcacerts", "-alias", "%s_opendj" % Config.hostname, \
                  "-file", Config.opendj_cert_fn, "-keystore", Config.defaultTrustStoreFN, \
                  "-storepass", "changeit", "-noprompt"])


    def index_opendj(self):

        self.logIt("Creating OpenDJ Indexes")

        with open(self.openDjIndexJson) as f:
            index_json = json.load(f)

        index_backends = ['userRoot']

        if Config.mappingLocations['site'] == 'ldap':
            index_backends.append('site')

        for attrDict in index_json:
            attr_name = attrDict['attribute']
            for backend in attrDict['backend']:
                if backend in index_backends:
                    dn = 'ds-cfg-attribute={},cn=Index,ds-cfg-backend-id={},cn=Backends,cn=config'.format(attrDict['attribute'], backend)
                    entry = {
                            'objectClass': ['top','ds-cfg-backend-index'],
                            'ds-cfg-attribute': [attrDict['attribute']],
                            'ds-cfg-index-type': attrDict['index'],
                            'ds-cfg-index-entry-limit': ['4000']
                            }
                    self.logIt("Creating Index {}".format(dn))
                    self.dbUtils.ldap_conn.add(dn, attributes=entry)


    def prepare_opendj_schema(self):
        self.logIt("Copying OpenDJ schema")
        for schemaFile in self.openDjschemaFiles:
            self.copyFile(schemaFile, self.openDjSchemaFolder)

        self.run([paths.cmd_chmod, '-R', 'a+rX', Config.ldapBaseFolder])
        self.run([paths.cmd_chown, '-R', 'ldap:ldap', Config.ldapBaseFolder])

        self.logIt("Re-starting OpenDj after schema update")
        self.stop()
        self.start()

    def setup_opendj_service(self):
        if not base.snap:
            init_script_fn = '/etc/init.d/opendj'
            if (base.clone_type == 'rpm' and base.os_initdaemon == 'systemd') or base.deb_sysd_clone:
                remove_init_script = True
                opendj_script_name = os.path.basename(self.opendj_service_centos7)
                opendj_dest_folder = "/etc/systemd/system"
                try:
                    self.copyFile(self.opendj_service_centos7, opendj_dest_folder)
                except:
                    self.logIt("Error copying script file %s to %s" % (opendj_script_name, opendj_dest_folder))
                if os.path.exists(init_script_fn):
                    self.run(['rm', '-f', init_script_fn])
            else:
                self.run([self.ldapDsCreateRcCommand, "--outputFile", "/etc/init.d/opendj", "--userName",  "ldap"])
                # Make the generated script LSB compliant
                lsb_str=(
                        '### BEGIN INIT INFO\n'
                        '# Provides:          opendj\n'
                        '# Required-Start:    $remote_fs $syslog\n'
                        '# Required-Stop:     $remote_fs $syslog\n'
                        '# Default-Start:     2 3 4 5\n'
                        '# Default-Stop:      0 1 6\n'
                        '# Short-Description: Start daemon at boot time\n'
                        '# Description:       Enable service provided by daemon.\n'
                        '### END INIT INFO\n'
                        )
                self.insertLinesInFile("/etc/init.d/opendj", 1, lsb_str)

                if base.os_type in ['ubuntu', 'debian']:
                    self.run([paths.cmd_update_rc, "-f", "opendj", "remove"])

                self.fix_init_scripts('opendj', init_script_fn)

            self.reload_daemon()


    def fix_opendj_java_properties(self):

        #Set memory and default.java-home in java.properties   
        opendj_java_properties_fn = os.path.join(Config.ldapBaseFolder, 'config/java.properties')

        self.logIt("Setting memory and default.java-home in %s" % opendj_java_properties_fn)
        opendj_java_properties = self.readFile(opendj_java_properties_fn).splitlines()
        java_home_ln = 'default.java-home={}'.format(Config.jre_home)
        java_home_ln_w = False

        for i, l in enumerate(opendj_java_properties[:]):
            n = l.find('=')
            if n > -1:
                k = l[:n].strip()
                if k == 'default.java-home':
                    opendj_java_properties[i] = java_home_ln
                    java_home_ln_w = True
                if k == 'start-ds.java-args':
                    if os.environ.get('ce_ldap_xms') and os.environ.get('ce_ldap_xmx'):
                        opendj_java_properties[i] = 'start-ds.java-args=-server -Xms{}m -Xmx{}m -XX:+UseCompressedOops'.format(os.environ['ce_ldap_xms'], os.environ['ce_ldap_xmx'])

        if not java_home_ln_w:
            opendj_java_properties.append(java_home_ln)

        self.writeFile(opendj_java_properties_fn, '\n'.join(opendj_java_properties))



    def fix_opendj_config(self):
        if Config.opendj_truststore_format.upper() == 'PKCS11':
            config_fn = os.path.join(Config.ldapBaseFolder, 'config/config.ldif')
            src = os.path.join(Config.ldapBaseFolder, 'config/truststore')
            dest = os.path.join(Config.ldapBaseFolder, 'config/admin-truststore')
            if not os.path.exists(dest):
                self.run([paths.cmd_ln, '-s', src, dest])

    def installed(self):
        if os.path.exists(self.openDjSchemaFolder):
            ldap_install = InstallTypes.LOCAL
        elif os.path.exists(Config.opendj_p12_fn):
            ldap_install = InstallTypes.REMOTE
        else:
            ldap_install = 0

        return ldap_install
