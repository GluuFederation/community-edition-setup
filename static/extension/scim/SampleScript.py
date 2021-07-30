# Visit https://www.gluu.org/docs/gluu-server/user-management/scim-scripting/ to learn more
from org.gluu.model.custom.script.type.scim import ScimType

import java

class ScimEventHandler(ScimType):

    def __init__(self, currentTimeMillis):
        self.currentTimeMillis = currentTimeMillis

    def init(self, configurationAttributes):
        print "ScimEventHandler (init): Initialized successfully"
        return True   

    def destroy(self, configurationAttributes):
        print "ScimEventHandler (destroy): Destroyed successfully"
        return True   

    def getApiVersion(self):
        return 5

    def createUser(self, user, configurationAttributes):
        return True

    def updateUser(self, user, configurationAttributes):
        return True

    def deleteUser(self, user, configurationAttributes):
        return True

    def createGroup(self, group, configurationAttributes):
        return True

    def updateGroup(self, group, configurationAttributes):
        return True

    def deleteGroup(self, group, configurationAttributes):
        return True
        
    def postCreateUser(self, user, configurationAttributes):
        return True

    def postUpdateUser(self, user, configurationAttributes):
        return True

    def postDeleteUser(self, user, configurationAttributes):
        return True

    def postUpdateGroup(self, group, configurationAttributes):
        return True

    def postCreateGroup(self, group, configurationAttributes):
        return True

    def postDeleteGroup(self, group, configurationAttributes):
        return True
    
    def getUser(self, user, configurationAttributes):
        return True
    
    def getGroup(self, group, configurationAttributes):
        return True
        
    def postSearchUsers(self, results, configurationAttributes):
        # Warning: postSearchUsers is a misnomer. This gets actually executed before the 
        # SCIM search operation is serialized, so modifications on results variable will
        # take effect on the output of the API call
        return True

    def postSearchGroups(self, results, configurationAttributes):
        # Warning: postSearchGroups is a misnomer. This gets actually executed before the 
        # SCIM search operation is serialized, so modifications on results variable will
        # take effect on the output of the API call
        return True
        
    def allowResourceOperation(self, context, entity, configurationAttributes):
        return True 
    
    def allowSearchOperation(self, context, configurationAttributes):
        return ""
    
    def rejectedResourceOperationResponse(self, context, entity, configurationAttributes):
        return None       
    
    def rejectedSearchOperationResponse(self, context, configurationAttributes):
        return None
