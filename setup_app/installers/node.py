import os
import glob

from setup_app import paths
from setup_app.utils import base
from setup_app.static import AppType, InstallOption
from setup_app.config import Config
from setup_app.utils.setup_utils import SetupUtils, SetupProfiles
from setup_app.installers.base import BaseInstaller

class NodeInstaller(BaseInstaller, SetupUtils):

    node_base = os.path.join(Config.gluuOptFolder, 'node')
    templates_rendered = False

    def __init__(self):
        setattr(base.current_app, self.__class__.__name__, self)
        self.service_name = 'node'
        self.needdb = False # we don't need backend connection in this class
        self.install_var = 'install_node_app'
        self.app_type = AppType.APPLICATION
        self.install_type = InstallOption.MANDATORY
        self.register_progess()

        self.node_initd_script = os.path.join(Config.install_dir, 'static/system/initd/node')
        self.node_user_home = '/home/node'

    def install(self):

        node_archieve_list = glob.glob(os.path.join(Config.distAppFolder, 'node-*-linux-x64.tar.xz'))

        if not node_archieve_list:
            self.logIt("Can't find node archive", True, True)

        self.createUser('node', self.node_user_home)
        self.addUserToGroup('gluu', 'node')

        nodeArchive = max(node_archieve_list)

        try:
            self.logIt("Extracting %s into /opt" % nodeArchive)
            self.run([paths.cmd_tar, '-xJf', nodeArchive, '-C', '/opt/', '--no-xattrs', '--no-same-owner', '--no-same-permissions'])
        except:
            self.logIt("Error encountered while extracting archive %s" % nodeArchive)

        nodeDestinationPath = max(glob.glob('/opt/node-*-linux-x64'))

        self.run([paths.cmd_ln, '-sf', nodeDestinationPath, Config.node_home])
        self.run([paths.cmd_chmod, '-R', "755", "%s/bin/" % nodeDestinationPath])

        self.render_templates()

        # Create temp folder
        self.run([paths.cmd_mkdir, '-p', "%s/temp" % Config.node_home])

        node_user_group = '{}:{}'.format(Config.node_user, Config.gluu_group)

        # Copy init.d script
        self.copyFile(self.node_initd_script, Config.gluuOptSystemFolder)
        self.run([paths.cmd_chmod, '-R', "755", "%s/node" % Config.gluuOptSystemFolder])

        self.run([paths.cmd_chown, '-R', node_user_group, nodeDestinationPath])
        self.run([paths.cmd_chown, '-h', node_user_group, Config.node_home])

        self.run([paths.cmd_mkdir, '-p', self.node_base])
        self.run([paths.cmd_chown, '-R', node_user_group, self.node_base])


    def render_templates(self):
        self.logIt("Rendering node templates")
        self.templates_rendered = True
        # make variables of this class accesible from Config
        self.update_rendering_dict()

        nodeTepmplatesFolder = os.path.join(Config.templateFolder, 'node')
        self.render_templates_folder(nodeTepmplatesFolder)

    def installNodeService(self, serviceName):
        self.logIt("Installing node service %s..." % serviceName)

        if hasattr(self, 'service_user'):
            Config.templateRenderingDict['service_user'] = self.service_user
        else:
            Config.templateRenderingDict['service_user'] = Config.node_user

        if not self.templates_rendered:
            self.render_templates()

        try:
            self.renderTemplateInOut(serviceName, os.path.join(Config.templateFolder, 'node'), os.path.join(Config.outputFolder, 'node'))
        except Exception:
            self.logIt("Error rendering service '%s' defaults" % serviceName, True)
            self.logIt(traceback.format_exc(), True)


        nodeServiceConfiguration = os.path.join(Config.outputFolder, 'node', serviceName)
        self.copyFile(nodeServiceConfiguration, Config.osDefault)
        self.run([paths.cmd_chown, 'root:root', os.path.join(Config.osDefault, serviceName)])

        if serviceName == 'passport':
            initscript_fn = os.path.join(Config.gluuOptSystemFolder, serviceName)
            self.fix_init_scripts(serviceName, initscript_fn)
        else:
            self.run([paths.cmd_ln, '-sf', '%s/node' % Config.gluuOptSystemFolder, '/etc/init.d/%s' % serviceName])

        self.render_unit_file(serviceName)

        if Config.profile == SetupProfiles.DISA_STIG:
            self.fapolicyd_access(serviceName, nodeServiceConfiguration)

        self.run([paths.cmd_chown, '-R', '{}:gluu'.format(Config.templateRenderingDict['service_user']), nodeServiceConfiguration])
