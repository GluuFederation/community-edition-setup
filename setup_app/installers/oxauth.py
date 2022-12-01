import os
import glob
import random
import string

from setup_app import paths
from setup_app.utils import base
from setup_app.config import Config
from setup_app.installers.jetty import JettyInstaller
from setup_app.static import AppType, InstallOption

class OxauthInstaller(JettyInstaller):

    def __init__(self):
        setattr(base.current_app, self.__class__.__name__, self)
        self.service_name = 'oxauth'
        self.app_type = AppType.SERVICE
        self.install_type = InstallOption.OPTONAL
        self.install_var = 'installOxAuth'
        self.register_progess()

        self.source_files = [
                    (os.path.join(Config.distGluuFolder, 'oxauth.war'), Config.maven_root + '/maven/org/gluu/oxauth-server/%s/oxauth-server-%s.war' % (Config.oxVersion, Config.oxVersion)),
                    ]

        self.templates_folder = os.path.join(Config.templateFolder, self.service_name)
        self.output_folder = os.path.join(Config.outputFolder, self.service_name)

        self.ldif_config = os.path.join(self.output_folder, 'configuration.ldif')
        self.ldif_clients = os.path.join(self.output_folder, 'clients.ldif')
        self.oxauth_config_json = os.path.join(self.output_folder, 'oxauth-config.json')
        self.oxauth_static_conf_json = os.path.join(self.templates_folder, 'oxauth-static-conf.json')
        self.oxauth_error_json = os.path.join(self.templates_folder, 'oxauth-errors.json')
        self.oxauth_openid_jwks_fn = os.path.join(self.output_folder, 'oxauth-keys.json')
        self.oxauth_openid_jks_fn = os.path.join(Config.certFolder, self.get_keystore_fn('oxauth-keys'))

        Config.oxauth_legacyIdTokenClaims = 'false'
        Config.oxauth_openidScopeBackwardCompatibility = 'false'


    def install(self):
        self.logIt("Copying oxauth.war into jetty webapps folder...")
        self.profile_templates(self.templates_folder)
        self.installJettyService(self.jetty_app_configuration[self.service_name], True)
        jettyServiceWebapps = os.path.join(self.jetty_base, self.service_name, 'webapps')
        self.copyFile(self.source_files[0][0], jettyServiceWebapps)
        self.enable()


    def generate_configuration(self):
        if not Config.get('oxauth_openid_jks_pass'):
            Config.oxauth_openid_jks_pass = self.getPW()

        self.check_clients([('oxauth_client_id', '1001.')])

        if not Config.get('oxauthClient_pw'):
            Config.oxauthClient_pw = self.getPW()
            Config.oxauthClient_encoded_pw = self.obscure(Config.oxauthClient_pw)

        self.logIt("Generating oxauth openid keys", pbar=self.service_name)
        sig_keys = 'RS256 RS384 RS512 ES256 ES384 ES512 PS256 PS384 PS512'
        enc_keys = 'RSA1_5 RSA-OAEP'
        jwks = self.gen_openid_data_store_keys(self.oxauth_openid_jks_fn, Config.oxauth_openid_jks_pass, key_expiration=2, key_algs=sig_keys, enc_keys=enc_keys)
        self.write_openid_keys(self.oxauth_openid_jwks_fn, jwks)

    def render_import_templates(self):
        Config.templateRenderingDict['person_custom_object_class_list'] = '[]' if Config.mappingLocations['default'] == 'rdbm' else '["gluuCustomPerson", "gluuPerson"]'

        self.renderTemplateInOut(self.oxauth_config_json, self.templates_folder, self.output_folder)

        Config.templateRenderingDict['oxauth_config_base64'] = self.generate_base64_ldap_file(self.oxauth_config_json)
        Config.templateRenderingDict['oxauth_static_conf_base64'] = self.generate_base64_ldap_file(self.oxauth_static_conf_json)
        Config.templateRenderingDict['oxauth_error_base64'] = self.generate_base64_ldap_file(self.oxauth_error_json)
        Config.templateRenderingDict['oxauth_openid_key_base64'] = self.generate_base64_ldap_file(self.oxauth_openid_jwks_fn)

        self.renderTemplateInOut(self.ldif_config, self.templates_folder, self.output_folder)
        self.renderTemplateInOut(self.ldif_clients, self.templates_folder, self.output_folder)

        self.dbUtils.import_ldif([self.ldif_config, self.ldif_clients])


    def genRandomString(self, N):
        return ''.join(random.SystemRandom().choice(string.ascii_lowercase
                                                    + string.ascii_uppercase
                                                    + string.digits) for _ in range(N))

    def make_salt(self, enforce=False):
        if not Config.get('pairwiseCalculationKey') or enforce:
            Config.pairwiseCalculationKey = self.genRandomString(random.randint(20,30))
        if not Config.get('pairwiseCalculationSalt') or enforce:
            Config.pairwiseCalculationSalt = self.genRandomString(random.randint(20,30))

    def copy_static(self):
        self.copyFile(
                os.path.join(Config.install_dir, 'static/auth/lib/duo_web.py'),
                os.path.join(Config.gluuOptPythonFolder, 'libs' )
            )
        
        for conf_fn in ('duo_creds.json', 'gplus_client_secrets.json', 'super_gluu_creds.json',
                        'vericloud_gluu_creds.json', 'cert_creds.json', 'otp_configuration.json'):
            
            src_fn = os.path.join(Config.install_dir, 'static/auth/conf', conf_fn)
            self.copyFile(src_fn, Config.certFolder)
