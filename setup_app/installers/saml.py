import os
import glob
import shutil

from setup_app import paths
from setup_app.static import PersistenceType
from setup_app.static import AppType, InstallOption, SetupProfiles
from setup_app.config import Config
from setup_app.utils import base
from setup_app.installers.jetty import JettyInstaller

class SamlInstaller(JettyInstaller):

    def __init__(self):
        setattr(base.current_app, self.__class__.__name__, self)
        self.service_name = 'idp'
        self.app_type = AppType.SERVICE
        self.install_type = InstallOption.OPTONAL
        self.install_var = 'installSaml'
        self.register_progess()

        self.needdb = True

        self.source_files = [
                (os.path.join(Config.distGluuFolder,'idp.war'), Config.maven_root + '/maven/org/gluu/oxshibbolethIdp/{0}/oxshibbolethIdp-{0}.war'.format(Config.oxVersion)),
                (os.path.join(Config.distGluuFolder,'idp3_cml_keygenerator.jar'), Config.maven_root + '/maven/org/gluu/oxShibbolethKeyGenerator/{0}/oxShibbolethKeyGenerator-{0}.jar'.format(Config.oxVersion)),
                (os.path.join(Config.distGluuFolder,'shibboleth-idp.jar'), Config.maven_root + '/maven/org/gluu/oxShibbolethStatic/{0}/oxShibbolethStatic-{0}.jar'.format(Config.oxVersion)),
                ]

        self.templates_folder = os.path.join(Config.templateFolder, 'idp')
        self.output_folder = os.path.join(Config.outputFolder, 'idp')

        self.ldif_config = os.path.join(self.output_folder, 'configuration.ldif')
        self.ldif_clients = os.path.join(self.output_folder, 'clients.ldif')
        self.ldif_oxidp = os.path.join(self.output_folder, 'oxidp.ldif')
        self.oxidp_config_json = os.path.join(self.output_folder, 'oxidp-config.json')

        self.shib_data_store_fn = os.path.join(Config.certFolder, 'shibIDP.jks')

        self.shibboleth_version = 'v3'

        self.data_source_properties = os.path.join(self.output_folder, 'datasource.properties')
        self.staticIDP3FolderConf = os.path.join(Config.install_dir, 'static/idp3/conf')
        self.staticIDP3FolderMetadata = os.path.join(Config.install_dir, 'static/idp3/metadata')
        self.oxtrust_conf_fn = os.path.join(self.output_folder, 'oxtrust_conf.json')
        self.idp3_configuration_properties = 'idp.properties'
        self.idp3_configuration_ldap_properties = 'ldap.properties'
        self.idp3_configuration_saml_nameid = 'saml-nameid.properties'
        self.idp3_configuration_services = 'services.properties'
        self.idp3_configuration_password_authn = 'authn/password-authn-config.xml'
        self.idp3_metadata = 'idp-metadata.xml'

        self.idp3Folder = '/opt/shibboleth-idp'
        self.idp3MetadataFolder = os.path.join(self.idp3Folder, 'metadata')
        self.idp3MetadataCredentialsFolder = os.path.join(self.idp3MetadataFolder, 'credentials')
        self.idp3LogsFolder = os.path.join(self.idp3Folder, 'logs')
        self.idp3LibFolder = os.path.join(self.idp3Folder, 'lib')
        self.idp3ConfFolder = os.path.join(self.idp3Folder, 'conf')
        self.idp3ConfAuthnFolder = os.path.join(self.idp3Folder, 'conf/authn')
        self.idp3CredentialsFolder = os.path.join(self.idp3Folder, 'credentials')
        self.idp3WebappFolder = os.path.join(self.idp3Folder, 'webapp')

        self.shib_key_file = os.path.join(Config.certFolder, 'shibIDP.key')
        self.shib_crt_file = os.path.join(Config.certFolder, 'shibIDP.crt')
        self.idp_encryption_crt_file = os.path.join(Config.certFolder, 'idp-encryption.crt')
        self.idp_signing_crt_file = os.path.join(Config.certFolder, 'idp-signing.crt')

        Config.templateRenderingDict['sealer_data_store_fn'] = 'sealer.jks'
        Config.templateRenderingDict['shib_data_store_fn'] = self.shib_data_store_fn


    def install(self):
        self.logIt("Install SAML Shibboleth IDP v3...")

        self.unpack_idp3()

        if not base.argsp.dummy:
            if not Config.get('shibJksPass'):
                Config.shibJksPass = self.getPW()
                Config.encoded_shib_jks_pw = self.obscure(Config.shibJksPass)

            # generate crypto
            self.gen_cert('shibIDP', Config.shibJksPass, 'jetty')
            self.gen_cert('idp-encryption', Config.shibJksPass, 'jetty')
            self.gen_cert('idp-signing', Config.shibJksPass, 'jetty')

            self.gen_keystore('shibIDP',
                              self.shib_data_store_fn,
                              Config.shibJksPass,
                              self.shib_key_file,
                              self.shib_crt_file,
                              store_type='JKS'
                              )



            if Config.mappingLocations['user'] == 'couchbase':
                Config.templateRenderingDict['idp_attribute_resolver_ldap.search_filter'] = '(&(|(lower(uid)=$requestContext.principalName)(mail=$requestContext.principalName))(objectClass=gluuPerson))'

            # Process templates
            self.renderTemplateInOut(self.idp3_configuration_properties, self.staticIDP3FolderConf, self.idp3ConfFolder)
            self.renderTemplateInOut(self.idp3_configuration_ldap_properties, self.staticIDP3FolderConf, self.idp3ConfFolder)
            self.renderTemplateInOut(self.idp3_configuration_saml_nameid, self.staticIDP3FolderConf, self.idp3ConfFolder)
            self.renderTemplateInOut(self.idp3_configuration_services, self.staticIDP3FolderConf, self.idp3ConfFolder)
            self.renderTemplateInOut(
                        self.idp3_configuration_password_authn, 
                        os.path.join(self.staticIDP3FolderConf, 'authn'),
                        os.path.join(self.idp3ConfFolder, 'authn')
                        )

            # load certificates to update metadata
            Config.templateRenderingDict['idp3EncryptionCertificateText'] = self.load_certificate_text(self.idp_encryption_crt_file)
            Config.templateRenderingDict['idp3SigningCertificateText'] = self.load_certificate_text(self.idp_signing_crt_file)
            # update IDP3 metadata
            self.renderTemplateInOut(self.idp3_metadata, self.staticIDP3FolderMetadata, self.idp3MetadataFolder)

        self.installJettyService(self.jetty_app_configuration[self.service_name], True)
        jettyServiceWebapps = os.path.join(self.jetty_base, self.service_name,  'webapps')
        self.copyFile(self.source_files[0][0], jettyServiceWebapps)
        # Prepare libraries needed to for command line IDP3 utilities

        self.install_saml_libraries()


        if not base.argsp.dummy:
            # generate new keystore with AES symmetric key
            # there is one throuble with Shibboleth IDP 3.x - it doesn't load keystore from /etc/certs. It accepts %{idp.home}/credentials/sealer.jks  %{idp.home}/credentials/sealer.kver path format only.
            cmd = [Config.cmd_java,'-classpath', '"{}"'.format(os.path.join(self.idp3Folder,'webapp/WEB-INF/lib/*')),
                'net.shibboleth.utilities.java.support.security.BasicKeystoreKeyStrategyTool',
                '--storefile', os.path.join(self.idp3Folder,'credentials', Config.templateRenderingDict['sealer_data_store_fn']),
                '--versionfile',  os.path.join(self.idp3Folder, 'credentials/sealer.kver'),
                '--alias secret',
                '--storepass', Config.shibJksPass]

            self.run(' '.join(cmd), shell=True)


        couchbase_mappings = self.getMappingType('couchbase')
        if 'user' in couchbase_mappings:
            self.saml_couchbase_settings()

        self.saml_persist_configurations()
        user_group = 'identity:gluu' if Config.profile == SetupProfiles.DISA_STIG else 'jetty:gluu'
        self.run([paths.cmd_chown, '-R', user_group, self.idp3Folder])
        self.enable()

    def unpack_idp3(self):
        # unpack IDP3 JAR with static configs
        tmpShibpDir = os.path.join('/tmp', os.urandom(5).hex())
        self.logIt("Unpacking %s..." % self.source_files[2][0])
        self.createDirs(tmpShibpDir)
        self.run([Config.cmd_jar, 'xf', self.source_files[2][0]], tmpShibpDir)
        self.copyTree(os.path.join(tmpShibpDir, 'shibboleth-idp'), '/opt/shibboleth-idp')
        self.removeDirs(tmpShibpDir)

    def generate_configuration(self):
        self.check_clients([('idp_client_id', '1101.')])

        if not Config.get('idpClient_pw'):
            Config.idpClient_pw = self.getPW()
            Config.idpClient_encoded_pw = self.obscure(Config.idpClient_pw)

    def render_import_templates(self):

        self.renderTemplateInOut(self.oxidp_config_json, self.templates_folder, self.output_folder)
        Config.templateRenderingDict['oxidp_config_base64'] = self.generate_base64_ldap_file(self.oxidp_config_json)

        for tmp in (self.ldif_config, self.ldif_oxidp, self.oxtrust_conf_fn, self.ldif_clients):
            self.renderTemplateInOut(tmp, self.templates_folder, self.output_folder)

        self.dbUtils.import_ldif([self.ldif_config, self.ldif_oxidp, self.ldif_clients])

    def update_backend(self):
        self.dbUtils.enable_service('gluuSamlEnabled')
        oxtrust_conf = base.readJsonFile(self.oxtrust_conf_fn)
        self.dbUtils.set_oxTrustConfApplication(oxtrust_conf)


    def install_saml_libraries(self):
        # Unpack oxauth.war to get bcprov-jdk16.jar
        tmpIdpDir = os.path.join('/tmp', os.urandom(5).hex())

        self.logIt("Unpacking %s..." % self.source_files[0][0])
        self.createDirs(tmpIdpDir)

        self.run([Config.cmd_jar, 'xf', self.source_files[0][0]], tmpIdpDir)

        # Copy libraries into webapp
        idp3WebappLibFolder = os.path.join(self.idp3WebappFolder, 'WEB-INF/lib')
        self.createDirs(idp3WebappLibFolder)
        self.copyTree(os.path.join(tmpIdpDir, 'WEB-INF/lib'), idp3WebappLibFolder)

        self.removeDirs(tmpIdpDir)


    def saml_couchbase_settings(self):

        if not Config.get('couchbaseShibUserPassword'):
            Config.couchbaseShibUserPassword = self.getPW()

        shib_user = 'couchbaseShibUser'
        shib_user_roles = 'query_select[*]'
        if Config.get('isCouchbaseUserAdmin'):
            self.logIt("Creating couchbase readonly user for shib")
            self.dbUtils.cbm.create_user(shib_user, Config.couchbaseShibUserPassword, 'Shibboleth IDP', shib_user_roles)
        else:
            Config.post_messages.append('Please create a user on Couchbase Server with the following credidentals and roles')
            Config.post_messages.append('Username: {}'.format(shib_user))
            Config.post_messages.append('Password: {}'.format(Config.couchbaseShibUserPassword))
            Config.post_messages.append('Roles: {}'.format(shib_user_roles))


    def saml_persist_configurations(self):

        if Config.persistence_type in (PersistenceType.couchbase, PersistenceType.sql):

            # Add datasource.properties to idp.properties
            idp3_configuration_properties_fn = os.path.join(self.idp3ConfFolder, self.idp3_configuration_properties)

            with open(idp3_configuration_properties_fn) as f:
                idp3_properties = f.readlines()

            for i,l in enumerate(idp3_properties[:]):
                if l.strip().startswith('idp.additionalProperties'):
                    idp3_properties[i] = l.strip() + ', /conf/datasource.properties\n'

            new_idp3_props = ''.join(idp3_properties)
            self.writeFile(idp3_configuration_properties_fn, new_idp3_props, backup=False)

            if Config.persistence_type == 'sql':
                self.data_source_properties = self.data_source_properties + '.sql'
                bean_formatter = 'rdbm'
                if Config.rdbm_type == 'pgsql':
                    Config.non_setup_properties['rdbm_driver_class'] = 'org.postgresql.Driver'
                    Config.non_setup_properties['rdbm_name'] = 'postgresql'
                    Config.non_setup_properties['sql_search_filter'] = '''select * from "gluuPerson" where ((LOWER("uid") = '$requestContext.principalName') OR (LOWER("mail") = '$requestContext.principalName')) AND ("objectClass" = 'gluuPerson')'''
                else:
                     Config.non_setup_properties['rdbm_driver_class'] = 'com.{}.jdbc.Driver'.format(Config.rdbm_type)
                     Config.non_setup_properties['rdbm_name'] = Config.rdbm_type
                     Config.non_setup_properties['sql_search_filter'] = '''select * from `gluuPerson` where ((LOWER(uid) = "$requestContext.principalName") OR (LOWER(mail) = "$requestContext.principalName")) AND (objectClass = "gluuPerson")'''
            else:
                bean_formatter = 'couchbase'

            self.renderTemplateInOut(self.data_source_properties, self.templates_folder, self.output_folder)

            idp_data_source_fn = os.path.join(self.idp3ConfFolder, 'datasource.properties')
            self.copyFile(self.data_source_properties, idp_data_source_fn)
            self.run([paths.cmd_chmod, '0600', idp_data_source_fn])
            bean_xml = os.path.join(self.staticIDP3FolderConf, 'gluu-{}-bean.xml'.format(bean_formatter))
            self.copyFile(bean_xml, self.idp3ConfFolder)


    def create_folders(self):
        self.createDirs(os.path.join(Config.gluuBaseFolder, 'conf/shibboleth3'))
        self.createDirs(os.path.join(self.jetty_base, 'identity/conf/shibboleth3/idp'))
        self.createDirs(os.path.join(self.jetty_base, 'identity/conf/shibboleth3/sp'))

        for folder in (self.idp3Folder, self.idp3MetadataFolder, self.idp3MetadataCredentialsFolder,
                        self.idp3LogsFolder, self.idp3LibFolder, self.idp3ConfFolder, 
                        self.idp3ConfAuthnFolder, self.idp3CredentialsFolder, self.idp3WebappFolder):

            self.run([paths.cmd_mkdir, '-p', folder])
