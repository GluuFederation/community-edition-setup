import re
import os
import time
import pprint
import shutil
import inspect
import glob

from pathlib import Path
from collections import OrderedDict

from setup_app.paths import INSTALL_DIR
from setup_app.static import InstallTypes, SetupProfiles
from setup_app.utils.printVersion import get_war_info
from setup_app.utils import base

class Config:

    # we define statics here so that is is acessible without construction
    gluuOptFolder = '/opt/gluu'
    distFolder = '/opt/dist'
    jre_home = '/opt/jre'
    gluuBaseFolder = '/etc/gluu'
    certFolder = '/etc/certs'
    oxBaseDataFolder = '/var/gluu'
    etc_hosts = '/etc/hosts'
    etc_hostname = '/etc/hostname'
    osDefault = '/etc/default'
    sysemProfile = '/etc/profile'
    node_home = '/opt/node'
    jython_home = '/opt/jython'
    ldapBaseFolder = '/opt/opendj'
    network = '/etc/sysconfig/network'
    jetty_home = '/opt/jetty'
    jetty_base = os.path.join(gluuOptFolder, 'jetty')
    installed_instance = False
    maven_root = 'https://jenkins.gluu.org'
    profile = SetupProfiles.CE

    @classmethod
    def get(self, attr, default=None):
        return getattr(self, attr) if hasattr(self, attr) else default


    @classmethod
    def determine_version(self):
        oxauth_info = get_war_info(os.path.join(self.distGluuFolder, 'oxauth.war'))
        self.oxVersion = oxauth_info['version']
        self.currentGluuVersion = re.search('([\d.]+)', oxauth_info['version']).group().strip('.')
        self.githubBranchName = oxauth_info['branch']

        self.ce_setup_zip = 'https://github.com/GluuFederation/community-edition-setup/archive/%s.zip' % self.githubBranchName

    @classmethod
    def dump(self, dumpFile=False):
        if not os.environ.get('gdebug'):
            return
        myDict = {}
        for obj_name, obj in inspect.getmembers(self):
            obj_name = str(obj_name)
            if not obj_name.startswith('__') and (not callable(obj)):
                myDict[obj_name] = obj

        if dumpFile:
            fn = os.path.join(self.install_dir, 'config-'+time.ctime().replace(' ', '-'))
            with open(fn, 'w') as w:
                w.write(pprint.pformat(myDict, indent=2))
        else:
            pp = pprint.PrettyPrinter(indent=2)
            pp.pprint(myDict)


    @classmethod
    def init(self, install_dir=INSTALL_DIR):

        self.install_dir = install_dir
        self.thread_queue = None
        self.jetty_user = 'jetty'
        self.gluu_user = 'gluu'
        self.gluu_group = 'gluu'
        self.root_user = 'root'
        self.node_user = 'node'
        self.ldap_user = 'ldap'
        self.use_existing_java = base.argsp.j
        self.system_dir = '/etc/systemd/system'
        self.user_group = '{}:{}'.format(self.jetty_user, self.gluu_group)
        self.default_store_type = 'pkcs12'
        self.opendj_truststore_format = 'pkcs12'
        self.default_client_test_store_type = 'pkcs12'
        self.start_oxauth_after = 'network.target'

        if self.profile == SetupProfiles.DISA_STIG:
            self.distFolder = '/var/gluu/dist'

        self.distAppFolder = os.path.join(self.distFolder, 'app')
        self.distGluuFolder = os.path.join(self.distFolder, 'gluu')
        self.distTmpFolder = os.path.join(self.distFolder, 'tmp')
        self.ldapBinFolder = os.path.join(self.ldapBaseFolder, 'bin')

        if self.profile == SetupProfiles.DISA_STIG:
            self.use_existing_java = True
            self.cmd_java = shutil.which('java')
            self.jre_home = Path(self.cmd_java).resolve().parent.parent.as_posix()
            self.cmd_keytool = shutil.which('keytool')
            self.cmd_jar = shutil.which('jar')
            os.environ['GLUU_SERVICES'] = 'installHttpd installOxd installCasa installScimServer installFido2'
            self.default_store_type = 'bcfks'
            self.opendj_truststore_format = base.argsp.opendj_keystore_type
            self.default_client_test_store_type = 'pkcs12'
            self.bc_fips_jar = max(glob.glob(os.path.join(self.distAppFolder, 'bc-fips-*.jar')))
            self.bcpkix_fips_jar = max(glob.glob(os.path.join(self.distAppFolder, 'bcpkix-fips-*.jar')))
        else:
            self.profile = SetupProfiles.CE
            self.cmd_java = os.path.join(self.jre_home, 'bin/java')
            self.cmd_keytool = os.path.join(self.jre_home, 'bin/keytool')
            self.cmd_jar = os.path.join(self.jre_home, 'bin/jar')

        os.environ['OPENDJ_JAVA_HOME'] =  self.jre_home

        #create dummy progress bar that logs to file in case not defined
        progress_log_file = os.path.join(self.install_dir, 'logs', 'progress-bar.log')
        class DummyProgress:

            services = []

            def register(self, installer):
                pass


            def start(self):
                pass

            def progress(self, service_name, msg, incr=False):
                with open(progress_log_file, 'a') as w:
                    w.write("{}: {}\n".format(service_name, msg))

        self.pbar = DummyProgress()

        self.properties_password = None
        self.noPrompt = False

        self.downloadWars = None
        self.templateRenderingDict = {
                                        'oxauthClient_2_inum': 'AB77-1A2B',
                                        'oxauthClient_3_inum': '3E20',
                                        'oxauthClient_4_inum': 'FF81-2D39',
                                        'idp_attribute_resolver_ldap.search_filter': '(|(uid=$requestContext.principalName)(mail=$requestContext.principalName))',
                                        'oxd_port': '8443',
                                        'server_time_zone': 'UTC' + time.strftime("%z"),
                                     }

        # java commands
        self.cmd_java = os.path.join(self.jre_home, 'bin/java')
        self.cmd_keytool = os.path.join(self.jre_home, 'bin/keytool')
        self.cmd_jar = os.path.join(self.jre_home, 'bin/jar')
        os.environ['OPENDJ_JAVA_HOME'] =  self.jre_home

        # Component ithversions
        self.apache_version = None
        self.opendj_version = None

        #passwords
        self.ldapPass = None
        self.oxtrust_admin_password = None
        self.encoded_admin_password = ''
        self.cb_password = None
        self.encoded_cb_password = ''

        #DB installation types
        self.ldap_install = InstallTypes.LOCAL
        self.cb_install = InstallTypes.NONE
        self.rdbm_install = False

        #rdbm
        self.rdbm_install_type = InstallTypes.NONE
        self.rdbm_type = 'mysql'
        self.rdbm_host = 'localhost'
        self.rdbm_port = 3306
        self.rdbm_db = 'gluudb'
        self.rdbm_user = None
        self.rdbm_password = None
        self.static_rdbm_dir = os.path.join(self.install_dir, 'static/rdbm')

        #spanner
        self.spanner_project = 'gluu-project'
        self.spanner_instance = 'gluu-instance'
        self.spanner_database = 'gluudb' 
        self.spanner_emulator_host = None
        self.google_application_credentials = None

        #couchbase
        self.couchbaseBuckets = []

        # Gluu components installation status
        self.loadData = True
        self.installGluu = True
        self.installJre = True
        self.installJetty = True
        self.install_node_app = self.profile == SetupProfiles.CE
        self.installJython = True
        self.installOxAuth = True
        self.installOxTrust = True
        self.installHttpd = True
        self.installSaml = False
        self.installPassport = False
        self.installGluuRadius = False
        self.installScimServer = False
        self.installFido2 = False
        self.installCasa = False
        self.installOxd = False
        self.loadTestData = False
        self.allowPreReleasedFeatures = False

        # backward compatibility
        self.os_type = base.os_type
        self.os_version = base.os_version
        self.os_initdaemon = base.os_initdaemon

        self.persistence_type = 'ldap'

        self.setup_properties_fn = os.path.join(self.install_dir, 'setup.properties')
        self.savedProperties = os.path.join(self.install_dir, 'setup.properties.last')

        self.gluuOptBinFolder = os.path.join(self.gluuOptFolder, 'bin')
        self.gluuOptSystemFolder = os.path.join(self.gluuOptFolder, 'system')
        self.gluuOptPythonFolder = os.path.join(self.gluuOptFolder, 'python')
        self.configFolder = os.path.join(self.gluuBaseFolder, 'conf') 

        self.gluu_properties_fn = os.path.join(self.configFolder,'gluu.properties')
        self.gluu_hybrid_roperties_fn = os.path.join(self.configFolder, 'gluu-hybrid.properties')

        self.cache_provider_type = 'NATIVE_PERSISTENCE'

        self.java_type = 'jre'

        self.hostname = None
        self.ip = None
        self.orgName = None
        self.countryCode = None
        self.city = None
        self.state = None
        self.admin_email = None
        self.encoded_ox_ldap_pw = None
        self.application_max_ram = int(base.current_mem_size * .83 * 1024) # 83% of physical memory
        self.encode_salt = None
        self.admin_inum = None

        self.ldapBaseFolderldapPass = None

        self.outputFolder = os.path.join(self.install_dir, 'output')
        self.templateFolder = os.path.join(self.install_dir, 'templates')
        self.staticFolder = os.path.join(self.install_dir, 'static')

        self.extensionFolder = os.path.join(self.staticFolder, 'extension')

        self.opendj_cert_fn = os.path.join(self.certFolder, 'opendj.crt')
        if self.opendj_truststore_format.lower() == 'pkcs11':
            self.opendj_trust_store_fn = self.opendj_cert_fn
        else:
            self.opendj_trust_store_fn = os.path.join(self.certFolder, 'opendj.' + self.opendj_truststore_format)

        self.oxd_package = base.determine_package(os.path.join(Config.distGluuFolder, 'oxd-server*.tgz'))

        self.opendj_truststore_pass = None


        self.ldap_binddn = 'cn=directory manager'
        self.ldap_hostname = 'localhost'
        self.couchbase_hostname = 'localhost'
        self.ldap_port = '1389'
        self.ldaps_port = '1636'
        self.ldap_admin_port = '4444'

        self.ldap_user_home = self.ldapBaseFolder
        self.ldapPassFn = os.path.join(self.ldap_user_home, '.pw')
        self.ldap_backend_type = 'je'

        self.gluuScriptFiles = [
                            os.path.join(self.install_dir, 'static/scripts/logmanager.sh'),
                            os.path.join(self.install_dir, 'static/scripts/testBind.py'),
                            os.path.join(self.install_dir, 'static/scripts/jetty10CompatibleWar.py'),
                            ]

        self.redhat_services = ['httpd', 'rsyslog']
        self.debian_services = ['apache2', 'rsyslog']

        self.default_trust_store_fn = os.path.join(self.jre_home, 'lib/security/cacerts')

        self.defaultTrustStorePW = 'changeit'


        # Stuff that gets rendered; filename is necessary. Full path should
        # reflect final path if the file must be copied after its rendered.

        self.gluu_python_readme = os.path.join(self.gluuOptPythonFolder, 'libs/python.txt')
        self.ox_ldap_properties = os.path.join(self.configFolder, 'gluu-ldap.properties')
        self.gluuCouchebaseProperties = os.path.join(self.configFolder, 'gluu-couchbase.properties')
        self.gluuRDBMProperties = os.path.join(self.configFolder, 'gluu-sql.properties')
        self.gluuSpannerProperties = os.path.join(self.configFolder, 'gluu-spanner.properties')

        self.ldif_base = os.path.join(self.outputFolder, 'base.ldif')
        self.ldif_attributes = os.path.join(self.outputFolder, 'attributes.ldif')
        self.ldif_scopes = os.path.join(self.outputFolder, 'scopes.ldif')

        self.ldif_metric = os.path.join(self.staticFolder, 'metric/o_metric.ldif')
        self.ldif_site = os.path.join(self.install_dir, 'static/cache-refresh/o_site.ldif')
        self.ldif_configuration = os.path.join(self.outputFolder, 'configuration.ldif')

        self.system_profile_update_init = os.path.join(self.outputFolder, 'system_profile_init')
        self.system_profile_update_systemd = os.path.join(self.outputFolder, 'system_profile_systemd')

        ### rsyslog file customised for init.d
        self.rsyslogUbuntuInitFile = os.path.join(self.install_dir, 'static/system/ubuntu/rsyslog')
        self.ldap_setup_properties = os.path.join(self.templateFolder, 'opendj-setup.properties')

        # OpenID key generation default setting
        self.default_openid_dstore_dn_name = 'CN=oxAuth CA Certificates'

        self.default_sig_key_algs = 'RS256 RS384 RS512 ES256 ES384 ES512 PS256 PS384 PS512'
        self.default_enc_key_algs = 'RSA1_5 RSA-OAEP'

        self.default_key_expiration = 365

        self.post_messages = []

        self.ldif_files = [self.ldif_base,
                           self.ldif_attributes,
                           self.ldif_scopes,
                           self.ldif_site,
                           self.ldif_metric,
                           self.ldif_configuration,
                           ]

        self.ce_templates = {
                             self.gluu_python_readme: True,
                             self.ox_ldap_properties: True,
                             self.etc_hostname: False,
                             self.ldif_base: False,
                             self.ldif_attributes: False,
                             self.ldif_scopes: False,
                             self.network: False,
                             self.gluu_properties_fn: True,
                             }

        self.service_requirements = {
                        'opendj': ['', 70],
                        'oxauth': ['opendj', 72],
                        'fido2': ['opendj', 73],
                        'identity': ['opendj oxauth', 74],
                        'scim': ['opendj oxauth', 75],
                        'idp': ['opendj oxauth', 76],
                        'casa': ['opendj oxauth', 78],
                        'oxd-server': ['opendj oxauth', 80],
                        'passport': ['opendj oxauth', 82],
                        'gluu-radius': ['opendj oxauth', 86],
                        }

        self.install_time_ldap = None

        if base.current_mem_size < 4.0:
            self.system_ram =  500 #MB
            self.opendj_ram = 1280 #MB
        else:
            self.system_ram =  750 #MB
            self.opendj_ram = 1500 #MB

        self.app_mem_weigths = {
                'opendj':    {'weigth' : 75, "min" : 512},
                'oxauth':    {'weigth' : 50, "min" : 128},
                'identity':  {'weigth' : 75, "min" : 128},
                'idp':       {'weigth' : 25, "min" : 128},
                'passport':  {'weigth' : 10, "min" : 128},
                'casa':      {'weigth' : 15, "min" : 128},
                'fido2':     {'weigth' : 10, "min" : 128},
                'scim':      {'weigth' : 10, "min" : 128},
                'oxd':       {'weigth' : 10, "min" : 128},
            }

        self.couchbaseBucketDict = OrderedDict((
                        ('default', { 'ldif':[
                                            self.ldif_base, 
                                            self.ldif_attributes,
                                            self.ldif_scopes,
                                            self.ldif_configuration,
                                            self.ldif_metric,
                                            ],
                                      'memory_allocation': 100,
                                      'mapping': '',
                                      'document_key_prefix': []
                                    }),

                        ('user',     {   'ldif': [],
                                        'memory_allocation': 300,
                                        'mapping': 'people, groups, authorizations',
                                        'document_key_prefix': ['groups_', 'people_', 'authorizations_'],
                                    }),

                        ('site',     {   'ldif': [self.ldif_site],
                                        'memory_allocation': 100,
                                        'mapping': 'cache-refresh',
                                        'document_key_prefix': ['site_', 'cache-refresh_'],
                                    }),

                        ('cache',    {   'ldif': [],
                                        'memory_allocation': 100,
                                        'mapping': 'cache',
                                        'document_key_prefix': ['cache_'],
                                    }),

                        ('token',   { 'ldif': [],
                                      'memory_allocation': 300,
                                      'mapping': 'tokens',
                                      'document_key_prefix': ['tokens_'],
                                    }),

                        ('session',   { 'ldif': [],
                                      'memory_allocation': 200,
                                      'mapping': 'sessions',
                                      'document_key_prefix': [],
                                    }),

                    ))

        self.mappingLocations = { group: 'ldap' for group in self.couchbaseBucketDict }  #default locations are OpenDJ
        self.non_setup_properties = {
            'java_truststore_aliases': [],
            'oxauth_client_jar_fn': os.path.join(self.distGluuFolder, 'oxauth-client-jar-with-dependencies.jar'),
            'oxauth_client_noprivder_jar_fn': os.path.join(self.distGluuFolder, 'oxauth-client-jar-without-provider-dependencies.jar'),
            'service_enable_dict': {
                        'installPassport': ('gluuPassportEnabled', 'enable_scim_access_policy'),
                        'installGluuRadius': ('gluuRadiusEnabled', 'oxauth_legacyIdTokenClaims', 'oxauth_openidScopeBackwardCompatibility', 'enableRadiusScripts'),
                        'installSaml': ('gluuSamlEnabled',),
                        'installScimServer': ('gluuScimEnabled', 'enable_scim_access_policy'),
                    },
                }
        Config.addPostSetupService = []

        self.smtp_jks_fn = os.path.join(self.certFolder, 'smtp-keys' + '.' + Config.default_store_type)
        self.smtp_alias = 'smtp_sig_ec256'
        self.smtp_signing_alg = 'SHA256withECDSA'
