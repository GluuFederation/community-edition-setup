# oxAuth is available under the MIT License (2008). See http://opensource.org/licenses/MIT for full text.
# Copyright (c) 2016, Gluu
#
# Author: Yuriy Movchan
#

from org.gluu.model.custom.script.type.user import CacheRefreshType
from org.gluu.util import StringHelper, ArrayHelper
from java.util import Arrays, ArrayList
from org.gluu.oxtrust.model import GluuCustomAttribute
from org.gluu.model.custom.script.model.bind import BindCredentials

import java

class CacheRefresh(CacheRefreshType):
    def __init__(self, currentTimeMillis):
        self.currentTimeMillis = currentTimeMillis

    def init(self, customScript, configurationAttributes):
        print "Cache refresh. Initialization"
        print "Cache refresh. Initialized successfully"

        return True   

    def destroy(self, configurationAttributes):
        print "Cache refresh. Destroy"
        print "Cache refresh. Destroyed successfully"
        return True

    # Check if this instance conform starting conditions 
    #   configurationAttributes is java.util.Map<String, SimpleCustomProperty>
    #   return True/False
    def isStartProcess(self, configurationAttributes):
        print "Cache refresh. Is start process method"

        return False
    
    # Get bind credentials required to access source server 
    #   configId is the source server
    #   configurationAttributes is java.util.Map<String, SimpleCustomProperty>
    #   return None (use password from configuration) or org.gluu.model.custom.script.model.bind.BindCredentials
    def getBindCredentials(self, configId, configurationAttributes):
        print "Cache refresh. GetBindCredentials method"
#        if configId == "source":
#            return BindCredentials("cn=Directory Manager", "password")

        return None

    # Update user entry before persist it
    #   user is org.gluu.oxtrust.model.GluuCustomPerson
    #   configurationAttributes is java.util.Map<String, SimpleCustomProperty>
    def updateUser(self, user, configurationAttributes):
        print "Cache refresh. UpdateUser method"

        attributes = user.getCustomAttributes()

        # Add new attribute preferredLanguage
        attrPrefferedLanguage = GluuCustomAttribute("preferredLanguage", "en-us")
        attributes.add(attrPrefferedLanguage)

        # Add new attribute userPassword
        attrUserPassword = GluuCustomAttribute("userPassword", "test")
        attributes.add(attrUserPassword)

        # Update givenName attribute
        for attribute in attributes:
            attrName = attribute.getName()
            if (("givenname" == StringHelper.toLowerCase(attrName)) and StringHelper.isNotEmpty(attribute.getValue())):
                attribute.setValue(StringHelper.removeMultipleSpaces(attribute.getValue()) + " (updated)")

        return True

    # Update user entry loaded from source server
    #   user is org.gluu.oxtrust.ldap.cache.model.GluuSimplePerson
    #   configurationAttributes is java.util.Map<String, SimpleCustomProperty>
    def updateSourceUser(self, user, configurationAttributes):
        print "Cache refresh. UpdateUser method"

        attributes = user.getCustomAttributes()
        sourceServer = user.getSourceServerName()
        if StringHelper.equals(sourceServer, "ad1"):
            # Add new attribute preferredLanguage
            attrPrefferedLanguage = GluuCustomAttribute("preferredLanguage", "en-us")
            attributes.add(attrPrefferedLanguage)
        else if StringHelper.equals(sourceServer, "ad2"):
            # Add new attribute preferredLanguage
            attrPrefferedLanguage = GluuCustomAttribute("preferredLanguage", "en-gb")
            attributes.add(attrPrefferedLanguage)

        return True

    def getApiVersion(self):
        return 11
