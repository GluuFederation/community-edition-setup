import os
import time
import zipfile
import inspect
import base64
import shutil
import glob
import re

from pathlib import Path

from setup_app import paths
from setup_app import static
from setup_app.utils import base
from setup_app.static import InstallTypes, AppType, InstallOption
from setup_app.config import Config
from setup_app.utils.setup_utils import SetupUtils
from setup_app.utils.progress import gluuProgress
from setup_app.installers.base import BaseInstaller

class GluuInstaller(BaseInstaller, SetupUtils):

    install_var = 'installGluu'

    def __repr__(self):
        txt = ''
        try:
            if not Config.installed_instance:
                txt += 'hostname'.ljust(30) + Config.hostname.rjust(35) + "\n"
                txt += 'orgName'.ljust(30) + Config.orgName.rjust(35) + "\n"
                txt += 'os'.ljust(30) + Config.os_type.rjust(35) + "\n"
                txt += 'city'.ljust(30) + Config.city.rjust(35) + "\n"
                txt += 'state'.ljust(30) + Config.state.rjust(35) + "\n"
                txt += 'countryCode'.ljust(30) + Config.countryCode.rjust(35) + "\n"
                txt += 'Applications max ram'.ljust(30) + str(Config.application_max_ram).rjust(35) + "\n"

                txt += 'Install oxAuth'.ljust(30) + repr(Config.installOxAuth).rjust(35) + "\n"
                txt += 'Install oxTrust'.ljust(30) + repr(Config.installOxTrust).rjust(35) + "\n"

                bc = []
                if Config.wrends_install:
                    t_ = 'opendj'
                    if Config.wrends_install == InstallTypes.REMOTE:
                        t_ += '[R]'
                    bc.append(t_)

                if Config.cb_install:
                    t_ = 'couchbase'
                    if Config.cb_install == InstallTypes.REMOTE:
                        t_ += '[R]'
                    bc.append(t_)

                if Config.rdbm_install:
                    t_ = Config.rdbm_type
                    if Config.rdbm_install_type == InstallTypes.REMOTE:
                        t_ += '[R]'
                    bc.append(t_)

                if bc:
                    bct = ', '.join(bc)
                    txt += 'Backends'.ljust(30) + bct.rjust(35) + "\n"

                txt += 'Java Type'.ljust(30) + Config.java_type.rjust(35) + "\n"

            txt += 'Install Apache 2 web server'.ljust(30) + repr(Config.installHttpd).rjust(35) + (' *' if 'installHttpd' in Config.addPostSetupService else '') + "\n"
            txt += 'Install Fido2 Server'.ljust(30) + repr(Config.installFido2).rjust(35) + (' *' if 'installFido2' in Config.addPostSetupService else '') + "\n"
            txt += 'Install Scim Server'.ljust(30) + repr(Config.installScimServer).rjust(35) + (' *' if 'installScimServer' in Config.addPostSetupService else '') + "\n"
            txt += 'Install Shibboleth SAML IDP'.ljust(30) + repr(Config.installSaml).rjust(35) + (' *' if 'installSaml' in Config.addPostSetupService else '') + "\n"
            txt += 'Install Passport '.ljust(30) + repr(Config.installPassport).rjust(35) + (' *' if 'installPassport' in Config.addPostSetupService else '') + "\n"
            txt += 'Install Casa '.ljust(30) + repr(Config.installCasa).rjust(35) + (' *' if 'installCasa' in Config.addPostSetupService else '') + "\n"
            txt += 'Install Oxd '.ljust(30) + repr(Config.installOxd).rjust(35) + (' *' if 'installOxd' in Config.addPostSetupService else '') + "\n"
            txt += 'Install Gluu Radius '.ljust(30) + repr(Config.installGluuRadius).rjust(35) + (' *' if 'installGluuRadius' in Config.addPostSetupService else '') + "\n"
            txt += 'Load Test Data '.ljust(30) + repr( base.argsp.t).rjust(35) + "\n"
            return txt

        except:
            s = ""
            if not base.argsp.dummy:
                for key in list(Config.__dict__):
                    if not key in ('__dict__',):
                        val = getattr(Config, key)
                        if not inspect.ismethod(val):
                            s = s + "%s\n%s\n%s\n\n" % (key, "-" * len(key), val)
            return s


    def initialize(self):
        self.service_name = 'gluu'
        self.app_type = AppType.APPLICATION
        self.install_type = InstallOption.MONDATORY
        gluuProgress.register(self)

        Config.install_time_ldap = time.strftime('%Y%m%d%H%M%SZ', time.gmtime(time.time()))
        if not os.path.exists(Config.distFolder):
            print("Please ensure that you are running this script inside Gluu container.")
            sys.exit(1)

        #Download oxauth-client-jar-with-dependencies
        if not os.path.exists(Config.non_setup_properties['oxauth_client_jar_fn']):
            oxauth_client_jar_url = 'https://ox.gluu.org/maven/org/gluu/oxauth-client/{0}/oxauth-client-{0}-jar-with-dependencies.jar'.format(Config.oxVersion)
            self.logIt("Downloading {}".format(os.path.basename(oxauth_client_jar_url)))
            base.download(oxauth_client_jar_url, Config.non_setup_properties['oxauth_client_jar_fn'])

        self.determine_key_gen_path()

    def determine_key_gen_path(self):

        self.logIt("Determining key generator path")
        oxauth_client_jar_zf = zipfile.ZipFile(Config.non_setup_properties['oxauth_client_jar_fn'])

        for f in oxauth_client_jar_zf.namelist():
            if os.path.basename(f) == 'KeyGenerator.class':
                p, e = os.path.splitext(f)
                Config.non_setup_properties['key_gen_path'] = p.replace(os.path.sep, '.')
            elif os.path.basename(f) == 'KeyExporter.class':
                p, e = os.path.splitext(f)
                Config.non_setup_properties['key_export_path'] = p.replace(os.path.sep, '.')

        if (not 'key_gen_path' in Config.non_setup_properties) or (not 'key_export_path' in Config.non_setup_properties):
            self.logIt("Can't determine key generator and/or key exporter path form {}".format(Config.non_setup_properties['oxauth_client_jar_fn']), True, True)
        else:
            self.logIt("Key generator path was determined as {}".format(Config.non_setup_properties['key_export_path']))

    def configureSystem(self):
        self.logIt("Configuring system", 'gluu')
        self.customiseSystem()
        if not base.snap:
            self.createGroup('gluu')
        self.makeFolders()

        if Config.persistence_type == 'hybrid':
            self.writeHybridProperties()

    def makeFolders(self):
        # Create these folder on all instances
        for folder in (Config.gluuOptFolder, Config.gluuOptBinFolder, Config.gluuOptSystemFolder,
                        Config.gluuOptPythonFolder, Config.configFolder, Config.certFolder,
                        Config.outputFolder, Config.osDefault):

            if not os.path.exists(folder):
                self.run([paths.cmd_mkdir, '-p', folder])

        if not base.snap:
            self.run([paths.cmd_chown, '-R', 'root:gluu', Config.certFolder])
            self.run([paths.cmd_chmod, '551', Config.certFolder])
            
            self.run([paths.cmd_chmod, 'ga+w', "/tmp"]) # Allow write to /tmp

    def customiseSystem(self):

        if not base.snap:
            if Config.os_initdaemon == 'init':
                system_profile_update = Config.system_profile_update_init
            else:
                system_profile_update = Config.system_profile_update_systemd

            # Render customized part
            self.renderTemplate(system_profile_update)
            renderedSystemProfile = self.readFile(system_profile_update)

            # Read source file
            currentSystemProfile = self.readFile(Config.sysemProfile)

            # Write merged file
            self.backupFile(Config.sysemProfile)
            resultSystemProfile = "\n".join((currentSystemProfile, renderedSystemProfile))
            self.writeFile(Config.sysemProfile, resultSystemProfile)

            # Fix new file permissions
            self.run([paths.cmd_chmod, '644', Config.sysemProfile])

    def make_salt(self):

        if not Config.encode_salt:
            Config.encode_salt= self.getPW() + self.getPW()

        self.logIt("Making salt")
        salt_fn = os.path.join(Config.configFolder,'salt')

        try:
            salt_text = 'encodeSalt = {}'.format(Config.encode_salt)
            self.writeFile(salt_fn, salt_text)
        except:
            self.logIt("Error writing salt", True, True)

    def render_templates(self, templates=None):
        self.logIt("Rendering templates")

        if not templates:
            templates = Config.ce_templates

        if Config.persistence_type in ('couchbase', 'sql', 'spanner'):
            Config.ce_templates[Config.ox_ldap_properties] = False

        for fullPath in templates:
            try:
                self.renderTemplate(fullPath)
            except:
                self.logIt("Error writing template %s" % fullPath, True)


    def render_configuration_template(self):
        self.logIt("Rendering configuration templates")

        try:
            self.renderTemplate(Config.ldif_configuration)
        except:
            self.logIt("Error writing template", True)


    def render_test_templates(self):
        self.logIt("Rendering test templates")

        testTepmplatesFolder = os.path.join(self.templateFolder, 'test')
        self.render_templates_folder(testTepmplatesFolder)

    def writeHybridProperties(self):

        ldap_mappings = self.getMappingType('ldap')
        couchbase_mappings = self.getMappingType('couchbase')
        
        for group in Config.mappingLocations:
            if group == 'default':
                default_mapping = Config.mappingLocations[group]
                break

        storages = set(Config.mappingLocations.values())

        gluu_hybrid_roperties = [
                        'storages: {0}'.format(', '.join(storages)),
                        'storage.default: {0}'.format(default_mapping),
                        ]

        if ldap_mappings:
            gluu_hybrid_roperties.append('storage.ldap.mapping: {0}'.format(', '.join(ldap_mappings)))
            ldap_map_list = []
            for m in ldap_mappings:
                if m != 'default':
                    ldap_map_list.append(Config.couchbaseBucketDict[m]['mapping'])
            gluu_hybrid_roperties.append('storage.ldap.mapping: {0}'.format(', '.join(ldap_map_list)))

        if couchbase_mappings:
            cb_map_list = []
            for m in couchbase_mappings:
                if m != 'default':
                    cb_map_list.append(Config.couchbaseBucketDict[m]['mapping'])
            cb_map_str = ', '.join(cb_map_list)
            gluu_hybrid_roperties.append('storage.couchbase.mapping: {0}'.format(cb_map_str))

        gluu_hybrid_roperties_content = '\n'.join(gluu_hybrid_roperties)

        self.writeFile(Config.gluu_hybrid_roperties_fn, gluu_hybrid_roperties_content)


    def setup_init_scripts(self):
        self.logIt("Setting up init scripts")
        if base.os_initdaemon == 'initd':
            for init_file in Config.init_files:
                try:
                    script_name = os.path.split(init_file)[-1]
                    self.copyFile(init_file, "/etc/init.d")
                    self.run([paths.cmd_chmod, "755", "/etc/init.d/%s" % script_name])
                except:
                    self.logIt("Error copying script file %s to /etc/init.d" % init_file)

        if base.clone_type == 'rpm':
            for service in Config.redhat_services:
                self.run(["/sbin/chkconfig", service, "on"])
        elif not base.snap:
            for service in Config.debian_services:
                self.run([paths.cmd_update_rc , service, 'defaults'])
                self.run([paths.cmd_update_rc, service, 'enable'])


    def copy_scripts(self):
        self.logIt("Copying script files")

        for script in Config.gluuScriptFiles:
            self.copyFile(script, Config.gluuOptBinFolder)

        self.logIt("Rendering encode.py")
        encode_script = self.readFile(os.path.join(Config.templateFolder, 'encode.py'))
        encode_script = encode_script % self.merge_dicts(Config.__dict__, Config.templateRenderingDict)
        self.writeFile(os.path.join(Config.gluuOptBinFolder, 'encode.py'), encode_script)

        super_gluu_lisence_renewer_fn = os.path.join(Config.staticFolder, 'scripts', 'super_gluu_license_renewer.py')

        if base.snap:
            target_fn = os.path.join(Config.gluuOptBinFolder, 'super_gluu_lisence_renewer.py')
            self.run(['cp', '-f', super_gluu_lisence_renewer_fn, target_fn])

        else:
            target_fn = '/etc/cron.daily/super_gluu_lisence_renewer'
            self.run(['cp', '-f', super_gluu_lisence_renewer_fn, target_fn])
            self.run([paths.cmd_chown, 'root:root', target_fn])
            self.run([paths.cmd_chmod, '+x', target_fn])

            print_version_scr_fn = os.path.join(Config.install_dir, 'setup_app/utils/printVersion.py')
            self.run(['cp', '-f', print_version_scr_fn , Config.gluuOptBinFolder])
            self.run([paths.cmd_ln, '-s', 'printVersion.py' , 'show_version.py'], cwd=Config.gluuOptBinFolder)

        for scr in Path(Config.gluuOptBinFolder).glob('*'):
            scr_path = scr.as_posix()
            if base.snap and scr_path.endswith('.py'):
                scr_content = self.readFile(scr_path).splitlines()
                first_line = '#!' + paths.cmd_py3
                if scr_content[0].startswith('#!'):
                    scr_content[0] = first_line
                else:
                    scr_content.insert(0, first_line)
                self.writeFile(scr_path, '\n'.join(scr_content), backup=False)

            self.run([paths.cmd_chmod, '700', scr_path])

    def update_hostname(self):
        self.logIt("Copying hosts and hostname to final destination")

        if base.os_initdaemon == 'systemd' and base.clone_type == 'rpm':
            self.run(['/usr/bin/hostnamectl', 'set-hostname', Config.hostname])
        else:
            if Config.os_type in ['debian', 'ubuntu']:
                self.copyFile("%s/hostname" % Config.outputFolder, Config.etc_hostname)
                self.run(['/bin/chmod', '-f', '644', Config.etc_hostname])

            if Config.os_type in ['centos', 'red', 'fedora']:
                self.copyFile("%s/network" % Config.outputFolder, Config.network)

            self.run(['/bin/hostname', Config.hostname])

        if not os.path.exists(Config.etc_hosts):
            self.writeFile(Config.etc_hosts, '{}\t{}\n'.format(Config.ip, Config.hostname))
        else:
            hostname_file_content = self.readFile(Config.etc_hosts)
            with open(Config.etc_hosts,'w') as w:
                for l in hostname_file_content.splitlines():
                    if not Config.hostname in l.split():
                        w.write(l+'\n')

                w.write('{}\t{}\n'.format(Config.ip, Config.hostname))

        self.run([paths.cmd_chmod, '-R', '644', Config.etc_hosts])

    def set_ulimits(self):
        self.logIt("Setting ulimist")
        try:
            apache_user = 'apache' if base.clone_type == 'rpm' else 'www-data'

            self.appendLine("ldap       soft nofile     131072", "/etc/security/limits.conf")
            self.appendLine("ldap       hard nofile     262144", "/etc/security/limits.conf")
            self.appendLine("%s     soft nofile     131072" % apache_user, "/etc/security/limits.conf")
            self.appendLine("%s     hard nofile     262144" % apache_user, "/etc/security/limits.conf")
            self.appendLine("jetty      soft nofile     131072", "/etc/security/limits.conf")
            self.appendLine("jetty      hard nofile     262144", "/etc/security/limits.conf")
        except:
            self.logIt("Could not set limits.")


    def copy_output(self):
        self.logIt("Copying rendered templates to final destination")

        for dest_fn in list(Config.ce_templates.keys()):
            if Config.ce_templates[dest_fn]:
                fn = os.path.split(dest_fn)[-1]
                output_fn = os.path.join(Config.outputFolder, fn)
                try:
                    self.logIt("Copying %s to %s" % (output_fn, dest_fn))
                    dest_dir = os.path.dirname(dest_fn)
                    if not os.path.exists(dest_dir):
                        self.logIt("Created destination folder %s" % dest_dir)
                        os.makedirs(dest_dir)
                    self.backupFile(output_fn, dest_fn)
                    shutil.copyfile(output_fn, dest_fn)
                except:
                    self.logIt("Error writing %s to %s" % (output_fn, dest_fn), True)


    def render_custom_templates(self, ldif_dir):
        output_dir_p = Path(ldif_dir + '.output')
        self.logIt("Rendering custom templates from {} to {}".format(ldif_dir, output_dir_p))

        for p in Path(ldif_dir).rglob('*'):
            if p.is_file():
                out_file_p = output_dir_p.joinpath(p.relative_to(ldif_dir))
                if not out_file_p.parent.exists():
                    out_file_p.parent.mkdir(parents=True)
                    try:
                        self.renderTemplateInOut(p.as_posix(), p.parent.as_posix(), out_file_p.parent.as_posix())
                    except Exception:
                        self.logIt("Error writing template {}".format(out_file_p), True)


    def import_custom_ldif_dir(self, ldif_dir):
        self.logIt("Importing Custom LDIF files", pbar='post-setup')
        self.render_custom_templates(ldif_dir)

        output_dir = ldif_dir + '.output'

        for p in Path(output_dir).rglob('*.ldif'):
            ldif = p.as_posix()
            self.logIt("Importing rendered custom ldif {}".format(ldif))
            try:
                self.dbUtils.import_ldif([ldif])
            except Exception:
                self.logIt("Error importing custom ldif file {}".format(ldif), True)


    def post_install_tasks(self):
        # set systemd timeout
        self.set_systemd_timeout()

        if base.argsp.import_ldif:
            self.import_custom_ldif_dir(base.argsp.import_ldif)

        self.deleteLdapPw()

        if base.snap:
            #write post-install.py script
            self.logIt("Writing snap-post-setup.py", pbar='post-setup')
            post_setup_script = self.readFile(os.path.join(Config.templateFolder, 'snap-post-setup.py'))

            for key, val in (('{{SNAP_NAME}}', os.environ['SNAP_NAME']),
                             ('{{SNAP_PY3}}', paths.cmd_py3),
                             ('{{SNAP}}', base.snap),
                             ('{{SNAP_COMMON}}', base.snap_common)
                             ):
            
                post_setup_script = post_setup_script.replace(key, val)

            post_setup_script_fn = os.path.join(Config.install_dir, 'snap-post-setup.py')
            with open(post_setup_script_fn, 'w') as w:
                w.write(post_setup_script)
            self.run([paths.cmd_chmod, '+x', post_setup_script_fn])

            if not Config.installed_instance:
                Config.post_messages.insert(0, "Please execute:\nsudo " + post_setup_script_fn)

            self.logIt("Setting permissions", pbar='post-setup')

            for crt_fn in Path(os.path.join(base.snap_common, 'etc/certs')).glob('*'):
                self.run([paths.cmd_chmod, '0600', crt_fn.as_posix()])

            for spath in ('gluu', 'etc/gluu/conf', 'opendj/db'):
                for gpath in Path(os.path.join(base.snap_common, spath)).rglob('*'):
                    if ('node_modules' in gpath.as_posix()) or ('gluu/bin' in gpath.as_posix()) or ('jetty/temp' in gpath.as_posix()):
                        continue
                    chm_mode = '0755' if os.path.isdir(gpath.as_posix()) else '0600'
                    self.run([paths.cmd_chmod, chm_mode, gpath.as_posix()])

            self.add_yacron_job(
                    command = os.path.join(Config.gluuOptBinFolder, 'super_gluu_lisence_renewer.py'), 
                    schedule = '0 2 * * *', # everyday at 2 am
                    name='super-gluu-license-renewer', 
                    args={'captureStderr': True}
                    )

            self.restart('yacron')

            self.writeFile(os.path.join(base.snap_common, 'etc/hosts.gluu'), Config.ip + '\t' + Config.hostname)

        else:
            for f in os.listdir(Config.certFolder):
                if not f.startswith('passport-'):
                    fpath = os.path.join(Config.certFolder, f)
                    self.run([paths.cmd_chown, 'root:gluu', fpath])
                    self.run([paths.cmd_chmod, '660', fpath])
                    self.run([paths.cmd_chmod, 'u+X', fpath])
            self.run([paths.cmd_chown, '-R', 'root:gluu', Config.gluuOptPythonFolder])

            if not Config.installed_instance:
                cron_service = 'crond' if base.clone_type == 'rpm' else 'cron'
                self.restart(cron_service)



    def after_setup_tasks(self):
        if Config.installSaml and Config.persistence_type in (static.PersistenceType.couchbase, static.PersistenceType.sql):
            attrib_resolver_fn = os.path.join(base.current_app.SamlInstaller.idp3ConfFolder, 'attribute-resolver.xml')
            attrib_resolver = self.readFile(attrib_resolver_fn)
            re_result = re.search(r'<DataConnector(.*?)</DataConnector>', attrib_resolver, re.DOTALL)
            data_connector_fn = os.path.join(base.current_app.SamlInstaller.staticIDP3FolderConf, Config.persistence_type + '_attribute_resolver.xml')
            data_connector = self.readFile(data_connector_fn)

            if re_result:
                replace_string = re_result.group()
                new_attrib_resolver = attrib_resolver.replace(replace_string, data_connector)
                self.writeFile(attrib_resolver_fn, new_attrib_resolver)

            self.stop('idp')
            logs = glob.glob(os.path.join(base.current_app.SamlInstaller.idp3Folder, 'logs/*.log'))
            for log_fn in logs:
                os.remove(log_fn)
            self.start('idp')
