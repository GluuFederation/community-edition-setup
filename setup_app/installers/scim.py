import os
import glob
import shutil
import json

from setup_app.utils import base
from setup_app.static import AppType, InstallOption
from setup_app.config import Config
from setup_app.installers.jetty import JettyInstaller
from setup_app.pylib.ldif4.ldif import LDIFWriter

class ScimInstaller(JettyInstaller):

    def __init__(self):
        setattr(base.current_app, self.__class__.__name__, self)
        self.service_name = 'scim'
        self.needdb = True
        self.app_type = AppType.SERVICE
        self.install_type = InstallOption.OPTONAL
        self.install_var = 'installScimServer'
        self.register_progess()

        self.source_files = [
                (os.path.join(Config.distGluuFolder, 'scim.war'), Config.maven_root + '/maven/org/gluu/scim-server/{0}/scim-server-{0}.war'.format(Config.oxVersion))
                ]

        self.templates_folder = os.path.join(Config.templateFolder, self.service_name)
        self.output_folder = os.path.join(Config.outputFolder, self.service_name)
        self.oxtrust_config_fn = os.path.join(self.output_folder, 'oxtrust_config.json')
        self.ldif_config = os.path.join(self.output_folder, 'configuration.ldif')
        self.scim_ldif = os.path.join(self.output_folder, 'scim.ldif')
        self.ldif_clients = os.path.join(self.output_folder, 'clients.ldif')
        self.scope_ldif_fn = os.path.join(self.output_folder, 'scopes.ldif')

        self.scim_rs_client_jks_fn = os.path.join(Config.certFolder, 'scim-rs.jks')
        self.scim_rp_client_jks_fn = os.path.join(Config.outputFolder, 'scim-rp.jks')


    def install(self):
        self.logIt("Copying scim.war into jetty webapps folder...")

        self.installJettyService(self.jetty_app_configuration[self.service_name], True)
        jettyServiceWebapps = os.path.join(self.jetty_base, self.service_name,  'webapps')
        self.copyFile(self.source_files[0][0], jettyServiceWebapps)
        self.enable()


    def generate_configuration(self):

        if Config.get('scim_protection_mode') not in ('TEST', 'UMA', 'OAUTH'):
            if base.argsp.enable_scim_test_mode:
                Config.scim_protection_mode = 'TEST'
            elif base.argsp.enable_scim_uma_mode:
                Config.scim_protection_mode = 'UMA'
            else:
                Config.scim_protection_mode = 'OAUTH'

        self.logIt("Generating {} configuration".format(self.service_name))
        client_var_id_list = (
                    ('scim_rs_client_id', '1201.'),
                    ('scim_rp_client_id', '1202.'),
                    )
        self.check_clients(client_var_id_list)
        self.check_clients([('scim_resource_oxid', '1203.')], resource=True)

        if not Config.get('scim_rs_client_jks_pass'):
            Config.scim_rs_client_jks_pass = self.getPW()
        
        Config.scim_rs_client_jks_pass_encoded = self.obscure(Config.scim_rs_client_jks_pass)

        if not Config.get('scim_rp_client_jks_pass'):
            Config.scim_rp_client_jks_pass = self.getPW()

        Config.enable_scim_access_policy = 'true' if Config.installPassport else 'false'

        #backup current jks files if exists
        for jks_fn in (self.scim_rs_client_jks_fn, self.scim_rp_client_jks_fn):
            if os.path.exists(jks_fn):
                self.backupFile(jks_fn, move=True)

        Config.scim_rs_client_jwks = self.gen_openid_data_store_keys(self.scim_rs_client_jks_fn, Config.scim_rs_client_jks_pass)
        Config.templateRenderingDict['scim_rs_client_base64_jwks'] = self.generate_base64_string(Config.scim_rs_client_jwks, 1)

        Config.scim_rp_client_jwks = self.gen_openid_data_store_keys(self.scim_rp_client_jks_fn, Config.scim_rp_client_jks_pass)
        Config.templateRenderingDict['scim_rp_client_base64_jwks'] = self.generate_base64_string(Config.scim_rp_client_jwks, 1)

        self.copyFile(self.scim_rp_client_jks_fn, Config.certFolder)

    def create_folders(self):
        for d in (self.output_folder,):
            if not os.path.exists(d):
                self.createDirs(d)

    def scopes(self):

        scopes_def = (
            ('https://gluu.org/scim/users.read','Query user resources'),
            ('https://gluu.org/scim/users.write','Modify user resources'),
            ('https://gluu.org/scim/groups.read','Query group resources'),
            ('https://gluu.org/scim/groups.write','Modify group resources'),
            ('https://gluu.org/scim/fido.read','Query fido resources'),
            ('https://gluu.org/scim/fido.write','Modify fido resources'),
            ('https://gluu.org/scim/fido2.read','Query fido 2 resources'),
            ('https://gluu.org/scim/fido2.write','Modify fido 2 resources'),
            ('https://gluu.org/scim/all-resources.search','Access the root .search endpoint'),
            ('https://gluu.org/scim/bulk','Send requests to the bulk endpoint'),
            )

        scim_scopes = []
        scope_ldif_fd = open(self.scope_ldif_fn, 'wb')
        ldif_scopes_writer = LDIFWriter(scope_ldif_fd, cols=1000)

        for oxId, desc in scopes_def:

            if Config.installed_instance and self.dbUtils.search('ou=scopes,o=jans', search_filter='(&(oxId={})(objectClass=oxAuthCustomScope))'.format(oxId)):
                continue

            inum = '1200.' + os.urandom(3).hex().upper()
            scope_dn = 'inum={},ou=scopes,o=gluu'.format(inum)
            display_name = 'Scim scope {}'.format(oxId.split('/')[-1])
            ldif_scopes_writer.unparse(
                    scope_dn, {
                        'objectclass': ['top', 'oxAuthCustomScope'],
                        'description': [desc],
                        'displayName': [display_name],
                        'inum': [inum],
                        'defaultScope': ['false'],
                        'oxId': [oxId],
                        'oxScopeType': ['oauth'],
                        'oxAttributes': [json.dumps({"spontaneousClientId":"","spontaneousClientScopes":[],"showInConfigurationEndpoint":False})],
                    })

            scim_scopes.append(scope_dn)

        scope_ldif_fd.close()


    def render_import_templates(self):
        self.scopes()

        self.renderTemplateInOut(self.ldif_config, self.templates_folder, self.output_folder)
        self.renderTemplateInOut(self.scim_ldif, self.templates_folder, self.output_folder)
        self.renderTemplateInOut(self.ldif_clients, self.templates_folder, self.output_folder)
        self.renderTemplateInOut(self.oxtrust_config_fn, self.templates_folder, self.output_folder)

        self.dbUtils.import_ldif([self.scim_ldif, self.ldif_config, self.ldif_clients, self.scope_ldif_fn])

    def update_backend(self):
        oxtrust_config = base.readJsonFile(self.oxtrust_config_fn)
        self.dbUtils.set_oxTrustConfApplication(oxtrust_config)

        self.dbUtils.add_client2script('2DAF-F9A5', Config.scim_rp_client_id)
        self.dbUtils.add_client2script('2DAF-F995', Config.scim_rp_client_id)
        self.dbUtils.enable_script('2DAF-F9A5')
        self.dbUtils.enable_service('gluuScimEnabled')
