#!/usr/bin/env python
from django.contrib.auth.models import User

from atmosphere import settings

from service.accounts.eucalyptus import AccountDriver as EucaAccountDriver
from service.accounts.openstack import AccountDriver as OSAccountDriver

from novaclient.exceptions import OverLimit
def main():
    euca_driver = EucaAccountDriver()
    os_driver = OSAccountDriver()
    found = 0
    create = 0

    core_services = ['admin','esteve','jmatt','cjlarose','mlent','edwins']
    #core_services += ['nirav','smckay','dgessler','vaughn','steinj']
    for user in core_services:
        #Get the user from Euca DB
        user_dict = euca_driver.get_user(user)
        #Create a euca account/identity
        create_euca_account(euca_driver, user_dict)
        #Then add the Openstack Identity
        create_os_account(os_driver, user, True)
        make_admin(user)
    print "Total core-service/admins added:%s" % len(core_services)

    #all_users = euca_driver.list_users()
    #for user_dict in all_users.values():
    #    create_euca_account(euca_driver, user_dict)
    #    #create_os_account(os_driver, user_dict['username'])
    #print "Total users added:%s" % len(all_users)

def make_admin(user):
    u = User.objects.get(username=user)
    u.is_superuser = True
    u.is_staff = True
    u.save()

def create_euca_account(euca_driver, user_dict):
    key = euca_driver.create_key(user_dict)
    id = euca_driver.create_identity(user_dict)
    return id

def create_os_account(os_driver, username, admin_role=False):
    finished = False
    #Special case for admin.. Use the Openstack admin identity..
    if username == 'admin':
        ident = os_driver.create_openstack_identity(settings.OPENSTACK_ADMIN_KEY, settings.OPENSTACK_ADMIN_SECRET, settings.OPENSTACK_ADMIN_TENANT)
        return ident
    while not finished:
        try:
            password = os_driver.hashpass(username)
            user = os_driver.get_user(username)
            if not user:
                (username, password) = os_driver.create_user(username, True, admin_role)
            finished = True
        except OverLimit:
            print 'Requests are rate limited. Pausing for one minute.'
            time.sleep(60) #Wait one minute
    ident = os_driver.create_openstack_identity(username, password, tenant_name=username)
    return ident

if __name__ == "__main__":
    main()
