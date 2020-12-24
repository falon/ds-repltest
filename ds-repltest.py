#!/usr/bin/env python3
import logging
import logging.handlers
import os
import time
import sys
import ldap
from flask import Flask, render_template, url_for
from datetime import datetime
import lib.ldap as myldap
import lib.common as setting


'''
Read Config
'''
# get the config from FHS conform dir
CONFIG = os.path.join(os.path.dirname("/etc/ds-repltest/"), "ds-repltest.conf")
if not os.path.isfile(CONFIG):
    # developing stage
    CONFIG = os.path.join(os.path.dirname(__file__), "etc/ds-repltest.conf")

if not os.path.isfile(CONFIG):
    # Try to copy dist file in first config file
    distconf = os.path.join(os.path.dirname(CONFIG), "ds-repltest.conf-dist")
    if os.path.isfile(distconf):
        print("First run? I don't find <ds-repltest.conf>, but <ds-repltest.conf-dist> exists. I try to rename it.")
        os.rename(distconf, os.path.join(os.path.dirname(distconf), "ds-repltest.conf"))

# get the configuration items
if os.path.isfile(CONFIG):
    logging_parameters =  setting.load_yaml(CONFIG, "Logging")
    LOGFILE_DIR = logging_parameters['LOGFILE_DIR']
    LOGFILE_NAME = logging_parameters['LOGFILE_NAME']
    LOGSTDOUT = logging_parameters['LOGSTDOUT']
    LOGHANDLER = logging_parameters['TYPE']
    SYSLOG_FAC = logging_parameters['SYSLOG_FAC']
    SYSLOG_LEVEL = logging_parameters['LOG_LEVEL']
    SYSLOG_SOCKET = logging_parameters['SYSLOG_SOCKET']

    LDAP_INSTANCES = setting.load_yaml(CONFIG, "INSTANCES")
    ENTRY = setting.load_yaml(CONFIG, "TEST_ENTRY")
    NET_TIMEOUT = setting.load_yaml(CONFIG, "TIMEOUT")
    SLEEPTIME = setting.load_yaml(CONFIG, "TIMEWAIT")
    UPDATE_SLEEPTIME = setting.load_yaml(CONFIG, "UPDATE_TIMEWAIT")
else:
    sys.exit("Please check the config file! Config path: %s.\nHint: put a ds-repltest.conf in /etc/ds-repltest/ path." % CONFIG)
# =============================================================================

# check if all config parameters are present
for confvar in (
        LOGFILE_DIR, LOGFILE_NAME, LOGSTDOUT, LDAP_INSTANCES,
        LOGHANDLER, SYSLOG_FAC, SYSLOG_LEVEL, SYSLOG_SOCKET):
    if confvar is None:
        sys.exit("Please check the config file! Some parameters are missing. This is an YAML syntax file!")


if LOGHANDLER == 'file':
    LOGFILE_PATH = os.path.join(LOGFILE_DIR, LOGFILE_NAME)
    Path(LOGFILE_DIR).mkdir(exist_ok=True)
    Path(LOGFILE_PATH).touch()
else:
    LOGFILE_PATH = False

if not setting.set_log(LOGHANDLER, SYSLOG_SOCKET, SYSLOG_FAC, SYSLOG_LEVEL, LOGSTDOUT, LOGFILE_PATH):
    print("Something wrong in log definition")
    sys.exit(1)

log = logging.getLogger(setting.loggerName)

''' Initialize the RESULT Dictionary '''
RESULT = {}

''' check on ENTRY used for test '''
if ('uid' in ENTRY.keys()):
    rdn = 'uid'
elif ('cn' in ENTRY.keys()):
    rdn = 'cn'
else:
    log.fatal("The rdn of the test entry is not 'cn' or 'uid'")
    sys.exit(255)

''' convert ENTRY in bytes
  This is to avoid to enter the b'string' in the config file
'''
for key, value in ENTRY.items():
    if type(value) == list:
        for i in range(len(value)):
            ENTRY[key][i] = value[i].encode('utf-8')
    else:
        ENTRY[key] = value.encode('utf-8')

''' mod ldif to force the remote replica update, if it's needed. '''
switch_on  = {'nsds5ReplicaEnabled': [b'on']}
switch_off = {'nsds5ReplicaEnabled': [b'off']}

''' MAIN procedure '''
someError = False
for instance in LDAP_INSTANCES:
    RESULT[instance] = {}
    print (instance)
    for basedn in LDAP_INSTANCES[instance]:
        print("\t{}".format(basedn))
        entryDN = "{}={},{}".format(rdn, ENTRY[rdn].decode('utf-8'), basedn)
        RESULT[instance][basedn] = {}
        for supplier in LDAP_INSTANCES[instance][basedn]:
            RESULT[instance][basedn][supplier] = {}
            RESULT[instance][basedn][supplier]['replica'] = {}
            # Connect to the Supplier
            print("\t\tWorking on supplier {}".format(supplier))
            supplier_uri = "{}://{}:{}".format(LDAP_INSTANCES[instance][basedn][supplier]['protocol'], supplier,
                                               LDAP_INSTANCES[instance][basedn][supplier]['port'])
            try:
                connS = myldap.connect(supplier_uri,
                                LDAP_INSTANCES[instance][basedn][supplier]['bind'],
                                LDAP_INSTANCES[instance][basedn][supplier]['pwd'], NET_TIMEOUT, log)
                log.info('instance="{}" baseDN="{}" host={} action=connect status=success'.format(instance, basedn, supplier))
            except ldap.LDAPError as err:
                log.error('instance="{}" baseDN="{}" host={} action=connect status=fail {}'
                          .format(instance, basedn, supplier, myldap.handle_log(err)))
                RESULT[instance][basedn][supplier]['status'] = False
                someError = True
                log.fatal('instance="{}" baseDN="{}" supplier={} action=validate status=fail detail={}'
                          .format(instance, basedn, supplier, "Can't connect"))
                continue
            except:
                print("\n\n Unhandled exception!! \n\n")
                log.fatal('instance="{}" baseDN="{}" host={} action=connect status=fail error="unhandled exception"'
                          .format(instance, basedn, supplier))
                raise


            # Garbage collection: we delete the test ENTRY if already existent
            # for some reason
            try:
                nentries = myldap.search(connS, entryDN, ldap.SCOPE_BASE, 'objectclass=*')
                log.info('instance="{}" baseDN="{}" host={} action="garbage search" status=success detail="{} entries found"'.format(instance, basedn, supplier, nentries))
            except ldap.LDAPError as err:
                nentries = 0
                someError = True
                log.error('instance="{}" baseDN="{}" host={} action="garbage search" status=fail {}'
                          .format(instance, basedn, supplier, myldap.handle_log(err)))

            if nentries == 1:
                try:
                    myldap.delete(connS, entryDN, log)
                    log.info('instance="{}" baseDN="{}" host={} action=garbage status=success'.format(instance, basedn, supplier))
                except ldap.NO_SUCH_OBJECT:
                    log.info('instance="{}" baseDN="{}" host={} action=garbage status=success detail="No such object"'
                             .format(instance, basedn, supplier))
                except ldap.LDAPError as err:
                    log.error('instance="{}" baseDN="{}" host={} action=garbage status=fail {}'
                              .format(instance, basedn, supplier, myldap.handle_log(err)))

            if nentries > 1:
                log.fatal('instance="{}" baseDN="{}" host={} action=garbage status=fail detail="{} entries found. Expected 1."'.format(instance, basedn, supplier, nentries))
                sys.exit(255)


            # Add to the Supplier
            try:
                myldap.add(connS, entryDN, ENTRY, log)
                log.info('instance="{}" baseDN="{}" host={} action=write status=success'.format(instance, basedn, supplier))
            except ldap.LDAPError as err:
                log.error('instance="{}" baseDN="{}" host={} action=write status=fail {}'
                          .format(instance, basedn, supplier, myldap.handle_log(err)))
                log.fatal('instance="{}" baseDN="{}" supplier={} action=validate status=fail detail="{}"'
                          .format(instance, basedn, supplier, "Can't add to the supplier"))
                RESULT[instance][basedn][supplier]['status'] = False
                someError= True

            # Wait to allow replica propagation among consumers
            time.sleep(SLEEPTIME)
            # Check the ENTRY replica on Consumers
            for consumer in LDAP_INSTANCES[instance][basedn][supplier]['replica']:
                for consumer_host, consumer_repl in consumer.items():
                    # "send update now" for non-always in synch replica
                    try:
                        myldap.send_update_now(connS, consumer_repl, UPDATE_SLEEPTIME, instance, basedn, supplier, consumer_host, log)
                    except myldap.sunError as err:
                        RESULT[instance][basedn][supplier]['replica'][consumer_host] = False
                        someError= True
                        log.fatal('instance="{}" baseDN="{}" supplier={} consumer={} action=validate status=fail {}'
                                .format(instance, basedn, supplier, consumer_host, myldap.handle_log(err)))
                        continue
                    # Check if the replica has completed as well
                    #  Connect on consumer
                    consumer_uri = "{}://{}:{}".format(LDAP_INSTANCES[instance][basedn][supplier]['protocol'], consumer_host,
                                                       LDAP_INSTANCES[instance][basedn][supplier]['port'])
                    try:
                        connC = myldap.connect(consumer_uri,
                                LDAP_INSTANCES[instance][basedn][supplier]['bind'],
                                LDAP_INSTANCES[instance][basedn][supplier]['pwd'], NET_TIMEOUT, log)
                        log.info('instance="{}" baseDN="{}" host={} action=connect status=success'.format(instance, basedn, consumer_host))
                    except ldap.LDAPError as err:
                        log.error('instance="{}" baseDN="{}" host={} action=connect status=fail {}'
                                  .format(instance, basedn, consumer_host, myldap.handle_log(err)))
                        RESULT[instance][basedn][supplier]['replica'][consumer_host] = False
                        someError = True
                        log.fatal('instance="{}" baseDN="{}" consumer={} action=validate status=fail detail={}'
                                  .format(instance, basedn, consumer_host, "Can't connect"))
                        continue
                    except:
                        print("\n\n Unhandled exception!! \n\n")
                        log.fatal('instance="{}" baseDN="{}" host={} action=connect status=fail error="unhandled exception"'
                                  .format(instance, basedn, consumer_host))
                        raise
                        sys.exit(255)
                    #  Search on the consumer
                    nentries = None
                    try:
                        nentries = myldap.search(connC, entryDN, ldap.SCOPE_BASE, 'objectclass=*')
                        log.info('instance="{}" baseDN="{}" host={} action=search status=success'.format(instance, basedn, consumer_host))
                    except ldap.LDAPError as err:
                        log.error('instance="{}" baseDN="{}" host={} action=search status=fail {}'
                                  .format(instance, basedn, consumer_host, myldap.handle_log(err)))
                        RESULT[instance][basedn][supplier]['replica'][consumer_host] = False
                        someError = True
                    if nentries == 1:
                        log.info('instance="{}" baseDN="{}" supplier={} consumer={} action=validate status=success'
                                 .format(instance, basedn, supplier, consumer_host))
                        RESULT[instance][basedn][supplier]['replica'][consumer_host] = True
                    else:
                        log.info('instance="{}" baseDN="{}" supplier={} consumer={} action=validate status=fail detail="{} entries found. Expected 1"'
                                 .format(instance, basedn, supplier, consumer_host, nentries))
                        RESULT[instance][basedn][supplier]['replica'][consumer_host] = False
                        someError = True
                    # Unbind from consumer
                    try:
                        connC.unbind_s()
                        log.info('instance="{}" baseDN="{}" host={} action=disconnect status=success'.format(instance, basedn, consumer_host))
                    except:
                        log.error('instance="{}" baseDN="{}" host={} action=disconnect status=fail'.format(instance, basedn, consumer_host))
                        someError = True


            # Delete the ENTRY from the Supplier
            try:
                myldap.delete(connS, entryDN, log)
                log.info('instance="{}" baseDN="{}" host={} action=delete status=success'.format(instance, basedn, supplier))
                log.info('instance="{}" baseDN="{}" supplier={} action=validate status=success'
                         .format(instance, basedn, supplier))
                RESULT[instance][basedn][supplier]['status'] = True
            except ldap.LDAPError as err:
                log.error('instance="{}" baseDN="{}" host={} action=delete status=fail {}'
                          .format(instance, basedn, supplier, myldap.handle_log(err)))
                RESULT[instance][basedn][supplier]['status'] = False
                someError = True
                log.fatal('instance="{}" baseDN="{}" supplier={} action=validate status=fail detail="{}"'
                          .format(instance, basedn, supplier, "Can't delete"))
            except ldap.NO_SUCH_OBJECT:
                log.error('instance="{}" baseDN="{}" host={} action=delete status=fail error="No such object"'
                          .format(instance, basedn, supplier))
                RESULT[instance][basedn][supplier]['status'] = False
                someError = True
                log.fatal('instance="{}" baseDN="{}" supplier={} action=validate status=fail detail="{}"'
                          .format(instance, basedn, supplier, "Can't delete. Deleted already? Unexpected."))

            # If the replica isn't always in synch, try to send update now
            for consumer in LDAP_INSTANCES[instance][basedn][supplier]['replica']:
                for consumer_host, consumer_repl in consumer.items():
                    # "send update now" for non-always in synch replica
                    try:
                        myldap.send_update_now(connS, consumer_repl, UPDATE_SLEEPTIME, instance, basedn, supplier, consumer_host, log)
                    except myldap.sunError as err:
                        someError= True

            # Unbind from Supplier
            try:
                connS.unbind_s()
                log.info('instance="{}" baseDN="{}" host={} action=disconnect status=success'.format(instance, basedn, supplier))
            except:
                log.error('instance="{}" baseDN="{}" host={} action=disconnect status=fail'.format(instance, basedn, supplier))
                someError = True
            time.sleep(SLEEPTIME)


print(RESULT)
current_time = datetime.now()

if (someError):
    print ("FAIL. Some errors occur. Check at the log for more details.")
else:
    print ("Test completed successfully on {}!".format(current_time.ctime()))


''' Result presentation with Flask '''
app = Flask(__name__)

@app.template_filter()
# See at https://realpython.com/primer-on-jinja-templating/#custom-filters
#        https://jinja.palletsprojects.com/en/2.11.x/templates/#filters
def datetimefilter(value, format='%d/%m/%Y at %H:%M:%S'):
    """Convert a datetime to a different format."""
    return value.strftime(format)
app.jinja_env.filters['datetimefilter'] = datetimefilter

def selectIcon(selector):
    ''' Select the right icon taken from https://freeiconshop.com/icon/ '''
    if selector:
        return url_for('static', filename='yes.png')
    else:
        return url_for('static', filename='no.png')
app.jinja_env.filters['selectIcon'] = selectIcon

@app.route("/")
def index():
    return render_template('template.html', result = RESULT, testdate=current_time)

if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=8080)
