#!/usr/bin/python

import getopt, sys, os, string, json, base64, sys, os.path
from ldif import LDIFParser
from getpass import getpass

ldapsearch_cmd = "/opt/opendj/bin/ldapsearch"
ldapmodify_cmd = "/opt/opendj/bin/ldapmodify"

fn_search = "config-search.ldif"
fn_mod = "config-mod.ldif"

network_args = "-h localhost -p 1636 -Z -X"
bind_args = '-D "cn=directory manager" -j %s'
scope = "-s base"
levels = ["TRACE", "DEBUG", "WARN", "INFO", "ERROR", "FATAL", "OFF"]
systems = {'oxauth': ('oxAuthConfDynamic', 'loggingLevel'), 
          'oxtrust': ('oxTrustConfApplication', 'loggingLevel'),
          'fido2': ('gluuConfDynamic', 'loggingLevel'),
          'oxpassport': ('gluuPassportConfiguration', ''), 
          'casa': ('oxConfApplication', 'log_level')
          }

def usage():
    print("""
REQUIRED
-l --loglevel= : TRACE, DEBUG, WARN, INFO, ERROR, FATAL, OFF
-s --system= : oxauth, oxtrust, fido2, oxpassport, and casa 

OPTIONAL
-h --help 
-F --force: Don't prompt to proceed

The program looks for the ldap directory manager password in /root/.pw. If it's 
not there, it will prompt you for the password, write it to .pw and then delete 
it after the program finishes. 

""")

def writeFile(s, fn):
    f = open(fn, 'w')
    f.write(s)
    f.close()

def main():
    system = None
    loglevel = None
    forceToProceed = False
    fn_pw = '/root/.pw'
    del_pw = False
    try:
        opts, args = getopt.getopt(sys.argv[1:], "-hFl:s:", ["help", "force" "loglevel=", "system="])
    except getopt.GetoptError as err:
        print(err)
        usage()
        sys.exit(2)
    for o, a in opts:
        if o in ("-l", "--loglevel"):
            loglevel = a.upper() 
            if loglevel not in levels:
                print("\nloglevel %s not recognized" % loglevel)
                usage()
                sys.exit(3)
        elif o in ("-F", "--force"):
            forceToProceed = True 
        elif o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o in ("-s", "--system"):
             system = a.lower()
             if system not in systems.keys():
                 print("\nsystem %s not recognized" % system)
                 usage()
                 sys.exit(4)
        else:
            assert False, "unhandled option"


    if (system == None):
        print("\nMissing -s -- you must specify the system")
        usage()
        sys.exit(5)
    
    if (loglevel == None):
        print("\nMissing -l -- you must specify the loglevel")
        usage()
        sys.exit(6)

    if not os.path.isfile(fn_pw):
        del_pw = True
        fn_pw = ".pw"
        pw = getpass("Enter 'cn=directory manager' password: ")
        writeFile(pw, fn_pw)

    configDN = "ou=%s,ou=configuration,o=gluu" % system
    base = "-b %s" % configDN

    cmd = [ldapsearch_cmd,
       network_args,
       bind_args % fn_pw,
       base,
       scope,
       "objectclass=*",
       "> %s" % fn_search]
    os.system(" ".join(cmd))

    parser = LDIFParser(open(fn_search, 'rb'))
    confLDAPAttr =  systems[system][0]
    confValue = None
    for dn, entry in parser.parse():
        confValue = json.loads(entry[confLDAPAttr][0])
        if system != "oxpassport":
            logKey = systems[system][1]
            confValue[logKey] = loglevel 
        else:
            confValue["conf"]["logging"]["level"] = loglevel.lower()

    confValue = json.dumps(confValue)
    message_bytes = confValue.encode("ascii")
    confValue= base64.b64encode(message_bytes)

    ldifMod = """dn: %s
changetype: modify
replace: %s 
%s:: %s
""" % (configDN, confLDAPAttr, confLDAPAttr, repr(confValue)[2:-1])

    writeFile(ldifMod, fn_mod)

    proceed = 'y'
    if not forceToProceed: 
        proceed = input("Proceed with update? [N|y] ")

    if proceed.lower()[0] == "y":
        cmd = [ldapmodify_cmd,
           network_args,
           bind_args % fn_pw,
           "-f %s" % fn_mod]
        os.system(" ".join(cmd))
        os.remove(fn_mod)
        os.remove(fn_search)
    if del_pw:
        os.remove(fn_pw)

if __name__ == "__main__":
    main()

