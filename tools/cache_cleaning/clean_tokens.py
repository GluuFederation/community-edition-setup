#!/usr/bin/python3

import os
import sys
import time
import datetime
import argparse
import ldap3
import logging
from logging.handlers import RotatingFileHandler

cur_dir = os.path.dirname(os.path.realpath(__file__))

parser = argparse.ArgumentParser(description="Gluu Server couchbase cache cleanup script")
parser.add_argument('-ldap_host', help="LDAP hostname or IP address", default='localhost')
parser.add_argument('-ldap_bind_dn', help="LDAP bind dn", default='cn=Directory Manager')
parser.add_argument('-ldap_bind_pw', help="Password for LDAP bind dn")
parser.add_argument('-log_dir', help="Password for LDAP bind dn", default=cur_dir)

argsp = parser.parse_args()

offset = 0

if not os.path.exists(argsp.log_dir):
    os.makedirs(argsp.log_dir)

logging.basicConfig(
  handlers=[
    RotatingFileHandler(
      os.path.join(argsp.log_dir, 'cache_clean.log'),
      maxBytes=10*1024*1025,
      backupCount=10
    )
  ],
  level=logging.INFO,
  format='%(asctime)s %(levelname)s - %(message)s'
)


def get_ldap_time_format(dt):
    return  '{}{:02d}{:02d}{:02d}{:02d}{:02d}.{}Z'.format(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, str(dt.microsecond)[:3])


ldap_host =  argsp.ldap_host
ldap_bind_dn = argsp.ldap_bind_dn
ldap_bind_pw = argsp.ldap_bind_pw
paged_size = 1000

ldap_server = ldap3.Server('ldaps://{}:1636'.format(ldap_host), use_ssl=True)
ldap_conn = ldap3.Connection(ldap_server, user=ldap_bind_dn, password=ldap_bind_pw)
ldap_conn.bind()


utc_now = datetime.datetime.utcnow()
cur_time = get_ldap_time_format(utc_now + datetime.timedelta(seconds=offset))

search_filter = '(&(exp<={0})(del=true))'.format(cur_time)

base_dn = [
        'ou=tokens,o=gluu',
        'ou=uma,o=gluu',
        'ou=clients,o=gluu',
        'ou=authorizations,o=gluu',
        'ou=scopes,o=gluu',
        'ou=metric,o=gluu',
        'ou=sessions,o=gluu',
        ]

def delete_cache(i, dn):
    logging.info("#%d Deleting DN %s", i, dn)
    ldap_conn.delete(dn)

for base in base_dn:

    logging.info("Searching expired cache entries for base %s", base)

    retreive_attributes = ['exp']
    if base == 'ou=tokens,o=gluu':
        retreive_attributes.append('ssnId')

    ldap_conn.search(search_base = base,
             search_filter = search_filter,
             search_scope = ldap3.SUBTREE,
             attributes = retreive_attributes,
             paged_size = paged_size)

    print ("ldap_conn.result is of type {} and has value {}".format(type(ldap_conn.result),ldap_conn.result))
    cookie = ldap_conn.result['controls']['1.2.840.113556.1.4.319']['value']['cookie']

    entry_count = len(ldap_conn.response)
    total_entries = entry_count
    logging.info("Reteived %d entries for base %s", entry_count, base)
    for i, entry in enumerate(ldap_conn.response):
        delete_cache(i, entry['dn'])
        if (base == 'ou=tokens,o=gluu' and entry['attributes']['ssnId']):
            delete_cache(i, entry['attributes']['ssnId'][0])

    while cookie:
        ldap_conn.search(search_base = base,
                 search_filter = search_filter,
                 search_scope = ldap3.SUBTREE,
                 attributes = retreive_attributes,
                 paged_size = paged_size,
                 paged_cookie = cookie)
        entry_count = len(ldap_conn.response)
        total_entries += entry_count
        logging.info("Reteived %d entries for base %s", entry_count, base)
        cookie = ldap_conn.result['controls']['1.2.840.113556.1.4.319']['value']['cookie']
        for i, entry in enumerate(ldap_conn.response):
            delete_cache(i, entry['dn'])
            if (base == 'ou=tokens,o=gluu' and entry['attributes']['ssnId']):
                delete_cache(i, entry['attributes']['ssnId'][0])

    logging.info("Deleted %d entries for base %s", total_entries, base)

