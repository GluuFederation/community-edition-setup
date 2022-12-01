import os
import re
import glob
import ssl
import time

from xml.etree import ElementTree

from setup_app import paths
from setup_app.static import AppType, InstallOption, SetupProfiles
from setup_app.utils import base
from setup_app.config import Config
from setup_app.utils.properties_utils import propertiesUtils
from setup_app.installers.jetty import JettyInstaller


class CasaInstaller(JettyInstaller):

    def __init__(self):
        setattr(base.current_app, self.__class__.__name__, self)
        self.service_name = 'casa'
        self.app_type = AppType.SERVICE
        self.install_type = InstallOption.OPTONAL
        self.install_var = 'installCasa'
        self.register_progess()

        self.source_files = [
                (os.path.join(Config.distGluuFolder, 'casa.war'), Config.maven_root + '/maven/org/gluu/casa/{0}/casa-{0}.war'.format(Config.oxVersion))
                ]

        self.templates_folder = os.path.join(Config.templateFolder, 'casa')
        self.output_folder = os.path.join(Config.outputFolder, 'casa')
        self.ldif = os.path.join(Config.outputFolder, 'casa/casa.ldif')
        self.ldif_scripts = os.path.join(Config.outputFolder, 'casa/scripts.ldif')
        self.pylib_folder = os.path.join(Config.gluuOptPythonFolder, 'libs')
        self.casa_jetty_dir = os.path.join(self.jetty_base, 'casa')

    def install(self):

        if not os.path.exists(self.pylib_folder):
            self.run([paths.cmd_mkdir , '-p', self.pylib_folder])

        self.run([paths.cmd_chmod , 'g+w', self.pylib_folder])
        self.logIt("Copying casa.war into jetty webapps folder...")
        self.installJettyService(self.jetty_app_configuration['casa'])

        jettyServiceWebapps = os.path.join(self.casa_jetty_dir, 'webapps')
        self.copyFile(self.source_files[0][0], jettyServiceWebapps)

        jettyServiceOxAuthCustomLibsPath = os.path.join(self.jetty_base,
                                                        "oxauth", 
                                                        "custom/libs"
                                                        )

        twillo_package = base.determine_package(os.path.join(Config.distGluuFolder, 'twilio-*.jar'))
        self.copyFile(twillo_package, jettyServiceOxAuthCustomLibsPath)

        jsmpp_package = base.determine_package(os.path.join(Config.distGluuFolder, 'jsmpp-*.jar'))
        self.copyFile(jsmpp_package, jettyServiceOxAuthCustomLibsPath)

        if Config.profile == SetupProfiles.DISA_STIG:
            lib_user_group = '{}:{}'.format(base.current_app.OxauthInstaller.service_name.lower(), Config.gluu_group)
        else:
            lib_user_group = '{}:{}'.format(Config.jetty_user, Config.gluu_group)

        self.run([paths.cmd_chown, '-R', lib_user_group, jettyServiceOxAuthCustomLibsPath])

        if not base.argsp.dummy:

            #Adding twilio jar path to oxauth.xml
            oxauth_xml_fn = os.path.join(self.jetty_base,  'oxauth/webapps/oxauth.xml')
            
            extra_classpath_list = [
                        './custom/libs/{}'.format(os.path.basename(twillo_package)),
                        './custom/libs/{}'.format(os.path.basename(jsmpp_package)),
                        ]

            self.add_extra_class(','.join(extra_classpath_list), oxauth_xml_fn)

        self.enable('casa')

    def copy_static(self):

        for script_fn in glob.glob(os.path.join(Config.staticFolder, 'casa/scripts/*.*')):
            self.run(['cp', script_fn, self.pylib_folder])

    def render_import_templates(self, import_script=True):

        Config.templateRenderingDict['oxd_protocol'] = 'https'
        scripts_template = os.path.join(self.templates_folder, os.path.basename(self.ldif_scripts))
        extensions = base.find_script_names(scripts_template)
        self.prepare_base64_extension_scripts(extensions=extensions)

        ldif_files = (self.ldif, self.ldif_scripts)
        for tmp in ldif_files:
            self.renderTemplateInOut(tmp, self.templates_folder, self.output_folder)

        if import_script:
            self.dbUtils.import_ldif(ldif_files)


    def create_folders(self):
        for path_name in ('static', 'plugins'):
            path = os.path.join(self.casa_jetty_dir, path_name)
            if not os.path.exists(path):
                self.run([paths.cmd_mkdir, '-p', path])
            self.run([paths.cmd_chown, '-R', 'jetty:jetty', path])
