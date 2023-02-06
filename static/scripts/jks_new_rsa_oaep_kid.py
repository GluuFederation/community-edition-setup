import os
import json
import ldap3
import zipfile


ldap_info = {}

with open('/etc/gluu/conf/gluu-ldap.properties') as f:
    for l in f:
        ls = l.strip()
        for k in ('bindDN', 'bindPassword', 'servers'):
            if ls.startswith(k):
                n = ls.find(':')
                ldap_info[k] = ls[n+1:].strip()


ldap_info['bindPassword'] = os.popen('/opt/gluu/bin/encode.py -D ' + ldap_info['bindPassword']).readline().strip('\n')
ldap_host, ldap_port = ldap_info['servers'].split(',')[0].strip().split(':')


ldap_server = ldap3.Server(ldap_host, port=int(ldap_port), use_ssl=True)
ldap_conn = ldap3.Connection(ldap_server, user=ldap_info['bindDN'], password=ldap_info['bindPassword'])
ldap_conn.bind()

print("Obtaining current infromation from LDAP")
oxauth_dn = 'ou=oxauth,ou=configuration,o=gluu'
ldap_conn.search(
            search_base=oxauth_dn,
            search_scope=ldap3.BASE,
            search_filter='(objectClass=oxAuthConfiguration)',
            attributes=['oxAuthConfDynamic', 'oxAuthConfWebKeys']
            )

oxAuthConfDynamic = json.loads(ldap_conn.response[0]['attributes']['oxAuthConfDynamic'][0])
oxAuthConfWebKeys = json.loads(ldap_conn.response[0]['attributes']['oxAuthConfWebKeys'][0])

keyStoreFile = oxAuthConfDynamic['keyStoreFile']
keyStoreSecret = oxAuthConfDynamic['keyStoreSecret']

ox_key_tool_path = '/opt/dist/gluu/oxauth-client-jar-with-dependencies.jar'
java_path = '/opt/jre/bin/java'
keytool_path = '/opt/jre/bin/keytool'
new_key_fn = '/tmp/{}.jks'.format(os.urandom(4).hex())
new_key_pw = os.urandom(4).hex()


oxauth_zip = zipfile.ZipFile(ox_key_tool_path)
pom_txt = oxauth_zip.read('META-INF/maven/org.gluu/oxauth-model/pom.properties')
for l in pom_txt.decode().splitlines():
     ls = l.strip()
     if ls.startswith('version'):
         n = ls.find('=')
         ver_s = ls[n+1:].strip()

n_ = ver_s.find('-')
if n_ > -1:
    ver_s = ver_s[:n_]
ver_l = ver_s.split('.')
verl = []

for v in ver_l:
    if v.isnumeric():
         verl.append(v)
    else:
        break

for i in range(3-len(verl)):
    verl.append('0')

ox_version = '.'.join(verl)

key_gen_cmd = '{} -Dlog4j.defaultInitOverride=true -cp {} org.gluu.oxauth.util.KeyGenerator -keystore {} -keypasswd {} -sig_keys RS256 -enc_keys RSA-OAEP -dnname "CN=oxAuth CA Certificates" -expiration 365'.format(java_path, ox_key_tool_path, new_key_fn, new_key_pw)


if ox_version > '4.4.0':
    key_gen_cmd += ' -key_length 4096'


print("Generating new temporary jks", new_key_fn, key_gen_cmd)
result = os.popen(key_gen_cmd).read()
keys_json = json.loads(result)

for jkey in keys_json['keys']:
    if jkey['alg'] == 'RSA-OAEP':
        new_kid =  jkey['kid']
        break

oxAuthConfWebKeys['keys'].append(jkey)

key_import_cmd = [
    keytool_path, '-importkeystore',
    '-srckeystore', new_key_fn,
    '-destkeystore', keyStoreFile,
    '-srcstoretype', 'JKS',
    '-deststoretype', 'JKS',
    '-srcstorepass', new_key_pw,
    '-deststorepass', keyStoreSecret,
    '-srcalias', new_kid,
    '-destalias', new_kid,
    '-noprompt'
    ]

print("Importing kid {} to {}".format(new_kid, keyStoreFile))
os.system(' '.join(key_import_cmd))

print("Updating oxAuthConfWebKeys")
oxAuthConfWebKeys_s = json.dumps(oxAuthConfWebKeys, indent=2)
ldap_conn.modify(oxauth_dn, {'oxAuthConfWebKeys': [(ldap3.MODIFY_REPLACE, [oxAuthConfWebKeys_s])]})

print("Removing temporary jks", new_key_fn)
os.remove(new_key_fn)
