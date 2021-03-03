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

def mod(ldapobj, dn, modlist, logger=None):
    '''Perform LDAP synchronous mod operation.'''
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
            self.err = {'desc': "Can't start the forced update in the replica."}
        if action == 'disable':
            self.err = {'desc': "Can't stop the forced update in the replica."}
        super().__init__(self.err)

def send_update_now(conn_supplier, consumer_replDN, waitSeconds, instance=None, baseDN=None, supplier=None, consumer=None, logger=None):
    # "send update now" for non-always in synch replica
    if consumer_replDN is not None:
        switch_on  = [( ldap.MOD_ADD,    'nsDS5ReplicaUpdateSchedule', b'*' )]
        switch_off = [( ldap.MOD_DELETE, 'nsDS5ReplicaUpdateSchedule', b'*' )]
        try:

            mod(conn_supplier,consumer_replDN,switch_on,logger)
            if logger:
                logger.info('instance="{}" baseDN="{}" supplier={} consumer={} action="force update" status=success'.format(instance, baseDN, supplier, consumer))
        except Exception as err:
            if logger:
                logger.error('instance="{}" baseDN="{}" supplier={} consumer={} action="force update" status=fail {}'
                    .format(instance, baseDN, supplier, consumer, handle_log(err)))
            raise sunError('enable')
        try:
            mod(conn_supplier,consumer_replDN,switch_off,logger)
            if logger:
                logger.info('instance="{}" baseDN="{}" supplier={} consumer={} action="stop force update" status=success'.format(instance, baseDN, supplier, consumer))
        except ldap.LDAPError as err:
            if logger:
                logger.error('instance="{}" baseDN="{}" supplier={} consumer={} action="stop force update" status=fail {}'
                    .format(instance, baseDN, supplier, consumer, handle_log(err)))
            raise sunError('disable')
        time.sleep(waitSeconds)


def time_to_notify(directoryInstances,netTimeout, sleepTime, UPDATE_sleepTime):
    ''' Calculate a time in order to tell systemd to wait until end of checks '''
    waiting = 0
    for instance in directoryInstances:
        for basedn in directoryInstances[instance]:
            for supplier in directoryInstances[instance][basedn]:
                waiting += netTimeout + 2*sleepTime
                for consumer in directoryInstances[instance][basedn][supplier]['replica']:
                    waiting += netTimeout
                    for consumer_host, consumer_repl in consumer.items():
                        if consumer_repl is not None:
                            waiting += UPDATE_sleepTime*2
    return waiting

def replTest(directoryInstances, rDN, testEntry, netTimeout, sleepTime, UPDATE_sleepTime, logger):
    someError = False
    ''' Initialize the RESULT Dictionary '''
    RESULT = {}

    for instance in directoryInstances:
        RESULT[instance] = {}
        print (instance)
        for basedn in directoryInstances[instance]:
            print("\t{}".format(basedn))
            entryDN = "{}={},{}".format(rDN, testEntry[rDN].decode('utf-8'), basedn)
            RESULT[instance][basedn] = {}
            for supplier in directoryInstances[instance][basedn]:
                RESULT[instance][basedn][supplier] = {}
                RESULT[instance][basedn][supplier]['replica'] = {}
                # Connect to the Supplier
                print("\t\tWorking on supplier {}".format(supplier))
                supplier_uri = "{}://{}:{}".format(directoryInstances[instance][basedn][supplier]['protocol'], supplier,
                                                   directoryInstances[instance][basedn][supplier]['port'])
                try:
                    connS = connect(supplier_uri,
                                    directoryInstances[instance][basedn][supplier]['bind'],
                                    directoryInstances[instance][basedn][supplier]['pwd'], netTimeout, logger)
                    logger.info('instance="{}" baseDN="{}" host={} action=connect status=success'.format(instance, basedn, supplier))
                except ldap.LDAPError as err:
                    logger.error('instance="{}" baseDN="{}" host={} action=connect status=fail {}'
                              .format(instance, basedn, supplier, handle_log(err)))
                    RESULT[instance][basedn][supplier]['status'] = False
                    someError = True
                    logger.fatal('instance="{}" baseDN="{}" supplier={} action=validate status=fail detail="{}"'
                              .format(instance, basedn, supplier, "Can't connect"))
                    continue
                except:
                    print("\n\n Unhandled exception!! \n\n")
                    logger.fatal('instance="{}" baseDN="{}" host={} action=connect status=fail error="unhandled exception"'
                              .format(instance, basedn, supplier))
                    raise


                # Garbage collection: we delete the test testEntry if already existent
                # for some reason
                try:
                    nentries = search(connS, entryDN, ldap.SCOPE_BASE, 'objectclass=*')
                    logger.info('instance="{}" baseDN="{}" host={} action="garbage search" status=success detail="{} entries found"'.format(instance, basedn, supplier, nentries))
                except ldap.LDAPError as err:
                    nentries = 0
                    someError = True
                    logger.error('instance="{}" baseDN="{}" host={} action="garbage search" status=fail {}'
                              .format(instance, basedn, supplier, handle_log(err)))

                if nentries == 1:
                    try:
                        delete(connS, entryDN, logger)
                        logger.info('instance="{}" baseDN="{}" host={} action=garbage status=success'.format(instance, basedn, supplier))
                    except ldap.NO_SUCH_OBJECT:
                        logger.info('instance="{}" baseDN="{}" host={} action=garbage status=success detail="No such object"'
                                 .format(instance, basedn, supplier))
                    except ldap.LDAPError as err:
                        logger.error('instance="{}" baseDN="{}" host={} action=garbage status=fail {}'
                                  .format(instance, basedn, supplier, handle_log(err)))

                if nentries > 1:
                    logger.fatal('instance="{}" baseDN="{}" host={} action=garbage status=fail detail="{} entries found. Expected 1."'.format(instance, basedn, supplier, nentries))
                    sys.exit(255)


                # Add to the Supplier
                try:
                    add(connS, entryDN, testEntry, logger)
                    logger.info('instance="{}" baseDN="{}" host={} action=write status=success'.format(instance, basedn, supplier))
                except ldap.LDAPError as err:
                    logger.error('instance="{}" baseDN="{}" host={} action=write status=fail {}'
                              .format(instance, basedn, supplier, handle_log(err)))
                    logger.fatal('instance="{}" baseDN="{}" supplier={} action=validate status=fail detail="{}"'
                              .format(instance, basedn, supplier, "Can't add to the supplier"))
                    RESULT[instance][basedn][supplier]['status'] = False
                    someError= True

                # Wait to allow replica propagation among consumers
                time.sleep(sleepTime)
                # Check the testEntry replica on Consumers
                for consumer in directoryInstances[instance][basedn][supplier]['replica']:
                    for consumer_host, consumer_repl in consumer.items():
                        # "send update now" for non-always in synch replica
                        try:
                            send_update_now(connS, consumer_repl, UPDATE_sleepTime, instance, basedn, supplier, consumer_host, logger)
                        except sunError as err:
                            RESULT[instance][basedn][supplier]['replica'][consumer_host] = False
                            someError= True
                            logger.fatal('instance="{}" baseDN="{}" supplier={} consumer={} action=validate status=fail {}'
                                    .format(instance, basedn, supplier, consumer_host, handle_log(err)))
                            continue
                        # Check if the replica has completed as well
                        #  Connect on consumer
                        consumer_uri = "{}://{}:{}".format(directoryInstances[instance][basedn][supplier]['protocol'], consumer_host,
                                                           directoryInstances[instance][basedn][supplier]['port'])
                        try:
                            connC = connect(consumer_uri,
                                    directoryInstances[instance][basedn][supplier]['bind'],
                                    directoryInstances[instance][basedn][supplier]['pwd'], netTimeout, logger)
                            logger.info('instance="{}" baseDN="{}" host={} action=connect status=success'.format(instance, basedn, consumer_host))
                        except ldap.LDAPError as err:
                            logger.error('instance="{}" baseDN="{}" host={} action=connect status=fail {}'
                                      .format(instance, basedn, consumer_host, handle_log(err)))
                            RESULT[instance][basedn][supplier]['replica'][consumer_host] = False
                            someError = True
                            logger.fatal('instance="{}" baseDN="{}" consumer={} action=validate status=fail detail="{}"'
                                      .format(instance, basedn, consumer_host, "Can't connect"))
                            continue
                        except:
                            print("\n\n Unhandled exception!! \n\n")
                            logger.fatal('instance="{}" baseDN="{}" host={} action=connect status=fail error="unhandled exception"'
                                      .format(instance, basedn, consumer_host))
                            raise
                            sys.exit(255)
                        #  Search on the consumer
                        nentries = None
                        try:
                            nentries = search(connC, entryDN, ldap.SCOPE_BASE, 'objectclass=*')
                            logger.info('instance="{}" baseDN="{}" host={} action=search status=success'.format(instance, basedn, consumer_host))
                        except ldap.LDAPError as err:
                            logger.error('instance="{}" baseDN="{}" host={} action=search status=fail {}'
                                      .format(instance, basedn, consumer_host, handle_log(err)))
                            RESULT[instance][basedn][supplier]['replica'][consumer_host] = False
                            someError = True
                        if nentries == 1:
                            logger.info('instance="{}" baseDN="{}" supplier={} consumer={} action=validate status=success'
                                     .format(instance, basedn, supplier, consumer_host))
                            RESULT[instance][basedn][supplier]['replica'][consumer_host] = True
                        else:
                            logger.error('instance="{}" baseDN="{}" supplier={} consumer={} action=validate status=fail detail="{} entries found. Expected 1"'
                                     .format(instance, basedn, supplier, consumer_host, nentries))
                            RESULT[instance][basedn][supplier]['replica'][consumer_host] = False
                            someError = True
                        # Unbind from consumer
                        try:
                            connC.unbind_s()
                            logger.info('instance="{}" baseDN="{}" host={} action=disconnect status=success'.format(instance, basedn, consumer_host))
                        except:
                            logger.error('instance="{}" baseDN="{}" host={} action=disconnect status=fail'.format(instance, basedn, consumer_host))
                            someError = True


                # Delete the testEntry from the Supplier
                try:
                    delete(connS, entryDN, logger)
                    logger.info('instance="{}" baseDN="{}" host={} action=delete status=success'.format(instance, basedn, supplier))
                    logger.info('instance="{}" baseDN="{}" supplier={} action=validate status=success'
                             .format(instance, basedn, supplier))
                    RESULT[instance][basedn][supplier]['status'] = True
                except ldap.LDAPError as err:
                    logger.error('instance="{}" baseDN="{}" host={} action=delete status=fail {}'
                              .format(instance, basedn, supplier, handle_log(err)))
                    RESULT[instance][basedn][supplier]['status'] = False
                    someError = True
                    logger.fatal('instance="{}" baseDN="{}" supplier={} action=validate status=fail detail="{}"'
                              .format(instance, basedn, supplier, "Can't delete"))
                except ldap.NO_SUCH_OBJECT:
                    logger.error('instance="{}" baseDN="{}" host={} action=delete status=fail error="No such object"'
                              .format(instance, basedn, supplier))
                    RESULT[instance][basedn][supplier]['status'] = False
                    someError = True
                    logger.fatal('instance="{}" baseDN="{}" supplier={} action=validate status=fail detail="{}"'
                              .format(instance, basedn, supplier, "Can't delete. Deleted already? Unexpected."))

                # If the replica isn't always in synch, try to send update now
                for consumer in directoryInstances[instance][basedn][supplier]['replica']:
                    for consumer_host, consumer_repl in consumer.items():
                        # "send update now" for non-always in synch replica
                        try:
                            send_update_now(connS, consumer_repl, UPDATE_sleepTime, instance, basedn, supplier, consumer_host, logger)
                        except sunError as err:
                            someError= True

                # Unbind from Supplier
                try:
                    connS.unbind_s()
                    logger.info('instance="{}" baseDN="{}" host={} action=disconnect status=success'.format(instance, basedn, supplier))
                except:
                    logger.error('instance="{}" baseDN="{}" host={} action=disconnect status=fail'.format(instance, basedn, supplier))
                    someError = True
                time.sleep(sleepTime)

    return RESULT, someError
