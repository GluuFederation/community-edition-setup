import os
import glob
import socket
import ruamel.yaml
import tempfile

from setup_app import paths
from setup_app.static import AppType, InstallOption, fapolicyd_rule_tmp
from setup_app.utils import base
from setup_app.config import Config
from setup_app.utils.setup_utils import SetupUtils, SetupProfiles
from setup_app.installers.base import BaseInstaller

class OxdInstaller(SetupUtils, BaseInstaller):

    def __init__(self):
        setattr(base.current_app, self.__class__.__name__, self)
        self.service_name = 'oxd-server'
        self.oxd_root = '/opt/oxd-server/'
        self.needdb = False # we don't need backend connection in this class
        self.app_type = AppType.SERVICE
        self.install_type = InstallOption.OPTONAL
        self.install_var = 'installOxd'
        self.register_progess()

        self.oxd_server_yml_fn = os.path.join(self.oxd_root, 'conf/oxd-server.yml')
        self.oxd_server_keystore_fn = os.path.join(self.oxd_root, 'conf/oxd-server.{}'.format(Config.default_store_type))
        self.oxd_jwks_keystore_fn = os.path.join(self.oxd_root, 'conf/oxd-jwks.{}'.format(Config.default_store_type))

        self.oxd_keystore_passw = 'example'
        self.fips_provider = self.get_keytool_provider()
        self.ks_type_bcfks = 'bcfks'
        self.ks_type_pkcs12 = 'pkcs12'

    @property
    def oxd_hostname(self):
        oxd_hostname, oxd_port = self.parse_url(Config.oxd_server_https)
        return oxd_hostname

    def install(self):
        self.logIt("Installing {}".format(self.service_name.title()), pbar=self.service_name)
        self.run(['tar', '-zxf', Config.oxd_package, '--no-same-owner', '--strip-components=1', '-C', self.oxd_root])

        oxd_user = 'oxd-server' if Config.profile == SetupProfiles.DISA_STIG else Config.jetty_user
        Config.templateRenderingDict['service_user'] = oxd_user 
        self.render_unit_file(self.service_name)

        if Config.profile == SetupProfiles.DISA_STIG:
            self.create_service_user(oxd_user)

        self.log_dir = '/var/log/oxd-server'
        service_file = os.path.join(self.oxd_root, 'oxd-server.service')
        if os.path.exists(service_file):
            self.run(['cp', service_file, '/lib/systemd/system'])
        else:
            self.run([Config.cmd_ln, service_file, '/etc/init.d/oxd-server'])

        if not os.path.exists(self.log_dir):
            self.run([paths.cmd_mkdir, self.log_dir])

        oxd_default = self.readFile(os.path.join(Config.install_dir, 'static/oxd/oxd-server.default'))
        rendered_oxd_default = self.fomatWithDict(oxd_default, self.merge_dicts(Config.__dict__, Config.templateRenderingDict))
        self.writeFile(os.path.join(Config.osDefault, 'oxd-server'), rendered_oxd_default)

        self.log_file = os.path.join(self.log_dir, 'oxd-server.log')
        if not os.path.exists(self.log_file):
            open(self.log_file, 'w').close()

        self.run([paths.cmd_chown, '-R', '{0}:{0}'.format(oxd_user), self.log_dir])

        for fn in glob.glob(os.path.join(self.oxd_root,'bin/*')):
            self.run([paths.cmd_chmod, '+x', fn])

        if not base.argsp.dummy:
            self.modify_config_yml()
            self.generate_keystore()
            self.import_oxd_certificate()

        self.run([paths.cmd_chown, '-R', '{0}:{0}'.format(oxd_user), self.oxd_root])

        if Config.profile == SetupProfiles.DISA_STIG:
            log_dir = '/var/log/oxd-server/'
            oxd_fapolicyd_rules = [
                    fapolicyd_rule_tmp.format(oxd_user, Config.jre_home),
                    fapolicyd_rule_tmp.format(oxd_user, log_dir),
                    fapolicyd_rule_tmp.format(oxd_user, self.oxd_root),
                    '# give access to oxd-server',
                    ]

            self.apply_fapolicyd_rules(oxd_fapolicyd_rules)
            # Restore SELinux Context
            self.run(['restorecon', '-rv', os.path.join(self.oxd_root, 'bin')])

            self.run([paths.cmd_chown, '{}:{}'.format(oxd_user, Config.gluu_group), os.path.join(Config.osDefault, self.service_name)])

        self.enable()

    def modify_config_yml(self):
        self.logIt("Configuring", pbar=self.service_name)
        yml_str = self.readFile(self.oxd_server_yml_fn)
        oxd_yaml = ruamel.yaml.load(yml_str, ruamel.yaml.RoundTripLoader)

        addr_list = [Config.ip]
        lo = '127.0.0.1'
        if self.oxd_hostname == 'localhost':
            addr_list.append(lo)

        if 'bind_ip_addresses' in oxd_yaml:
            oxd_yaml['bind_ip_addresses'] += addr_list
        else:
            for i, k in enumerate(oxd_yaml):
                if k == 'storage':
                    break
            else:
                i = 1
            
            if Config.profile == SetupProfiles.DISA_STIG and lo not in addr_list:
                addr_list.append(lo)
            oxd_yaml.insert(i, 'bind_ip_addresses',  addr_list)

        if Config.get('oxd_use_gluu_storage'):

            if 'dbFileLocation' in oxd_yaml['storage_configuration']:
                oxd_yaml['storage_configuration'].pop('dbFileLocation')
            oxd_yaml['storage'] = 'gluu_server_configuration'
            oxd_yaml['storage_configuration']['baseDn'] = 'o=gluu'
            oxd_yaml['storage_configuration']['type'] = Config.gluu_properties_fn
            if Config.mappingLocations['default'] == 'ldap':
                oxd_yaml['storage_configuration']['connection'] = Config.ox_ldap_properties
            elif Config.mappingLocations['default'] == 'rdbm':
                if Config.rdbm_type in ('mysql', 'pgsql'):
                    oxd_yaml['storage_configuration']['connection'] = Config.gluuRDBMProperties
                elif Config.rdbm_type == 'spanner':
                    oxd_yaml['storage_configuration']['connection'] = Config.gluuSpannerProperties
            elif Config.mappingLocations['default'] == 'couchbase':
                oxd_yaml['storage_configuration']['connection'] = Config.gluuCouchebaseProperties
            oxd_yaml['storage_configuration']['salt'] = os.path.join(Config.configFolder, "salt")

        if Config.profile == SetupProfiles.DISA_STIG:
            application_connectors = oxd_yaml['server']['applicationConnectors'][0]
            application_connectors['type'] = 'https'
            application_connectors['port'] = '8443'
            application_connectors['keyStorePath'] = self.oxd_server_keystore_fn
            application_connectors['keyStorePassword'] = self.oxd_keystore_passw
            application_connectors['keyStoreType'] = Config.default_store_type
            application_connectors['keyStoreProvider'] = self.fips_provider['-providername']
            application_connectors['trustStoreType'] = Config.default_store_type
            application_connectors['jceProvider'] = self.fips_provider['-providerclass']
            application_connectors['validateCerts'] = 'false'

            admin_connectors = oxd_yaml['server']['adminConnectors'][0]
            admin_connectors['type'] = 'https'
            admin_connectors['port'] = '8444'
            admin_connectors['keyStorePath'] = self.oxd_server_keystore_fn
            admin_connectors['keyStorePassword'] = self.oxd_keystore_passw
            admin_connectors['keyStoreType'] = Config.default_store_type
            admin_connectors['keyStoreProvider'] = self.fips_provider['-providername']
            admin_connectors['trustStoreType'] = Config.default_store_type
            admin_connectors['jceProvider'] = self.fips_provider['-providerclass']
            admin_connectors['validateCerts'] = 'false'

            oxd_yaml['crypt_provider_key_store_path']=self.oxd_jwks_keystore_fn
            oxd_yaml['crypt_provider_key_store_password']=self.oxd_keystore_passw

        yml_str = ruamel.yaml.dump(oxd_yaml, Dumper=ruamel.yaml.RoundTripDumper)
        self.writeFile(self.oxd_server_yml_fn, yml_str)

    def generate_keystore(self):
        self.logIt("Generating certificate", pbar=self.service_name)
        # generate oxd-server.keystore for the hostname

        keystore_tmp = '{}/oxd.{}'.format(tempfile.gettempdir(), Config.default_store_type)

        if Config.profile == SetupProfiles.DISA_STIG:

            cmd_cert_gen = [
                Config.cmd_keytool, '-genkey',
                '-alias', Config.hostname,
                '-keyalg', 'rsa',
                '-dname', 'CN={},O=OXD RSA Self-Signed Certificate'.format(Config.hostname),
                '-keystore', keystore_tmp,
                '-storetype', self.ks_type_bcfks,
                '-validity', '3650',
                ]

            cmd_cert_gen += [
                '-providername', self.fips_provider['-providername'],
                '-provider', self.fips_provider['-providerclass'],
                '-providerpath',  self.fips_provider['-providerpath'],
                '-keypass', self.oxd_keystore_passw,
                '-storepass', self.oxd_keystore_passw,
                '-keysize', '2048',
                '-sigalg', 'SHA256WITHRSA',
                    ]

            self.run(cmd_cert_gen)

        elif self.oxd_hostname != 'localhost':
            oxd_key_tmp = '{}/{}'.format(tempfile.gettempdir(),'oxd.key')
            oxd_crt_tmp = '{}/{}'.format(tempfile.gettempdir(),'oxd.crt')
            oxd_p12_tmp = '{}/{}'.format(tempfile.gettempdir(),'oxd.p12')

            self.run([
                paths.cmd_openssl,
                'req', '-x509', '-newkey', 'rsa:4096', '-nodes',
                '-out', oxd_crt_tmp,
                '-keyout', oxd_key_tmp,
                '-days', '3650',
                '-subj', '/C={}/ST={}/L={}/O={}/CN={}/emailAddress={}'.format(Config.countryCode, Config.state, Config.city, Config.orgName, Config.hostname, Config.admin_email),
                ])

            self.run([
                paths.cmd_openssl,
                'pkcs12', '-export',
                '-in', oxd_crt_tmp,
                '-inkey', oxd_key_tmp,
                '-out', oxd_p12_tmp,
                '-name', Config.hostname,
                '-passout', 'pass:{}'.format(self.oxd_keystore_passw)
                ])

            self.run([
                Config.cmd_keytool,
                '-importkeystore',
                '-deststorepass', self.oxd_keystore_passw,
                '-destkeypass', self.oxd_keystore_passw,
                '-destkeystore', keystore_tmp,
                '-srckeystore', oxd_p12_tmp,
                '-srcstoretype', self.ks_type_pkcs12,
                '-srcstorepass', self.oxd_keystore_passw,
                '-alias', Config.hostname,
                ])

            for f in (oxd_key_tmp, oxd_crt_tmp, oxd_p12_tmp):
                self.run([paths.cmd_rm, '-f', f])

        if os.path.exists(keystore_tmp):
            self.run([paths.cmd_rm, '-f', os.path.join(self.oxd_root,'conf/oxd-server.keystore')])
            self.run(['cp', '-f', keystore_tmp, self.oxd_server_keystore_fn])
            self.run([paths.cmd_rm, '-f', keystore_tmp])

        self.run([paths.cmd_chown, 'jetty:jetty', self.oxd_server_keystore_fn])


    def installed(self):
        return os.path.exists(self.oxd_server_yml_fn)

    def download_files(self, force=False):
        oxd_url = Config.maven_root + '/maven/org/gluu/oxd-server/{0}/oxd-server-{0}-distribution.zip'.format(Config.oxVersion)

        self.logIt("Downloading {} and preparing package".format(os.path.basename(oxd_url)))

        oxd_zip_fn = os.path.join(Config.outputFolder, 'oxd-server.zip')
        oxd_tgz_fn = os.path.join(Config.distGluuFolder, 'oxd-server.tgz')
        tmp_dir = os.path.join('/tmp', os.urandom(5).hex())
        oxd_tmp_dir = os.path.join(tmp_dir, 'oxd-server')

        self.run([paths.cmd_mkdir, '-p', oxd_tmp_dir])
        self.download_file(oxd_url, oxd_zip_fn)
        self.run([paths.cmd_unzip, '-qqo', oxd_zip_fn, '-d', oxd_tmp_dir])
        self.run([paths.cmd_mkdir, os.path.join(oxd_tmp_dir, 'data')])

        service_file = 'oxd-server.init.d' if base.deb_sysd_clone else 'oxd-server.service'
        service_url = 'https://raw.githubusercontent.com/GluuFederation/community-edition-package/master/package/systemd/oxd-server.service'.format(Config.oxVersion, service_file)
        self.download_file(service_url, os.path.join(oxd_tmp_dir, service_file))

        oxd_server_sh_url = 'https://raw.githubusercontent.com/GluuFederation/oxd/master/debian/oxd-server'
        self.download_file(oxd_server_sh_url, os.path.join(oxd_tmp_dir, 'bin/oxd-server'))

        self.run(['tar', '-zcf', oxd_tgz_fn, 'oxd-server'], cwd=tmp_dir)
        #self.run(['rm', '-r', '-f', tmp_dir])
        Config.oxd_package = oxd_tgz_fn


    def import_oxd_certificate(self):

        oxd_alias = 'oxd_' + self.oxd_hostname.replace('.','_')
        oxd_cert_fn = os.path.join(Config.outputFolder, '{}.pem'.format(oxd_alias))
        # let's delete if alias exists
        self.delete_key(oxd_alias)
        store_alias = 'localhost' if self.oxd_hostname == 'localhost' else Config.hostname
        self.export_cert_from_store(store_alias, self.oxd_server_keystore_fn, self.oxd_keystore_passw, oxd_cert_fn)
        self.import_cert_to_java_truststore(oxd_alias, oxd_cert_fn)


    def create_folders(self):
        if not os.path.exists(self.oxd_root):
            self.run([paths.cmd_mkdir, self.oxd_root])

