import os
import re
import base64
import json

from collections import OrderedDict
from pathlib import Path

from setup_app.pylib.pyDes import triple_des, ECB, PAD_PKCS5

from setup_app import paths
from setup_app import static
from setup_app.config import Config

class Crypto64:

    def get_ssl_subject(self, ssl_fn):
        retDict = {}
        cmd = paths.cmd_openssl + ' x509  -noout -subject -nameopt RFC2253 -in {}'.format(ssl_fn)
        s = self.run(cmd, shell=True)
        s = s.strip() + ','

        for k in ('emailAddress', 'CN', 'O', 'L', 'ST', 'C'):
            rex = re.search('{}=(.*?),'.format(k), s)
            retDict[k] = rex.groups()[0] if rex else ''

        return retDict

    def obscure(self, data=""):
        engine = triple_des(Config.encode_salt, ECB, pad=None, padmode=PAD_PKCS5)
        data = data.encode('utf-8')
        en_data = engine.encrypt(data)
        encoded_pw = base64.b64encode(en_data)
        return encoded_pw.decode('utf-8')

    def unobscure(self, data=""):
        engine = triple_des(Config.encode_salt, ECB, pad=None, padmode=PAD_PKCS5)
        cipher = triple_des(Config.encode_salt)
        decrypted = cipher.decrypt(base64.b64decode(data), padmode=PAD_PKCS5)
        return decrypted.decode('utf-8')

    def gen_cert(self, suffix, password, user='root', cn=None, truststore_fn=None):
        self.logIt('Generating Certificate for %s' % suffix)
        key_with_password = os.path.join(Config.certFolder, suffix + '.key.orig')
        key_without_password = os.path.join(Config.certFolder, suffix + '.key.noenc')
        key = '%s/%s.key' % (Config.certFolder, suffix)
        csr = '%s/%s.csr' % (Config.certFolder, suffix)
        public_certificate = '%s/%s.crt' % (Config.certFolder, suffix)
        if not truststore_fn:
            truststore_fn = Config.defaultTrustStoreFN


        if Config.profile == static.SetupProfiles.DISA_STIG:
            self.run([paths.cmd_openssl,
                  'genrsa',
                  '-out',
                  key_without_password,
                  ])

            self.run([paths.cmd_openssl,
                  'pkey',
                  '-in',
                  key_without_password,
                  '-out',
                  key_with_password,
                  '-des3',
                  '-passout',
                  'pass:%s' % password,
                  ])

            # remove unencrypted key
            os.remove(key_without_password)

        else:

            self.run([paths.cmd_openssl,
                      'genrsa',
                      '-des3',
                      '-out',
                      key_with_password,
                      '-passout',
                      'pass:%s' % password,
                      '2048'
                      ])

        self.run([paths.cmd_openssl,
                  'rsa',
                  '-in',
                  key_with_password,
                  '-passin',
                  'pass:%s' % password,
                  '-out',
                  key
                  ])

        certCn = cn
        if certCn == None:
            certCn = Config.hostname

        self.run([paths.cmd_openssl,
                  'req',
                  '-new',
                  '-key',
                  key,
                  '-out',
                  csr,
                  '-subj',
                  '/C=%s/ST=%s/L=%s/O=%s/CN=%s/emailAddress=%s' % (Config.countryCode, Config.state, Config.city, Config.orgName, certCn, Config.admin_email)
                  ])
        self.run([paths.cmd_openssl,
                  'x509',
                  '-req',
                  '-days',
                  '365',
                  '-in',
                  csr,
                  '-signkey',
                  key,
                  '-out',
                  public_certificate
                  ])
        self.run([paths.cmd_chown, '%s:%s' % (user, user), key_with_password])
        self.run([paths.cmd_chmod, '700', key_with_password])
        self.run([paths.cmd_chown, '%s:%s' % (user, user), key])
        self.run([paths.cmd_chmod, '700', key])

        self.run([Config.cmd_keytool, "-import", "-trustcacerts", "-alias", "%s_%s" % (Config.hostname, suffix), \
                  "-file", public_certificate, "-keystore", truststore_fn, \
                  "-storepass", "changeit", "-noprompt"])

    def prepare_base64_extension_scripts(self, extensions=[]):
        self.logIt("Preparing scripts")
        extension_path = Path(Config.extensionFolder)
        for ep in extension_path.glob("**/*"):
            if ep.is_file() and ep.suffix in ['.py']:
                extension_type = ep.parent.name.lower()
                extension_name = ep.stem.lower()
                extension_script_name = '{}_{}'.format(extension_type, extension_name)

                if extensions and extension_script_name not in extensions:
                    continue

                # Prepare key for dictionary
                base64_script_file = self.generate_base64_file(ep.as_posix(), 1)
                Config.templateRenderingDict[extension_script_name] = base64_script_file


    def generate_base64_file(self, fn, num_spaces):
        self.logIt('Loading file %s' % fn)
        plain_file_b64encoded_text = None
        try:
            plain_file_text = self.readFile(fn, rmode='rb')
            plain_file_b64encoded_text = base64.b64encode(plain_file_text).decode('utf-8').strip()
        except:
            self.logIt("Error loading file", True)

        if num_spaces > 0:
            plain_file_b64encoded_text = self.reindent(plain_file_b64encoded_text, num_spaces)

        return plain_file_b64encoded_text

    def generate_base64_ldap_file(self, fn):
        return self.generate_base64_file(fn, 1)

    def gen_keystore(self, suffix, keystoreFN, keystorePW, inKey, inCert):

        self.logIt("Creating keystore %s" % suffix)
        # Convert key to pkcs12
        pkcs_fn = '%s/%s.pkcs12' % (Config.certFolder, suffix)
        self.run([paths.cmd_openssl,
                  'pkcs12',
                  '-export',
                  '-inkey',
                  inKey,
                  '-in',
                  inCert,
                  '-out',
                  pkcs_fn,
                  '-name',
                  Config.hostname,
                  '-passout',
                  'pass:%s' % keystorePW
                  ])
        # Import p12 to keystore
        self.run([Config.cmd_keytool,
                  '-importkeystore',
                  '-srckeystore',
                  '%s/%s.pkcs12' % (Config.certFolder, suffix),
                  '-srcstorepass',
                  keystorePW,
                  '-srcstoretype',
                  'PKCS12',
                  '-destkeystore',
                  keystoreFN,
                  '-deststorepass',
                  keystorePW,
                  '-deststoretype',
                  Config.default_store_type,
                  '-keyalg',
                  'RSA',
                  '-noprompt'
                  ])


    def gen_openid_data_store_keys(self, data_store_path, data_store_pwd, data_store_create=True, key_expiration=None, dn_name=None, key_algs=None, enc_keys=None):
        self.logIt("Generating oxAuth OpenID Connect keys")

        if dn_name == None:
            dn_name = Config.default_openid_dstore_dn_name

        if key_algs == None:
            key_algs = Config.default_key_algs

        if key_expiration == None:
            key_expiration = Config.default_key_expiration

        if not enc_keys:
            enc_keys = key_algs

        client_cmd = self.get_key_gen_client_cmd()

        cmd = " ".join([Config.cmd_java,
                        "-Dlog4j.defaultInitOverride=true",
                        "-cp", client_cmd,
                        Config.non_setup_properties['key_gen_path'],
                        "-keystore",
                        data_store_path,
                        "-keypasswd",
                        data_store_pwd,
                        "-sig_keys",
                        "%s" % key_algs,
                        "-enc_keys",
                        "%s" % enc_keys,
                        "-dnname",
                        '"%s"' % dn_name,
                        "-expiration",
                        "%s" % key_expiration])

        output = self.run([cmd], shell=True)

        if output:
            return output.splitlines()

    def get_key_gen_client_cmd(self):
        if Config.profile == static.SetupProfiles.DISA_STIG:
            client_cmd = '{}:{}:{}'.format(
                        Config.non_setup_properties['oxauth_client_noprivder_jar_fn'],
                        Config.bc_fips_jar,
                        Config.bcpkix_fips_jar
                        )
        else:
            client_cmd = Config.non_setup_properties['oxauth_client_jar_fn']

        return client_cmd

    def get_key_gen_client_provider_cmd(self):
        return Config.non_setup_properties['oxauth_client_jar_fn']

    def get_keytool_provider(self):
        provider_list = ['-storetype', Config.default_store_type]
        if Config.profile == static.SetupProfiles.DISA_STIG:
            provider_list += [
                                '-providername', 'BCFIPS',
                                '-providerpath', '{}:{}'.format(Config.bc_fips_jar, Config.bcpkix_fips_jar),
                                '-providerclass', 'org.bouncycastle.jcajce.provider.BouncyCastleFipsProvider'
                             ]
        return provider_list

    def export_openid_key(self, data_store_path, data_store_pwd, cert_alias, cert_path):
        self.logIt("Exporting oxAuth OpenID Connect keys")
        client_cmd = self.get_key_gen_client_cmd()
        cmd = " ".join([Config.cmd_java,
                        "-Dlog4j.defaultInitOverride=true",
                        "-cp", client_cmd,
                        Config.non_setup_properties['key_export_path'],
                        "-keystore",
                        data_store_path,
                        "-keypasswd",
                        data_store_pwd,
                        "-alias",
                        cert_alias,
                        "-exportfile",
                        cert_path])
        self.run(['/bin/sh', '-c', cmd])

    def write_openid_keys(self, fn, jwks):
        self.logIt("Writing oxAuth OpenID Connect keys")

        if not jwks:
            self.logIt("Failed to write oxAuth OpenID Connect key to %s" % fn)
            return

        self.backupFile(fn)

        try:
            jwks_text = '\n'.join(jwks)
            self.writeFile(fn, jwks_text)
            self.run([Config.cmd_chown, Config.user_group, fn])
            self.run([Config.cmd_chmod, '600', fn])
            self.logIt("Wrote oxAuth OpenID Connect key to %s" % fn)
        except:
            self.logIt("Error writing command : %s" % fn, True)



    def generate_base64_string(self, lines, num_spaces):
        if not lines:
            return None

        plain_text = ''.join(lines)
        plain_b64encoded_text = base64.encodestring(plain_text.encode('utf-8')).decode('utf-8').strip()

        if num_spaces > 0:
            plain_b64encoded_text = self.reindent(plain_b64encoded_text, num_spaces)

        return plain_b64encoded_text

    def encode_passwords(self):
        self.logIt("Encoding passwords")

        if Config.ldapPass:
            Config.encoded_ox_ldap_pw = self.obscure(Config.ldapPass)

        if Config.cb_password:
            Config.encoded_cb_password = self.obscure(Config.cb_password)

        if not Config.get('opendj_truststore_pass'):
            Config.opendj_truststore_pass = os.urandom(6).hex()

        Config.opendj_truststore_pass_enc = self.obscure(Config.opendj_truststore_pass)

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
        except:
            self.logIt("Error encoding test passwords", True)

    def remove_pcks11_keys(self, keys=['server-cert', 'admin-cert', 'dummy']):
        output = self.run([Config.cmd_keytool, '-list', '-keystore', 'NONE', '-storetype', 'PKCS11', '-storepass', 'changeit'])
        for l in output.splitlines():
            if 'PrivateKeyEntry' in l:
                alias = l.split(',')[0]
                if alias in keys:
                    self.run([Config.cmd_keytool, '-delete', '-alias', alias, '-keystore', 'NONE', '-storetype', 'PKCS11', '-storepass', 'changeit'])
