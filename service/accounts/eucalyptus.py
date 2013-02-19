"""
UserManager:
  Remote Eucalyptus Admin controls..

User, BooleanField, StringList
  These XML parsing classes belong to euca_admin.py, and can be found on the Cloud Controller
TODO: Remove keys and add this to github, people using eucalyptus will appreciate it.
"""
from django.contrib.auth.models import User

from atmosphere import settings
from atmosphere.logger import logger
from core.models.euca_key import Euca_Key
from core.models.identity import Identity
from core.models.group import Group, IdentityMembership, ProviderMembership
from core.models.provider import Provider 
from core.models.credential import Credential
from core.models.quota import Quota
from service.drivers.eucalyptusUserManager import UserManager

class AccountDriver():
    user_manager = None
    euca_prov = None

    def __init__(self):
        self.user_manager = UserManager()
        self.euca_prov = Provider.objects.get(location='EUCALYPTUS')

    def add_user(self, username) :
        userCreated = self.user_manager.add_user(username)
        if not userCreated:
            return None
        user = self.user_manager.get_user(username)
        return user

    def delete_user(self, username) :
        userDeleted = self.user_manager.delete_user(username)
        return userDeleted

    def create_key(self, user_dict):
        try:
            return Euca_Key.objects.get(username=user_dict['username'])
        except Euca_Key.DoesNotExist, dne:
            return Euca_Key.objects.create(\
                    username=user_dict['username'],\
                    ec2_access_key=user_dict['access_key'],\
                    ec2_secret_key=user_dict['secret_key'],\
                    ec2_url=settings.EUCA_EC2_URL,\
                    s3_url=''\
                    )
        except Euca_Key.MultipleObjectsReturned, mor:
            #Delete all objects matching this user
            Euca_Key.objects.filter(username=user_dict['username']).delete()
            return Euca_Key.objects.create(\
                    username=user_dict['username'],\
                    ec2_access_key=user_dict['access_key'],\
                    ec2_secret_key=user_dict['secret_key'],\
                    ec2_url=settings.EUCA_EC2_URL,\
                    s3_url=''\
                    )
    def create_identity(self, user_dict):
        try:
            return IdentityMembership.objects.get(identity__provider=self.euca_prov, member__name=user_dict['username'], identity__created_by__username=user_dict['username'])
        except IdentityMembership.DoesNotExist as dne:
            #Create one
            logger.info(user_dict)
            user = User.objects.get_or_create(username=user_dict['username'])[0]
            group = Group.objects.get_or_create(name=user_dict['username'])[0]
            #Do we only need one?
            user.groups.add(group)
            user.save()
            #Build std quota
            default_quota = Quota().defaults()
            std_quota = Quota.objects.filter(cpu=default_quota['cpu'], memory=default_quota['memory'], storage=default_quota['storage'])[0]
            group.leaders.add(user)
            #Create the Identity
            identity = Identity.objects.get_or_create(created_by=user, provider=self.euca_prov)[0] #Build & Save
            key_cred = Credential.objects.get_or_create(identity=identity, key='key', value=user_dict['access_key'])[0]
            sec_cred = Credential.objects.get_or_create(identity=identity, key='secret', value=user_dict['secret_key'])[0]
            #Link it to the usergroup
            id_member = IdentityMembership.objects.get_or_create(identity=identity, member=group, quota=std_quota)[0]
            prov_member = ProviderMembership.objects.get_or_create(provider=self.euca_prov, member=group)[0]
            #Return the identity
            return identity
        except Identity.MultipleObjectsReturned as mult:
            #Handle multiple identities created by user (Should this be allowed?)
            identities = Identity.objects.filter(created_by__username=user_dict['username'])
            logger.info("%s has multiple identities: %s" % (user_dict['username'], identities))
            return identities[0]

    def get_key(self, user):
        return self.user_manager.get_key(user)

    def get_keys(self, userList):
        return self.user_manager.get_keys(userList)

    def get_user(self, user):
        return self.user_manager.get_user(user)

    def get_users(self, userList):
        return self.user_manager.get_users(userList)

    def list_users(self):
        return self.user_manager.get_all_users()
