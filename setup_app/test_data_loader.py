import os
import glob
import time
import json
import ldap3
import uuid

from setup_app import paths
from setup_app import static
from setup_app.utils import base
from setup_app.config import Config
from setup_app.utils.setup_utils import SetupUtils
from setup_app.installers.base import BaseInstaller
from setup_app.utils.ldif_utils import myLdifParser, schema2json
from setup_app.pylib.schema import ObjectClass
from setup_app.pylib.ldif4.ldif import LDIFWriter


class TestDataLoader(BaseInstaller, SetupUtils):

    def __init__(self):
        self.service_name = 'test-data'
        self.pbar_text = "Loading" 
        self.needdb = True
        self.app_type = static.AppType.APPLICATION
        self.install_type = static.InstallOption.OPTONAL
        self.install_var = 'loadTestData'
        self.register_progess()

        self.template_base = os.path.join(Config.templateFolder, 'test')
        self.test_client_keystore_fn = os.path.join(Config.outputFolder, 'test/oxauth/client', self.get_client_test_keystore_fn('client_keystore'))
        Config.templateRenderingDict['test_client_keystore_base_fn'] = os.path.basename(self.test_client_keystore_fn)


    def create_test_client_keystore(self):

        self.logIt("Creating {}".format(Config.templateRenderingDict['test_client_keystore_base_fn']))
        keys_json_fn =  os.path.join(Config.outputFolder, 'test/oxauth/client/keys_client_keystore.json')

        client_cmd = self.get_key_gen_client_provider_cmd()

        args = [Config.cmd_java, '-Dlog4j.defaultInitOverride=true',
                "-cp", client_cmd,
                Config.non_setup_properties['key_gen_path'],
                '-keystore', self.test_client_keystore_fn,
                '-keystore_type', Config.default_store_type,
                '-keypasswd', 'secret',
                '-sig_keys', Config.default_sig_key_algs,
                '-enc_keys', Config.default_enc_key_algs,
                '-dnname', "'{}'".format(Config.default_openid_dstore_dn_name),
                '-expiration', '365','>', keys_json_fn]

        cmd = ' '.join(args)

        self.run(cmd, shell=True)

        self.copyFile(self.test_client_keystore_fn, os.path.join(Config.outputFolder, 'test/oxauth/server'))
        self.copyFile(keys_json_fn, os.path.join(Config.outputFolder, 'test/oxauth/server'))

    def encode_test_passwords(self):
        self.logIt("Encoding test passwords")
        hostname = Config.hostname.split('.')[0]
        try:
            Config.templateRenderingDict['oxauthClient_2_pw'] = Config.templateRenderingDict['oxauthClient_2_inum'] + '-' + hostname
            Config.templateRenderingDict['oxauthClient_2_encoded_pw'] = self.obscure(Config.templateRenderingDict['oxauthClient_2_pw'])

            Config.templateRenderingDict['oxauthClient_3_pw'] =  Config.templateRenderingDict['oxauthClient_3_inum'] + '-' + hostname
            Config.templateRenderingDict['oxauthClient_3_encoded_pw'] = self.obscure(Config.templateRenderingDict['oxauthClient_3_pw'])

            Config.templateRenderingDict['oxauthClient_4_pw'] = Config.templateRenderingDict['oxauthClient_4_inum'] + '-' + hostname
            Config.templateRenderingDict['oxauthClient_4_encoded_pw'] = self.obscure(Config.templateRenderingDict['oxauthClient_4_pw'])

            testadmin_inum = str(uuid.uuid4())
            oxtrust_testadmin_password = base.argsp.testadmin_password or self.getPW()
            encoded_oxtrust_testadmin_password = self.ldap_encode(oxtrust_testadmin_password)
            Config.templateRenderingDict['testadmin_inum'] = testadmin_inum
            Config.templateRenderingDict['encoded_oxtrust_testadmin_password'] = encoded_oxtrust_testadmin_password
        except Exception:
            self.logIt("Error encoding test passwords", True)


    def load_test_data(self):
        Config.pbar.progress(self.service_name, "Loading Test Data", False)

        if Config.rdbm_install_type and not hasattr(base.current_app.RDBMInstaller, 'qchar'):
            base.current_app.RDBMInstaller.prepare()

        if 'key_gen_path' not in Config.non_setup_properties:
            base.current_app.GluuInstaller.determine_key_gen_path()

        Config.templateRenderingDict['rdbm_type_name'] = 'postgresql' if Config.rdbm_type == 'pgsql' else Config.rdbm_type
        Config.templateRenderingDict['rdbm_scheme'] = 'public' if Config.rdbm_type == 'pgsql' else 'gluudb'

        # we need ldap rebind
        if Config.persistence_type == 'ldap':
            try:
                self.dbUtils.ldap_conn.unbind()
            except:
                pass
            self.dbUtils.ldap_conn.bind()

        if not base.current_app.ScimInstaller.installed():
            self.logIt("Scim was not installed. Installing")
            Config.installScimServer = True
            base.current_app.ScimInstaller.start_installation()

        self.encode_test_passwords()

        Config.pbar.progress(self.service_name, "Rendering test templates", False)
        Config.templateRenderingDict['config_oxauth_test_ldap'] = '# ldap backend is not available'
        Config.templateRenderingDict['config_oxauth_test_couchbase'] = '# couchbase backend is not available'
        Config.templateRenderingDict['config_oxauth_test_spanner'] = '# spanner backend is not available'
        Config.templateRenderingDict['config_oxauth_test_sql'] = '# rdbm backend is not available'

        if self.getMappingType('ldap'):
            template_text = self.readFile(os.path.join(self.template_base, 'oxauth/server/config-oxauth-test-ldap.properties.nrnd'))
            rendered_text = self.fomatWithDict(template_text, self.merge_dicts(Config.__dict__, Config.templateRenderingDict))
            Config.templateRenderingDict['config_oxauth_test_ldap'] = rendered_text

        if self.getMappingType('couchbase'):
            cb_propt_dict = base.current_app.CouchbaseInstaller.couchbaseDict()
            cb_propt_dict['ssl_enabled'] = 'false'
            Config.templateRenderingDict.update(cb_propt_dict)
            template_text = self.readFile(os.path.join(self.template_base, 'oxauth/server/config-oxauth-test-couchbase.properties.nrnd'))
            rendered_text = self.fomatWithDict(template_text, self.merge_dicts(Config.__dict__, Config.templateRenderingDict))
            Config.templateRenderingDict['config_oxauth_test_couchbase'] = rendered_text

        if self.getMappingType('rdbm'):
            if Config.rdbm_type == 'spanner': 
                template_text = self.readFile(os.path.join(self.template_base, 'oxauth/server/config-oxauth-test-spanner.properties.nrnd'))
                rendered_text = self.fomatWithDict(template_text, self.merge_dicts(Config.__dict__, Config.templateRenderingDict))
                Config.templateRenderingDict['config_oxauth_test_spanner'] = rendered_text
            else:
                template_text = self.readFile(os.path.join(self.template_base, 'oxauth/server/config-oxauth-test-sql.properties.nrnd'))
                rendered_text = self.fomatWithDict(template_text, self.merge_dicts(Config.__dict__, Config.templateRenderingDict))
                Config.templateRenderingDict['config_oxauth_test_sql'] = rendered_text


            self.logIt("Adding custom attributs and indexes")

            schema2json(
                    os.path.join(Config.templateFolder, 'test/oxauth/schema/102-oxauth_test.ldif'),
                    os.path.join(Config.outputFolder, 'test/oxauth/schema/')
                    )
            schema2json(
                    os.path.join(Config.templateFolder, 'test/scim-client/schema/103-scim_test.ldif'),
                    os.path.join(Config.outputFolder, 'test/scim-client/schema/'),
                    )

            oxauth_json_schema_fn =os.path.join(Config.outputFolder, 'test/oxauth/schema/102-oxauth_test.json')
            
            oxauth_schema = base.readJsonFile(oxauth_json_schema_fn)
            oxauth_schema['objectClasses'][0]['names'] = ['oxAuthClient']

            with open(oxauth_json_schema_fn, 'w') as w:
                json.dump(oxauth_schema, w, indent=2)

            scim_json_schema_fn = os.path.join(Config.outputFolder, 'test/scim-client/schema/103-scim_test.json')
            gluu_schema_json_files = [ oxauth_json_schema_fn, scim_json_schema_fn ]

            scim_schema = base.readJsonFile(scim_json_schema_fn)
            may_list = []

            for attribute in scim_schema['attributeTypes']:
                may_list += attribute['names']

            gluuPerson = {
                        'kind': 'STRUCTURAL',
                        'may': may_list,
                        'must': ['objectclass'],
                        'names': ['gluuPerson'],
                        'oid': 'gluuObjClass',
                        'sup': ['top'],
                        'x_origin': 'Gluu created objectclass'
                        }
            scim_schema['objectClasses'].append(gluuPerson)

            with open(scim_json_schema_fn, 'w') as w:
                json.dump(scim_schema, w, indent=2)

            self.dbUtils.read_gluu_schema(others=gluu_schema_json_files)

            base.current_app.RDBMInstaller.create_tables(gluu_schema_json_files)
            if Config.rdbm_type != 'spanner': 
                self.dbUtils.rdm_automapper(force=True)

        self.render_templates_folder(self.template_base)

        Config.pbar.progress(self.service_name, "Loading test ldif files", False)
        if not base.current_app.PassportInstaller.installed() and Config.profile != static.SetupProfiles.DISA_STIG:
            base.current_app.PassportInstaller.generate_configuration()

        ox_auth_test_ldif = os.path.join(Config.outputFolder, 'test/oxauth/data/oxauth-test-data.ldif')
        ox_auth_test_user_ldif = os.path.join(Config.outputFolder, 'test/oxauth/data/oxauth-test-data-user.ldif')
        
        scim_test_ldif = os.path.join(Config.outputFolder, 'test/scim-client/data/scim-test-data.ldif')
        scim_test_user_ldif = os.path.join(Config.outputFolder, 'test/scim-client/data/scim-test-data-user.ldif')

        ldif_files = (ox_auth_test_ldif, scim_test_ldif, ox_auth_test_user_ldif, scim_test_user_ldif)
        self.dbUtils.import_ldif(ldif_files)

        apache_user = 'www-data' if base.clone_type == 'deb' else 'apache'

        # Client keys deployment
        base.download('https://raw.githubusercontent.com/GluuFederation/oxAuth/master/Client/src/test/resources/oxauth_test_client_keys.zip', '/var/www/html/oxauth_test_client_keys.zip')        
        self.run([paths.cmd_unzip, '-o', '/var/www/html/oxauth_test_client_keys.zip', '-d', '/var/www/html/'])
        self.run([paths.cmd_rm, '-rf', 'oxauth_test_client_keys.zip'])
        self.run([paths.cmd_chown, '-R', 'root:'+apache_user, '/var/www/html/oxauth-client'])


        oxAuthConfDynamic_changes = {
                                    'dynamicRegistrationCustomObjectClass':  'oxAuthClientCustomAttributes',
                                    'dynamicRegistrationCustomAttributes': [ "oxAuthTrustedClient", "myCustomAttr1", "myCustomAttr2", "oxIncludeClaimsInIdToken" ],
                                    'dynamicRegistrationExpirationTime': 86400,
                                    'grantTypesAndResponseTypesAutofixEnabled': True,
                                    'dynamicGrantTypeDefault': [ "authorization_code", "implicit", "password", "client_credentials", "refresh_token", "urn:ietf:params:oauth:grant-type:uma-ticket", "urn:openid:params:grant-type:ciba", "urn:ietf:params:oauth:grant-type:device_code" ],
                                    'legacyIdTokenClaims': True,
                                    'authenticationFiltersEnabled': True,
                                    'clientAuthenticationFiltersEnabled': True,
                                    'keyRegenerationEnabled': True,
                                    'openidScopeBackwardCompatibility': False,
                                    'forceOfflineAccessScopeToEnableRefreshToken' : False,
                                    'dynamicRegistrationPasswordGrantTypeEnabled' : True,
                                    'cibaEnabled': True,
                                    'backchannelTokenDeliveryModesSupported': ["poll", "ping", "push"],
                                    'backchannelAuthenticationRequestSigningAlgValuesSupported': [ "RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS384", "PS512" ],
                                    'backchannelClientId': '123-123-123',
                                    'backchannelUserCodeParameterSupported': True,
                                    'backchannelRequestsProcessorJobIntervalSec': 5,
                                    'tokenEndpointAuthSigningAlgValuesSupported': [ 'HS256', 'HS384', 'HS512', 'RS256', 'RS384', 'RS512', 'ES256', 'ES384', 'ES512', 'PS256', 'PS384', 'PS512' ],
                                    'userInfoSigningAlgValuesSupported': [ 'none', 'HS256', 'HS384', 'HS512', 'RS256', 'RS384', 'RS512', 'ES256', 'ES384', 'ES512', 'PS256', 'PS384', 'PS512' ],
                                    'consentGatheringScriptBackwardCompatibility': False,
                                    'claimsParameterSupported': True,
                                    'grantTypesSupported': [ 'urn:openid:params:grant-type:ciba', 'authorization_code', 'urn:ietf:params:oauth:grant-type:uma-ticket', 'urn:ietf:params:oauth:grant-type:device_code', 'client_credentials', 'implicit', 'refresh_token', 'password' ],
                                    'idTokenSigningAlgValuesSupported': [ 'none', 'HS256', 'HS384', 'HS512', 'RS256', 'RS384', 'RS512', 'ES256', 'ES384', 'ES512', 'PS256', 'PS384', 'PS512' ],
                                    'requestObjectSigningAlgValuesSupported': [ 'none', 'HS256', 'HS384', 'HS512', 'RS256', 'RS384', 'RS512', 'ES256', 'ES384', 'ES512', 'PS256', 'PS384', 'PS512' ],
                                    'softwareStatementValidationClaimName': 'jwks_uri',
                                    'softwareStatementValidationType': 'jwks_uri',
                                    'umaGrantAccessIfNoPolicies': True,
                                    'rejectJwtWithNoneAlg': False,
                                    'removeRefreshTokensForClientOnLogout': True,
                                    'fapiCompatibility': False,
                                    'forceIdTokenHintPrecense': False,
                                    'introspectionScriptBackwardCompatibility': False,
                                    'spontaneousScopeLifetime': 0,
                                    'tokenEndpointAuthMethodsSupported': [ 'client_secret_basic', 'client_secret_post', 'client_secret_jwt', 'private_key_jwt', 'tls_client_auth', 'self_signed_tls_client_auth', 'none' ],
                                    'sessionIdRequestParameterEnabled': True,
                                    'skipRefreshTokenDuringRefreshing': False,
                                    'enabledComponents': ['unknown', 'health_check', 'userinfo', 'clientinfo', 'id_generation', 'registration', 'introspection', 'revoke_token', 'revoke_session', 'end_session', 'status_session', 'gluu_configuration', 'ciba', 'uma', 'u2f', 'device_authz', 'stat'],
                                    'opPolicyUri':'https://test.as.org/policy',
                                    'cleanServiceInterval':7200
                                    }

        custom_scripts = ('2DAF-F995', '2DAF-F996', '4BBE-C6A8', 'A51E-76DA')

        self.dbUtils.set_oxAuthConfDynamic(oxAuthConfDynamic_changes)
        
        
        # Enable custom scripts
        for inum in custom_scripts:
            self.dbUtils.enable_script(inum)

        if Config.installCasa:
            self.dbUtils.enable_script('DAA9-F7F8', enable=False)

        if self.dbUtils.moddb == static.BackendTypes.LDAP:
            # Update LDAP schema
            openDjSchemaFolder = os.path.join(Config.ldapBaseFolder, 'config/schema/')
            self.copyFile(os.path.join(Config.outputFolder, 'test/oxauth/schema/102-oxauth_test.ldif'), openDjSchemaFolder)
            self.copyFile(os.path.join(Config.outputFolder, 'test/scim-client/schema/103-scim_test.ldif'), openDjSchemaFolder)

            schema_fn = os.path.join(openDjSchemaFolder, '77-customAttributes.ldif')

            obcl_parser = myLdifParser(schema_fn)
            obcl_parser.parse()

            for i, o in enumerate(obcl_parser.entries[0][1]['objectClasses']):
                objcl = ObjectClass(o)
                if 'gluuCustomPerson' in objcl.tokens['NAME']:
                    may_list = list(objcl.tokens['MAY'])
                    for a in ('scimCustomFirst','scimCustomSecond', 'scimCustomThird'):
                        if a not in may_list:
                            may_list.append(a)

                    objcl.tokens['MAY'] = tuple(may_list)
                    obcl_parser.entries[0][1]['objectClasses'][i] = objcl.getstr()

            tmp_fn = '/tmp/77-customAttributes.ldif'
            with open(tmp_fn, 'wb') as w:
                ldif_writer = LDIFWriter(w)
                for dn, entry in obcl_parser.entries:
                    ldif_writer.unparse(dn, entry)

            self.copyFile(tmp_fn, openDjSchemaFolder)

            for test_schema in ('102-oxauth_test.ldif', '103-scim_test.ldif', '77-customAttributes.ldif'):
                self.run([paths.cmd_chown, '{0}:{0}'.format(Config.ldap_user), os.path.join(openDjSchemaFolder, test_schema)])

            self.logIt("Making opndj listen all interfaces")
            ldap_operation_result = self.dbUtils.ldap_conn.modify(
                    'cn=LDAPS Connection Handler,cn=Connection Handlers,cn=config', 
                     {'ds-cfg-listen-address': [ldap3.MODIFY_REPLACE, '0.0.0.0']}
                    )

            if not ldap_operation_result:
                    self.logIt("Ldap modify operation failed {}".format(str(self.ldap_conn.result)))
                    self.logIt("Ldap modify operation failed {}".format(str(self.ldap_conn.result)), True)

            self.dbUtils.ldap_conn.unbind()

            self.logIt("Re-starting opendj")
            self.restart('opendj')

            self.logIt("Re-binding opendj")
            # try 5 times to re-bind opendj
            for i in range(5):
                time.sleep(5)
                self.logIt("Try binding {} ...".format(i+1))
                bind_result = self.dbUtils.ldap_conn.bind()
                if bind_result:
                    self.logIt("Binding to opendj was successful")
                    break
                self.logIt("Re-try in 5 seconds")
            else:
                self.logIt("Re-binding opendj FAILED")
                sys.exit("Re-binding opendj FAILED")

            for atr in ('myCustomAttr1', 'myCustomAttr2'):

                dn = 'ds-cfg-attribute={},cn=Index,ds-cfg-backend-id={},cn=Backends,cn=config'.format(atr, 'userRoot')
                entry = {
                            'objectClass': ['top','ds-cfg-backend-index'],
                            'ds-cfg-attribute': [atr],
                            'ds-cfg-index-type': ['equality'],
                            'ds-cfg-index-entry-limit': ['4000']
                            }
                self.logIt("Creating Index {}".format(dn))
                ldap_operation_result = self.dbUtils.ldap_conn.add(dn, attributes=entry)
                if not ldap_operation_result:
                    self.logIt("Ldap modify operation failed {}".format(str(self.dbUtils.ldap_conn.result)))
                    self.logIt("Ldap modify operation failed {}".format(str(self.dbUtils.ldap_conn.result)), True)

        elif self.dbUtils.moddb in (static.BackendTypes.SPANNER, static.BackendTypes.MYSQL, static.BackendTypes.PGSQL):
            # Create additional indexes for rdbm
            pass

        else:
            self.dbUtils.cbm.exec_query('CREATE INDEX def_gluu_myCustomAttr1 ON `gluu`(myCustomAttr1) USING GSI WITH {"defer_build":true}')
            self.dbUtils.cbm.exec_query('CREATE INDEX def_gluu_myCustomAttr2 ON `gluu`(myCustomAttr2) USING GSI WITH {"defer_build":true}')
            self.dbUtils.cbm.exec_query('BUILD INDEX ON `gluu` (def_gluu_myCustomAttr1, def_gluu_myCustomAttr2)')

        if Config.persistence_type == 'ldap':
            try:
                self.dbUtils.ldap_conn.unbind()
            except:
                pass

            self.dbUtils.ldap_conn.bind()

        result = self.dbUtils.search('ou=configuration,o=gluu', search_filter='(oxIDPAuthentication=*)', search_scope=ldap3.BASE)
        if result:
            if isinstance(result['oxIDPAuthentication'], dict):
                ox_idp_authentication = result['oxIDPAuthentication']
                
            else:
                ox_idp_authentication_str = result['oxIDPAuthentication'][0] if isinstance(result['oxIDPAuthentication'], list) else result['oxIDPAuthentication']
                ox_idp_authentication = json.loads(ox_idp_authentication_str) if isinstance(ox_idp_authentication_str, str) else ox_idp_authentication_str

            ox_idp_authentication['config']['servers'] = ['{0}:{1}'.format(Config.hostname, Config.ldaps_port)]
            ox_idp_authentication_str = json.dumps(ox_idp_authentication, indent=2)
            self.dbUtils.set_configuration('oxIDPAuthentication', ox_idp_authentication_str)

        self.create_test_client_keystore()

        # Disable token binding module
        if base.os_name in ('ubuntu18', 'ubuntu20'):
            self.run(['a2dismod', 'mod_token_binding'])
            self.restart('apache2')

        self.restart('oxauth')


        if Config.installScimServer:
            self.restart('scim')

        if Config.installFido2:
            self.restart('fido2')


        # Prepare for tests run
        #install_command, update_command, query_command, check_text = self.get_install_commands()
        #self.run_command(install_command.format('git'))
        #self.run([self.cmd_mkdir, '-p', 'oxAuth/Client/profiles/ce_test'])
        #self.run([self.cmd_mkdir, '-p', 'oxAuth/Server/profiles/ce_test'])
        # Download and unzip file test_data.zip from CE server.
        # Copy files from unziped folder test/oxauth/client/* into oxAuth/Client/profiles/ce_test
        # Copy files from unziped folder test/oxauth/server/* into oxAuth/Server/profiles/ce_test
        #self.run([self.cmd_keytool, '-import', '-alias', 'seed22.gluu.org_httpd', '-keystore', 'cacerts', '-file', '%s/httpd.crt' % self.certFolder, '-storepass', 'changeit', '-noprompt'])
        #self.run([self.cmd_keytool, '-import', '-alias', 'seed22.gluu.org_opendj', '-keystore', 'cacerts', '-file', '%s/opendj.crt' % self.certFolder, '-storepass', 'changeit', '-noprompt'])
 
