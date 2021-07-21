import os
import glob
import re


from setup_app import paths
from setup_app.utils import base
from setup_app.static import AppType, InstallOption, InstallTypes
from setup_app.config import Config
from setup_app.utils.setup_utils import SetupUtils
from setup_app.installers.base import BaseInstaller

class JettyInstaller(BaseInstaller, SetupUtils):

    # let's borrow these variables from Config
    jetty_home = Config.jetty_home
    jetty_base = Config.jetty_base
    jetty_app_configuration = base.readJsonFile(os.path.join(paths.DATA_DIR, 'jetty_app_configuration.json'), ordered=True)

    def __init__(self):
        self.service_name = 'jetty'
        self.needdb = False # we don't need backend connection in this class
        self.install_var = 'installJetty'
        self.app_type = AppType.APPLICATION
        self.install_type = InstallOption.MONDATORY
        if not base.snap:
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

        self.createUser('jetty', self.jetty_user_home)
        self.addUserToGroup('gluu', 'jetty')
        self.run([paths.cmd_mkdir, '-p', self.jetty_user_home_lib])

        jettyArchive, jetty_dist = self.get_jetty_info()

        jettyTemp = os.path.join(jetty_dist, 'temp')
        self.run([paths.cmd_mkdir, '-p', jettyTemp])
        self.run([paths.cmd_chown, '-R', 'jetty:jetty', jettyTemp])

        try:
            self.logIt("Extracting %s into /opt/jetty" % jettyArchive)
            self.run(['tar', '-xzf', jettyArchive, '-C', jetty_dist, '--no-xattrs', '--no-same-owner', '--no-same-permissions'])
        except:
            self.logIt("Error encountered while extracting archive %s" % jettyArchive)

        jettyDestinationPath = max(glob.glob(os.path.join(jetty_dist, 'jetty-distribution-*')))

        self.run([paths.cmd_ln, '-sf', jettyDestinationPath, self.jetty_home])
        self.run([paths.cmd_chmod, '-R', "755", "%s/bin/" % jettyDestinationPath])

        self.applyChangesInFiles(self.app_custom_changes['jetty'])

        self.run([paths.cmd_chown, '-R', 'jetty:jetty', jettyDestinationPath])
        self.run([paths.cmd_chown, '-h', 'jetty:jetty', self.jetty_home])

        self.run([paths.cmd_mkdir, '-p', self.jetty_base])
        self.run([paths.cmd_chown, '-R', 'jetty:jetty', self.jetty_base])

        jettyRunFolder = '/var/run/jetty'
        self.run([paths.cmd_mkdir, '-p', jettyRunFolder])
        self.run([paths.cmd_chmod, '-R', '775', jettyRunFolder])
        self.run([paths.cmd_chgrp, '-R', 'jetty', jettyRunFolder])

        self.run(['rm', '-rf', '/opt/jetty/bin/jetty.sh'])
        self.copyFile("%s/system/initd/jetty.sh" % Config.staticFolder, "%s/bin/jetty.sh" % self.jetty_home)
        self.run([paths.cmd_chown, '-R', 'jetty:jetty', "%s/bin/jetty.sh" % self.jetty_home])
        self.run([paths.cmd_chmod, '-R', '755', "%s/bin/jetty.sh" % self.jetty_home])

    def get_jetty_info(self):
        jetty_archive_list = glob.glob(os.path.join(Config.distAppFolder, 'jetty-distribution-*.tar.gz'))

        if not jetty_archive_list:
            self.logIt("Jetty archive not found in {}. Exiting...".format(Config.distAppFolder), True, True)

        jettyArchive = max(jetty_archive_list)

        jettyArchive_fn = os.path.basename(jettyArchive)
        jetty_regex = re.search('jetty-distribution-(\d*\.\d*)', jettyArchive_fn)

        if not jetty_regex:
            self.logIt("Can't determine Jetty version", True, True)

        jetty_dist = '/opt/jetty-' + jetty_regex.groups()[0]
        Config.templateRenderingDict['jetty_dist'] = jetty_dist

        return jettyArchive, jetty_dist


    def installJettyService(self, serviceConfiguration, supportCustomizations=False, supportOnlyPageCustomizations=False):
        serviceName = serviceConfiguration['name']

        self.logIt("Installing jetty service %s..." % serviceName)

        jettyServiceBase = os.path.join(self.jetty_base, serviceName)
        jettyModules = serviceConfiguration['jetty']['modules']
        jettyModulesList = jettyModules.split(',')
        
        if base.snap:
            Config.templateRenderingDict['jetty_dist'] = self.jetty_base
        else:
            # we need this, because this method may be called externally
            jettyArchive, jetty_dist = self.get_jetty_info()

        self.logIt("Preparing %s service base folders" % serviceName)
        self.run([paths.cmd_mkdir, '-p', jettyServiceBase])

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
        self.run([paths.cmd_chown, 'root:root', os.path.join(Config.osDefault, serviceName)])

        # Render web eources file
        try:
            web_resources = '%s_web_resources.xml' % serviceName
            if os.path.exists('%s/jetty/%s' % (Config.templateFolder, web_resources)):
                self.renderTemplateInOut(web_resources, '%s/jetty' % Config.templateFolder, '%s/jetty' % Config.outputFolder)
                self.copyFile('%s/jetty/%s' % (Config.outputFolder, web_resources), "%s/%s/webapps" % (self.jetty_base, serviceName))
        except:
            self.logIt("Error rendering service '%s' web_resources.xml" % serviceName, True)

        # Render web context file
        try:
            web_context = '%s.xml' % serviceName
            if os.path.exists('%s/jetty/%s' % (Config.templateFolder, web_context)):
                self.renderTemplateInOut(web_context, '%s/jetty' % Config.templateFolder, '%s/jetty' % Config.outputFolder)
                self.copyFile('%s/jetty/%s' % (Config.outputFolder, web_context), "%s/%s/webapps" % (self.jetty_base, serviceName))
        except:
            self.logIt("Error rendering service '%s' context xml" % serviceName, True)

        initscript_fn = os.path.join(self.jetty_home, 'bin/jetty.sh')
        self.fix_init_scripts(serviceName, initscript_fn)

        if not base.snap:
            tmpfiles_base = '/usr/lib/tmpfiles.d'
            if Config.os_initdaemon == 'systemd' and os.path.exists(tmpfiles_base):
                self.logIt("Creating 'jetty.conf' tmpfiles daemon file")
                jetty_tmpfiles_src = '%s/jetty.conf.tmpfiles.d' % Config.templateFolder
                jetty_tmpfiles_dst = '%s/jetty.conf' % tmpfiles_base
                self.copyFile(jetty_tmpfiles_src, jetty_tmpfiles_dst)
                self.run([paths.cmd_chown, 'root:root', jetty_tmpfiles_dst])
                self.run([paths.cmd_chmod, '644', jetty_tmpfiles_dst])

        serviceConfiguration['installed'] = True

        # don't send header to server
        self.set_jetty_param(serviceName, 'jetty.httpConfig.sendServerVersion', 'false')

        if base.snap:
            run_dir = os.path.join(jettyServiceBase, 'run')
            if not os.path.exists(run_dir):
                self.run([paths.cmd_mkdir, '-p', run_dir])

        self.run([paths.cmd_chown, '-R', 'jetty:jetty', jettyServiceBase])

    def set_jetty_param(self, jettyServiceName, jetty_param, jetty_val):

        self.logIt("Seeting jetty parameter {0}={1} for service {2}".format(jetty_param, jetty_val, jettyServiceName))

        service_fn = os.path.join(self.jetty_base, jettyServiceName, 'start.ini')
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

        self.writeFile(service_fn, '\n'.join(start_ini_list))

    def calculate_aplications_memory(self, application_max_ram, installedComponents):
        self.logIt("Calculating memory setting for applications")

        application_max_ram = float(application_max_ram)

        #prepare default mem needed for proper rendering
        for app in Config.app_mem_weigths:
            Config.templateRenderingDict['{}_max_mem'.format(app)] = Config.app_mem_weigths[app]['min']
            Config.templateRenderingDict['{}_min_mem'.format(app)] = Config.app_mem_weigths[app]['min']


        def calulate_total_weigth(withopendj=True):
            total_weigth = 0

            if Config.wrends_install == InstallTypes.LOCAL and withopendj:
                total_weigth += Config.app_mem_weigths['opendj']['weigth']

            for app in installedComponents:
                total_weigth += Config.app_mem_weigths[app]['weigth']

            return total_weigth

        total_weigth = calulate_total_weigth()
        
        if Config.wrends_install == InstallTypes.LOCAL:
            opendj_max_ram = round(Config.app_mem_weigths['opendj']['weigth'] * application_max_ram /total_weigth)
            
            if opendj_max_ram < Config.opendj_ram:
                total_weigth = calulate_total_weigth(withopendj=False)
                opendj_max_ram = Config.opendj_ram
                application_max_ram -= Config.opendj_ram

            os.environ['ce_wrends_xms'] = str(Config.app_mem_weigths['opendj']['min'])
            os.environ['ce_wrends_xmx'] = str(opendj_max_ram)

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
        if Config.installOxAuthRP:
            installedComponents.append('oxauth-rp')
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
