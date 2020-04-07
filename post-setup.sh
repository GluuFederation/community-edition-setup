#!/bin/sh

echo "Connecting plugs: block-devices, mount-observe, system-observe, network-observe"

snap connect gluu-server:block-devices :block-devices
snap connect gluu-server:mount-observe :mount-observe
snap connect gluu-server:system-observe :system-observe
snap connect gluu-server:network-observe :network-observe

echo "Setting ulimits"

apache_user="daemon"
jetty_user="root"
ldap_user="root"
limits_fn="/etc/security/limits.conf"

echo "$ldap_user       soft nofile     131072" >> $limits_fn
echo "$ldap_user       hard nofile     262144" >> $limits_fn
echo "$apache_user     soft nofile     131072" >> $limits_fn
echo "$apache_user     hard nofile     262144" >> $limits_fn
echo "$jetty_user      soft nofile     131072" >> $limits_fn
echo "$jetty_user      hard nofile     262144" >> $limits_fn


