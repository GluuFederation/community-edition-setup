# oxShibboleth is available under the MIT License (2008). See http://opensource.org/licenses/MIT for full text.
# Copyright (c) 2020, Gluu
#
# Author: Yuriy Movchan
#

from org.gluu.model.custom.script.type.idp import IdpType
from org.gluu.util import StringHelper
from org.gluu.idp.externalauth import AuthenticatedNameTranslator
from net.shibboleth.idp.authn.principal import UsernamePrincipal, IdPAttributePrincipal
from net.shibboleth.idp.authn import ExternalAuthentication
from net.shibboleth.idp.attribute import IdPAttribute, StringAttributeValue
from net.shibboleth.idp.authn.context import AuthenticationContext, ExternalAuthenticationContext
from net.shibboleth.idp.attribute.context import AttributeContext
from javax.security.auth import Subject
from java.util import Collections, HashMap, HashSet, ArrayList, Arrays

import java

class IdpExtension(IdpType):

    def __init__(self, currentTimeMillis):
        self.currentTimeMillis = currentTimeMillis

    def init(self, customScript, configurationAttributes):
        print "Idp extension. Initialization"
        
        self.defaultNameTranslator = AuthenticatedNameTranslator()
        
        return True

    def destroy(self, configurationAttributes):
        print "Idp extension. Destroy"
        return True

    def getApiVersion(self):
        return 11

    # Translate attributes from user profile
    #   context is org.gluu.idp.externalauth.TranslateAttributesContext (https://github.com/GluuFederation/shib-oxauth-authn3/blob/master/src/main/java/org/gluu/idp/externalauth/TranslateAttributesContext.java)
    #   configurationAttributes is java.util.Map<String, SimpleCustomProperty>
    def translateAttributes(self, context, configurationAttributes):
        print "Idp extension. Method: translateAttributes"
        userProfile = context.getUserProfile()
        if userProfile is None:
           print "No valid user profile could be found to translate"
           return False
          
        if userProfile.getId() is None:
           print "No valid user principal could be found to traslate"
           return False
        
        self.defaultNameTranslator.populateIdpAttributeList(userProfile.getAttributes(),context)
        
        #Return True to specify that default method is not needed
        return True

    # Update attributes before releasing them
    #   context is org.gluu.idp.consent.processor.PostProcessAttributesContext (https://github.com/GluuFederation/shib-oxauth-authn3/blob/master/src/main/java/org/gluu/idp/consent/processor/PostProcessAttributesContext.java)
    #   configurationAttributes is java.util.Map<String, SimpleCustomProperty>
    def updateAttributes(self, context, configurationAttributes):
        print "Idp extension. Method: updateAttributes"
        # Uncomment this line to remove the uid attribute , if it exists
        #context.getIdpAttributeMap().remove("uid")
        return True
