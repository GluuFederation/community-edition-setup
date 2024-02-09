import os
import uuid
import inspect

from pathlib import Path
from distutils.version import LooseVersion

from setup_app import paths
from setup_app import static
from setup_app.utils import base
from setup_app.config import Config
from setup_app.utils.db_utils import dbUtils
from setup_app.utils.progress import gluuProgress
from setup_app.utils.printVersion import get_war_info


class BaseInstaller:
    needdb = True
    dbUtils = dbUtils

    def register_progess(self):
        gluuProgress.register(self)

    def start_installation(self):
        if not hasattr(self, 'pbar_text'):
            pbar_text = "Installing " + self.service_name.title()
        else:
            pbar_text = self.pbar_text
        self.logIt(pbar_text, pbar=self.service_name)

        if self.needdb and not base.argsp.dummy:
            self.dbUtils.bind()

        self.pre_install()

        self.check_for_download()

        self.create_user()

        if not hasattr(self, 'service_user'):
            if Config.profile == static.SetupProfiles.DISA_STIG:
                self.service_user = self.service_name.lower()
            else:
                self.service_user = Config.jetty_user

        self.profile_templates()

        self.create_folders()

        self.install()
        if not base.argsp.dummy:
            self.copy_static()
            self.generate_configuration()

            # before rendering templates, let's push variables of this class to Config.templateRenderingDict
            self.update_rendering_dict()

            self.render_import_templates()
            self.update_backend()

        if Config.profile == static.SetupProfiles.DISA_STIG and self.service_name != 'jetty' and hasattr(self, 'jetty_home'):
            self.run([paths.cmd_chown, '-R', '{}:{}'.format(self.service_user, Config.gluu_group), os.path.join(self.jetty_base, self.service_user)])


    def profile_templates(self, temp_dir=None, recursive=False):
        if not temp_dir:
            if not hasattr(self, 'templates_folder'):
                return
            temp_dir = self.templates_folder

        glob_param = '*.' + Config.profile
        if recursive:
            glob_param = '**/' + glob_param

        for temp_p in Path(temp_dir).glob(glob_param):
            target_p = temp_p.with_suffix('')
            base.logIt("Renaming {} to {}".format(temp_p, target_p))
            temp_p.rename(target_p)


    def update_rendering_dict(self):
        mydict = {}
        for obj_name, obj in inspect.getmembers(self):
            if obj_name in ('dbUtils',):
                continue
            if not obj_name.startswith('__') and (not callable(obj)):
                mydict[obj_name] = obj

        Config.templateRenderingDict.update(mydict)


    def check_clients(self, client_var_id_list, resource=False):
        field_name, ou, object_class = ('oxId', 'resources', 'oxUmaResource') if resource else ('inum', 'clients', 'oxAuthClient')

        for client_var_name, client_id_prefix in client_var_id_list:
            self.logIt("Checking ID for client {}".format(client_var_name))
            if not Config.get(client_var_name):
                result = self.dbUtils.search('ou={},o=gluu'.format(ou), '(&({}={}*)(objectClass={}))'.format(field_name, client_id_prefix, object_class))
                if result:
                    setattr(Config, client_var_name, result[field_name])
                    self.logIt("{} was found in backend as {}".format(client_var_name, result[field_name]))

            if not Config.get(client_var_name):
                setattr(Config, client_var_name, client_id_prefix + str(uuid.uuid4()))
                self.logIt("Client ID for {} was created as {}".format(client_var_name, Config.get(client_var_name)))

    def run_service_command(self, operation, service):
        if not service:
            service = self.service_name

        self.set_systemd_ulimits(service)

        try:
            if (base.clone_type == 'rpm' and base.os_initdaemon == 'systemd') or base.deb_sysd_clone:
                self.run([base.service_path, operation, service], None, None, True)
            else:
                self.run([base.service_path, service, operation], None, None, True)
        except Exception:
            self.logIt("Error running operation {} for service {}".format(operation, service), True)


    def set_systemd_ulimits(self, service):
        umilit_file = '/etc/systemd/system/{}.service.d/override.conf'.format(service)
        if not os.path.exists(umilit_file):
            os.makedirs(os.path.dirname(umilit_file))
            self.writeFile(umilit_file, '[Service]\nLimitNOFILE=262144\n')


    def enable(self, service=None):
        self.run_service_command('enable', service)

    def stop(self, service=None):
        self.run_service_command('stop', service)

    def start(self, service=None):
        self.run_service_command('start', service)

    def restart(self, service=None):
        self.stop(service)
        self.start(service)

    def reload_daemon(self):
        if (base.clone_type == 'rpm' and base.os_initdaemon == 'systemd') or base.deb_sysd_clone:
            self.run([base.service_path, 'daemon-reload'])

    def pre_install(self):
        """Installer may require some settings before installation"""
        pass

    def generate_configuration(self):
        pass

    def render_import_templates(self):
        pass

    def update_backend(self):
        pass


    def check_for_download(self):
        # execute for each installer
        if Config.downloadWars:
            self.download_files(force=True)
            
        elif Config.installed_instance:
            self.download_files()

    def download_file(self, url, src):
        Config.pbar.progress(self.service_name, "Downloading {}".format(os.path.basename(src)))
        base.download(url, src)

    def download_files(self, force=False, downloads=[]):
        if hasattr(self, 'source_files'):
            for i, item in enumerate(self.source_files[:]):
                src = item[0]
                url = item[1]
                src_name = os.path.basename(src)

                if downloads and src_name not in downloads:
                    continue

                if force or self.check_download_needed(src):
                    src = os.path.join(Config.distGluuFolder, src_name)
                    self.source_files[i] = (src, url)
                    self.download_file(url, src)

    def check_download_needed(self, src):
        froot, fext = os.path.splitext(src)
        if fext in ('.war', '.jar'):
            if os.path.exists(src):
                war_info = get_war_info(src)
                if war_info.get('version'):
                    return LooseVersion(war_info['version']) < LooseVersion(Config.oxVersion)

        return True

    def installed(self):
        return os.path.exists(os.path.join(Config.jetty_base, self.service_name, 'start.ini')) or os.path.exists(os.path.join(Config.jetty_base, self.service_name, 'start.d/server.ini'))


    def create_user(self):
        pass

    def create_folders(self):
        pass
    
    def copy_static(self):
        pass

    def check_need_for_download(self):
        pass
