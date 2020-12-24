import ldap
import ldap.modlist
import sys
import time

def handle_log(excpt):
    '''
    A brief utility to compose structural log fields
    from ldap.LDAPError exceptions.
        excpt - ldap.LDAPError object

    This functions returns a string suitable for a
    syslog record.
    '''
    fields = ''
    if 'desc' in excpt.args[0]:
        fields = 'error="{}"'.format(excpt.args[0]['desc'].replace("\"","'").rstrip())
    if 'info' in excpt.args[0]:
        fields = fields + ' detail="{}"'.format(excpt.args[0]['info'].replace("\"","'").rstrip())
    return fields

def connect(ldapuri, binddn="", bindpw="", timeout=None, logger=None):
  """
  Perform LDAP connection and synchronous simple bind operation
    ldapuri - URI referring to the LDAP server (string)
    binddn - Distinguished Name used to bind (string)
    logger - Logger object instance

  This function returns an LDAPobject instance if successful,
  None if failure
  """

  # Set debugging level
  ldap.set_option(ldap.OPT_DEBUG_LEVEL, 0)
  ldap.set_option(ldap.OPT_NETWORK_TIMEOUT, timeout)
  ldap_trace_level = 0    # If non-zero a trace output of LDAP calls is generated.
  ldap_trace_file = sys.stderr

  # Create LDAPObject instance
  if logger: logger.debug("Connecting to {}".format(ldapuri))
  conn = ldap.initialize(ldapuri,
                         trace_level=ldap_trace_level,
                         trace_file=ldap_trace_file)

  # Set LDAP protocol version used
  if logger: logger.debug("LDAP protocol version 3")
  conn.protocol_version=ldap.VERSION3

  # Perform synchronous simple bind operation
  if binddn:
    password = bindpw
    if logger: logger.debug("Binding with {}".format(binddn))
  else:
    if logger: logger.debug("Binding anonymously")
    password = "";
  try:
    conn.bind_s(binddn, password, ldap.AUTH_SIMPLE)
    return conn
  except ldap.LDAPError as err:
    if logger and 'desc' in err.args[0]: logger.error("LDAP bind failed. {}".format(err.args[0]['desc']))
    raise
    return None

def search(ldapobj, baseDN, scope, filter):
  """
  Perform LDAP synchronous search operation
    ldapobj - LDAP object instance
    baseDN - LDAP base dn (string)
    scope - LDAP search scope (integer)
    filter - LDAP filter (string)

  This function returns the number of entries found.
  """
  try:
      return len(ldapobj.search_s(baseDN, scope, filter))
  except ldap.NO_SUCH_OBJECT:
      return 0

def add(ldapobj, dn, ldif, logger=None):
  modlist = ldap.modlist.addModlist(ldif)
  try:
      ldapobj.add_s(dn, modlist)
      return True
  except ldap.ALREADY_EXISTS:
      if logger: logger.debug("Can't add. The dn <{}> already exists.".format(dn))
      raise
      return False
  except ldap.LDAPError as err:
      if logger and 'desc' in err.args[0]: logger.debug("Can't add the dn <{}>. Error: {}".format(dn, err.args[0]['desc']))
      raise
      return False

def delete(ldapobj, dn, logger=None):
  '''Perform LDAP synchronous del operation.'''
  try:
      ldapobj.delete_s(dn)
      return True
  except ldap.NO_SUCH_OBJECT:
      if logger: logger.error("Can't delete. The dn <{}> doesn't exist.".format(dn))
      raise
      return False
  except ldap.LDAPError as err:
      if logger and 'desc' in err.args[0]: logger.debug("Can't delete the dn <{}>. Error: {}".format(dn, err.args[0]['desc']))
      raise
      return False

def mod(ldapobj, dn, old, new, logger=None):
    '''Perform LDAP synchronous mod operation.'''
    modlist = ldap.modlist.modifyModlist(old, new)
    try:
        ldapobj.modify_s(dn, modlist)
        return True
    except ldap.LDAPError as err:
        if logger and 'desc' in err.args[0]: logger.debug("Can't modify the dn <{}>. Error: {}".format(dn, err.args[0]['desc']))
        raise
        return False


class sunError(Exception):
    def __init__(self, action):
        self.action = action
        if action == 'enable':
            self.err = {'desc': "Can't re-enable the replica"}
        if action == 'disable':
            self.err = {'desc': "Can't disable the replica"}
        super().__init__(self.err)

def send_update_now(conn_supplier, consumer_replDN, waitSeconds, instance=None, baseDN=None, supplier=None, consumer=None, logger=None):
    # "send update now" for non-always in synch replica
    if consumer_replDN is not None:
        switch_on  = {'nsds5ReplicaEnabled': [b'on']}
        switch_off = {'nsds5ReplicaEnabled': [b'off']}
        try:
            mod(conn_supplier,consumer_replDN,switch_on,switch_off,logger)
            if logger:
                logger.info('instance="{}" baseDN="{}" supplier={} consumer={} action="disable replica" status=success'.format(instance, baseDN, supplier, consumer))
        except Exception as err:
            if logger:
                logger.error('instance="{}" baseDN="{}" supplier={} consumer={} action="disable replica" status=fail {}'
                    .format(instance, baseDN, supplier, consumer, handle_log(err)))
            raise sunError('disable')
        try:
            mod(conn_supplier,consumer_replDN,switch_off,switch_on,logger)
            if logger:
                logger.info('instance="{}" baseDN="{}" supplier={} consumer={} action="enable replica" status=success'.format(instance, baseDN, supplier, consumer))
        except ldap.LDAPError as err:
            if logger:
                logger.error('instance="{}" baseDN="{}" supplier={} consumer={} action="enable replica" status=fail {}'
                    .format(instance, baseDN, supplier, consumer, handle_log(err)))
            raise sunError('enable')
        time.sleep(waitSeconds)
