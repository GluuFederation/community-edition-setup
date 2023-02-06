import os
import glob
import re
import shutil
import zipfile
import xml.etree.ElementTree as ET

from setup_app import paths
from setup_app.utils import base
from setup_app.static import AppType, InstallOption, InstallTypes, SetupProfiles, fapolicyd_rule_tmp
from setup_app.config import Config
from setup_app.utils.setup_utils import SetupUtils
from setup_app.installers.base import BaseInstaller

class JettyInstaller(BaseInstaller, SetupUtils):

    # let's borrow these variables from Config
    jetty_home = Config.jetty_home
    jetty_base = Config.jetty_base
    jetty_app_configuration = base.readJsonFile(os.path.join(paths.DATA_DIR, 'jetty_app_configuration.json'), ordered=True)

    def __init__(self):
        setattr(base.current_app, self.__class__.__name__, self)
        self.service_name = 'jetty'
        self.needdb = False # we don't need backend connection in this class
        self.install_var = 'installJetty'
        self.app_type = AppType.APPLICATION
        self.install_type = InstallOption.MANDATORY
        self.register_progess()
        self.jetty_user_home = '/home/jetty'
        self.jetty_user_home_lib = os.path.join(self.jetty_user_home, 'lib')

        self.app_custom_changes = {
            'jetty' : {
                'name' : 'jetty',
                'files' : [
                    {
                        'path' : os.path.join(self.jetty_home, 'etc/webdefault.xml'),
                        'replace' : [
                            {
                                'pattern' : r'(\<param-name\>dirAllowed<\/param-name\>)(\s*)(\<param-value\>)true(\<\/param-value\>)',
                                'update' : r'\1\2\3false\4'
                            }
                        ]
                    },
                    {
                        'path' : os.path.join(self.jetty_home, 'etc/jetty.xml'),
                        'replace' : [
                            {
                                'pattern' : '<New id="DefaultHandler" class="org.eclipse.jetty.server.handler.DefaultHandler"/>',
                                'update' : '<New id="DefaultHandler" class="org.eclipse.jetty.server.handler.DefaultHandler">\n\t\t\t\t <Set name="showContexts">false</Set>\n\t\t\t </New>'
                            }
                        ]
                    }
                ]
            }
        }


    def install(self):

        self.createUser(Config.jetty_user, self.jetty_user_home)
        self.addUserToGroup(Config.gluu_user, Config.jetty_user)
        self.run([paths.cmd_mkdir, '-p', self.jetty_user_home_lib])

        jetty_archive, jetty_dist = self.get_jetty_info()

        jettyTemp = os.path.join(jetty_dist, 'temp')
        self.run([paths.cmd_mkdir, '-p', jettyTemp])
        self.run([paths.cmd_chown, '-R', Config.user_group, jettyTemp])
        self.run([paths.cmd_chown, '-R', Config.user_group, jetty_dist])
        self.run([paths.cmd_chmod, '775', jettyTemp])


        try:
            self.logIt("Extracting %s into /opt/jetty" % jetty_archive)
            self.run(['tar', '-xzf', jetty_archive, '-C', jetty_dist, '--no-xattrs', '--no-same-owner', '--no-same-permissions'])
        except:
            self.logIt("Error encountered while extracting archive %s" % jetty_archive)

        jettyDestinationPath = max(glob.glob(os.path.join(jetty_dist, '{}-*'.format(self.jetty_dist_string))))

        self.run([paths.cmd_ln, '-sf', jettyDestinationPath, self.jetty_home])
        self.run([paths.cmd_chmod, '-R', "755", "%s/bin/" % jettyDestinationPath])

        self.applyChangesInFiles(self.app_custom_changes['jetty'])

        self.run([paths.cmd_chown, '-R', Config.user_group, jetty_dist])
        self.run([paths.cmd_chown, '-R', Config.user_group, jettyDestinationPath])
        self.run([paths.cmd_chown, '-h', Config.user_group, self.jetty_home])

        self.run([paths.cmd_chmod, '-R', "u+rwX,g+rwX,o-rwX", jetty_dist])
        self.run([paths.cmd_chmod, '-R', "u+rwX,g+rwX,o-rwX", jettyDestinationPath])

        self.logIt("jetty_dist = %s" % jetty_dist)
        self.logIt("jettyDestinationPath = %s" % jettyDestinationPath)

        self.run([paths.cmd_mkdir, '-p', self.jetty_base])
        self.run([paths.cmd_chown, '-R', Config.user_group, self.jetty_base])

        jettyRunFolder = '/var/run/jetty'
        self.run([paths.cmd_mkdir, '-p', jettyRunFolder])
        self.run([paths.cmd_chmod, '-R', '775', jettyRunFolder])
        self.run([paths.cmd_chgrp, '-R', Config.gluu_group, jettyRunFolder])

        self.run(['rm', '-rf', '/opt/jetty/bin/jetty.sh'])
        self.copyFile("%s/system/initd/jetty.sh" % Config.staticFolder, "%s/bin/jetty.sh" % self.jetty_home)
        self.run([paths.cmd_chown, '-R', Config.user_group, "%s/bin/jetty.sh" % self.jetty_home])
        self.run([paths.cmd_chmod, '-R', '755', "%s/bin/jetty.sh" % self.jetty_home])

    def get_jetty_info(self):
        self.jetty_dist_string = 'jetty-home'
        # first try latest versions
        jetty_archive_list = glob.glob(os.path.join(Config.distAppFolder, 'jetty-home-*.tar.gz'))
        if not jetty_archive_list:
            jetty_archive_list = glob.glob(os.path.join(Config.distAppFolder, 'jetty-distribution-*.tar.gz'))
            self.jetty_dist_string = 'jetty-distribution'
        if not jetty_archive_list:
            self.logIt("Jetty archive not found in {}. Exiting...".format(Config.distAppFolder), True, True)

        jetty_archive = max(jetty_archive_list)

        jetty_archive_fn = os.path.basename(jetty_archive)
        jetty_regex = re.search('{}-(\d*\.\d*)'.format(self.jetty_dist_string), jetty_archive_fn)
        if not jetty_regex:
            self.logIt("Can't determine Jetty version", True, True)

        jetty_dist = '/opt/jetty-' + jetty_regex.groups()[0]
        Config.templateRenderingDict['jetty_dist'] = jetty_dist
        self.jetty_version_string = jetty_regex.groups()[0]

        return jetty_archive, jetty_dist

    @property
    def web_app_xml_fn(self):
        return os.path.join(self.jetty_base, self.service_name, 'webapps', self.service_name+'.xml')

    def installJettyService(self, serviceConfiguration, supportCustomizations=False, supportOnlyPageCustomizations=False):
        serviceName = serviceConfiguration['name']
        self.logIt("Installing jetty service %s..." % serviceName)

        self.get_jetty_info()
        jettyServiceBase = os.path.join(self.jetty_base, serviceName)
        jettyModules = serviceConfiguration['jetty']['modules']
        jettyModulesList = [m.strip() for m in jettyModules.split(',')]
        if self.jetty_dist_string == 'jetty-home':
            if 'cdi-decorate' not in jettyModulesList:
                jettyModulesList.append('cdi-decorate')
            jettyModules = ','.join(jettyModulesList)

 
        # we need this, because this method may be called externally
        jetty_archive, jetty_dist = self.get_jetty_info()


        if Config.profile == SetupProfiles.DISA_STIG:
            Config.templateRenderingDict['service_user'] = 'identity' if serviceName == 'idp' else serviceName
        else:
            Config.templateRenderingDict['service_user'] = Config.jetty_user

        self.create_service_user(Config.templateRenderingDict['service_user'])

        # Create ./ext/lib folder for custom libraries only if installed Jetty "ext" module
        if "ext" in jettyModulesList:
            self.run([paths.cmd_mkdir, '-p', "%s/lib/ext" % jettyServiceBase])

        # Create ./custom/pages and ./custom/static folders for custom pages and static resources, only if application supports them
        if supportCustomizations:
            if not os.path.exists("%s/custom" % jettyServiceBase):
                self.run([paths.cmd_mkdir, '-p', "%s/custom" % jettyServiceBase])
            self.run([paths.cmd_mkdir, '-p', "%s/custom/pages" % jettyServiceBase])

            if not supportOnlyPageCustomizations:
                self.run([paths.cmd_mkdir, '-p', "%s/custom/i18n" % jettyServiceBase])
                self.run([paths.cmd_mkdir, '-p', "%s/custom/static" % jettyServiceBase])
                self.run([paths.cmd_mkdir, '-p', "%s/custom/libs" % jettyServiceBase])

        self.logIt("Preparing %s service base configuration" % serviceName)
        jettyEnv = os.environ.copy()
        jettyEnv['PATH'] = '%s/bin:' % Config.jre_home + jettyEnv['PATH']

        self.run([Config.cmd_java, '-jar', '%s/start.jar' % self.jetty_home, 'jetty.home=%s' % self.jetty_home, 'jetty.base=%s' % jettyServiceBase, '--add-to-start=%s' % jettyModules], None, jettyEnv)

        # make variables of this class accesible from Config
        self.update_rendering_dict()

        try:
            self.renderTemplateInOut(serviceName, '%s/jetty' % Config.templateFolder, '%s/jetty' % Config.outputFolder)
        except:
            self.logIt("Error rendering service '%s' defaults" % serviceName, True)

        jettyServiceConfiguration = '%s/jetty/%s' % (Config.outputFolder, serviceName)
        self.copyFile(jettyServiceConfiguration, Config.osDefault)
        self.run([paths.cmd_chown, '{}:{}'.format(Config.templateRenderingDict['service_user'], Config.gluu_group), os.path.join(Config.osDefault, serviceName)])

        # Render web reources file
        try:
            web_resources = '%s_web_resources.xml' % serviceName
            if os.path.exists('%s/jetty/%s' % (Config.templateFolder, web_resources)):
                self.renderTemplateInOut(web_resources, '%s/jetty' % Config.templateFolder, '%s/jetty' % Config.outputFolder)
                self.copyFile('%s/jetty/%s' % (Config.outputFolder, web_resources), "%s/%s/webapps" % (self.jetty_base, serviceName))
        except:
            self.logIt("Error rendering service '%s' web_resources.xml" % serviceName, True)

        # Render web context file
        try:
            web_context = '{}.xml'.format(serviceName)
            jetty_temp_dir = os.path.join(Config.templateFolder, 'jetty')
            if not os.path.exists(os.path.join(jetty_temp_dir, web_context)):
                web_context = 'default_webcontext.xml'
            self.renderTemplateInOut(
                    web_context,
                    jetty_temp_dir,
                    out_file=os.path.join(self.jetty_base, serviceName, 'webapps/{}.xml'.format(serviceName))
                )
        except:
            self.logIt("Error rendering service '%s' context xml" % serviceName, True)

        initscript_fn = os.path.join(self.jetty_home, 'bin/jetty.sh')
        self.fix_init_scripts(serviceName, initscript_fn)

        tmpfiles_base = '/usr/lib/tmpfiles.d'
        if Config.os_initdaemon == 'systemd' and os.path.exists(tmpfiles_base):
            self.logIt("Creating 'jetty.conf' tmpfiles daemon file")
            jetty_tmpfiles_src = '%s/jetty.conf.tmpfiles.d' % Config.templateFolder
            jetty_tmpfiles_dst = '%s/jetty.conf' % tmpfiles_base
            self.copyFile(jetty_tmpfiles_src, jetty_tmpfiles_dst)
            self.run([paths.cmd_chown, '{0}:{0}'.format(Config.root_user), jetty_tmpfiles_dst])
            self.run([paths.cmd_chmod, '644', jetty_tmpfiles_dst])

        serviceConfiguration['installed'] = True

        # don't send header to server
        inifile = 'http.ini' if self.jetty_dist_string == 'jetty-home' else 'start.ini'
        self.set_jetty_param(serviceName, 'jetty.httpConfig.sendServerVersion', 'false', inifile=inifile)

        self.run([paths.cmd_chown, '{}:{}'.format(Config.templateRenderingDict['service_user'], Config.gluu_group), os.path.join(Config.osDefault, serviceName)])

        self.render_unit_file(serviceName)

        jetty_service_webapps = os.path.join(jettyServiceBase, 'webapps')
        target_war_fn = os.path.join(jetty_service_webapps, os.path.basename(self.source_files[0][0]))
        self.copyFile(self.source_files[0][0], jetty_service_webapps)

        self.run([paths.cmd_chown, '-R', '{}:{}'.format(Config.templateRenderingDict['service_user'], Config.gluu_group), jettyServiceBase])

        if Config.profile == SetupProfiles.DISA_STIG:
            additional_rules = []
            if serviceName == base.current_app.OxtrustInstaller.service_name:
                additional_rules.append(fapolicyd_rule_tmp.format(Config.templateRenderingDict['service_user'], base.current_app.SamlInstaller.idp3Folder))
                additional_rules.append('allow perm=any uid={} : path=/usr/bin/facter'.format(Config.templateRenderingDict['service_user']))
            self.fapolicyd_access(Config.templateRenderingDict['service_user'], jettyServiceBase, additional_rules)

        else:
            self.configure_extra_libs(target_war_fn)


    def set_jetty_param(self, jettyServiceName, jetty_param, jetty_val, inifile='start.ini'):

        self.logIt("Setting jetty parameter {0}={1} for service {2}".format(jetty_param, jetty_val, jettyServiceName))

        path_list = [self.jetty_base, jettyServiceName, inifile]
        if inifile != 'start.ini':
            path_list.insert(-1, 'start.d')
        service_fn = os.path.join(*tuple(path_list))

        if os.path.exists(service_fn):
            start_ini = self.readFile(service_fn)
            start_ini_list = start_ini.splitlines()
            param_ln = jetty_param + '=' + jetty_val

            for i, l in enumerate(start_ini_list[:]):
                if jetty_param in l and l[0]=='#':
                    start_ini_list[i] = param_ln 
                    break
                elif l.strip().startswith(jetty_param):
                    start_ini_list[i] = param_ln
                    break
            else:
                start_ini_list.append(param_ln)

            self.writeFile(service_fn, '\n'.join(start_ini_list), backup=False)

    def calculate_aplications_memory(self, application_max_ram, installedComponents):
        self.logIt("Calculating memory setting for applications")

        application_max_ram = float(application_max_ram)

        #prepare default mem needed for proper rendering
        for app in Config.app_mem_weigths:
            Config.templateRenderingDict['{}_max_mem'.format(app)] = Config.app_mem_weigths[app]['min']
            Config.templateRenderingDict['{}_min_mem'.format(app)] = Config.app_mem_weigths[app]['min']


        def calulate_total_weigth(withopendj=True):
            total_weigth = 0

            if Config.ldap_install == InstallTypes.LOCAL and withopendj:
                total_weigth += Config.app_mem_weigths['opendj']['weigth']

            for app in installedComponents:
                total_weigth += Config.app_mem_weigths[app]['weigth']

            return total_weigth

        total_weigth = calulate_total_weigth()

        if Config.ldap_install == InstallTypes.LOCAL:
            opendj_max_ram = round(Config.app_mem_weigths['opendj']['weigth'] * application_max_ram /total_weigth)

            if opendj_max_ram < Config.opendj_ram:
                total_weigth = calulate_total_weigth(withopendj=False)
                opendj_max_ram = Config.opendj_ram
                application_max_ram -= Config.opendj_ram

            os.environ['ce_ldap_xms'] = str(Config.app_mem_weigths['opendj']['min'])
            os.environ['ce_ldap_xmx'] = str(opendj_max_ram)

        for app in installedComponents:
            app_max_mem = round(Config.app_mem_weigths[app]['weigth'] * application_max_ram /total_weigth)
            Config.templateRenderingDict['{}_max_mem'.format(app)] = app_max_mem
            Config.templateRenderingDict['{}_min_mem'.format(app)] = Config.app_mem_weigths[app]['min']

        return True

    def calculate_selected_aplications_memory(self):
        Config.pbar.progress("gluu", "Calculating application memory")

        installedComponents = []

        # Jetty apps
        if Config.installOxAuth:
            installedComponents.append('oxauth')
        if Config.installOxTrust:
            installedComponents.append('identity')
        if Config.installSaml:
            installedComponents.append('idp')
        if Config.installCasa:
            installedComponents.append('casa')
        if Config.installScimServer:
            installedComponents.append('scim')
        if Config.installFido2:
            installedComponents.append('fido2')
        if Config.installOxd:
            installedComponents.append('oxd')

        # Node apps
        if Config.installPassport:
            installedComponents.append('passport')

        return self.calculate_aplications_memory(Config.application_max_ram, installedComponents)


    def add_extra_class(self, class_path, xml_fn=None):
        if not xml_fn:
            xml_fn = self.web_app_xml_fn
        tree = ET.parse(xml_fn)
        root = tree.getroot()
        path_list = []

        for app_set in root.findall("Set"):
            if app_set.get('name') == 'extraClasspath':
                if app_set.text:
                    for cp in app_set.text.split(','):
                        cps = cp.strip()
                        if cps:
                            path_list.append(cps)
                break
        else:
            app_set = ET.Element("Set")
            app_set.set('name', 'extraClasspath')

            root.append(app_set)

        for cp in class_path.split(','):
            if os.path.basename(cp) not in ','.join(path_list):
                path_list.append(cp.strip())

        app_set.text = ','.join(path_list)
        
        with open(xml_fn, 'wb') as f:
            f.write(b'<?xml version="1.0"  encoding="ISO-8859-1"?>\n')
            f.write(b'<!DOCTYPE Configure PUBLIC "-//Jetty//Configure//EN" "http://www.eclipse.org/jetty/configure_9_0.dtd">\n')
            f.write(ET.tostring(root, method='xml'))


    def configure_extra_libs(self, target_war_fn):
        version_rec = re.compile('-(\d+)?\.')

        builtin_libs = []
        war_zip = zipfile.ZipFile(target_war_fn)
        for builtin_path in war_zip.namelist():
            if  builtin_path.endswith('.jar'):
                builtin_libs.append(os.path.basename(builtin_path))
        war_zip.close()

        def in_war(name):
            for fn in builtin_libs:
                if fn.startswith(name):
                     return fn

        common_lib_dir = None

        if Config.cb_install:
            common_lib_dir = base.current_app.CouchbaseInstaller.common_lib_dir

        elif Config.rdbm_install and Config.rdbm_type == 'spanner':
            common_lib_dir = base.current_app.RDBMInstaller.common_lib_dir

        if common_lib_dir:

            add_custom_lib_dir = []
            for extra_lib_fn in os.listdir(common_lib_dir):
                version_search = version_rec.search(extra_lib_fn)
                if version_search:
                    version_start_index = version_search.start()
                    name = extra_lib_fn[:version_start_index]
                    if not in_war(name):
                        add_custom_lib_dir.append(os.path.join(common_lib_dir, extra_lib_fn))

            self.add_extra_class(','.join(add_custom_lib_dir))
