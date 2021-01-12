#!/usr/bin/env python3
import logging
import logging.handlers
import os
import time
import sys
import systemd.daemon
import ldap
from flask import Flask, render_template, url_for
from datetime import datetime
import dsReplTest.ldap as myldap
import dsReplTest.common as setting


'''
Read Config
'''
# get the config from FHS conform dir
CONFIG = os.path.join(os.path.dirname("/etc/ds-repltest/"), "ds-repltest.conf")
if not os.path.isfile(CONFIG):
    # developing stage
    CONFIG = os.path.join(os.path.dirname(myldap.__file__), "etc/ds-repltest.conf")

if not os.path.isfile(CONFIG):
    # Try to copy dist file in first config file
    distconf = os.path.join(os.path.dirname(CONFIG), "ds-repltest.conf.dist")
    if os.path.isfile(distconf):
        print("First run? I don't find <ds-repltest.conf>, but <ds-repltest.conf.dist> exists. I try to rename it.")
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
        LOGHANDLER, SYSLOG_FAC, SYSLOG_LEVEL, SYSLOG_SOCKET,
        LDAP_INSTANCES, ENTRY, NET_TIMEOUT, SLEEPTIME, UPDATE_SLEEPTIME ):
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

''' MAIN procedure '''
if systemd.daemon.booted():
    extend_time = myldap.time_to_notify(LDAP_INSTANCES, NET_TIMEOUT, SLEEPTIME, UPDATE_SLEEPTIME) * 1000000
    systemd.daemon.notify('EXTEND_TIMEOUT_USEC={}'.format(extend_time))
    systemd.daemon.notify('STATUS=Please wait. Check on progress...')
    log.debug('Systemd will wait up to {}s for end of checks.'.format(extend_time/1000000))

(RESULT, testError) = myldap.replTest(LDAP_INSTANCES, rdn, ENTRY, NET_TIMEOUT, SLEEPTIME, UPDATE_SLEEPTIME, log)
current_time = datetime.now()

if testError:
    print ("FAIL. Some errors occur. Check at the log for more details.")
    if systemd.daemon.booted():
        systemd.daemon.notify('READY=1')
        systemd.daemon.notify('STATUS=Checks completed with some errors! You can see the results on log or at the web page.')
else:
    print ("Test completed successfully on {}!".format(current_time.ctime()))
    if systemd.daemon.booted():
        systemd.daemon.notify('READY=1')
        systemd.daemon.notify('STATUS=All checks completed with success! You can see the results on log or at the web page.')

''' Result presentation with Flask inside the module dsReplTest '''
app = Flask('dsReplTest')

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

if systemd.daemon.booted():
    systemd.daemon.notify('STOPPING=1')
    systemd.daemon.notify('STATUS=ds-repltest stopping.')

