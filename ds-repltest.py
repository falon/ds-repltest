#!/usr/bin/env python3
import logging
import logging.handlers
import os
import time
import sys
import systemd.daemon
import ldap
import getopt
from flask import Flask, render_template, url_for
from datetime import datetime
import dsReplTest.ldap as myldap
import dsReplTest.common as setting


# Manage argv
argv = sys.argv[1:]
config_file = 'ds-repltest.yaml'
runOnce = False
usage = 'Usage: {} [-c <alt config file>][--once][--help]'.format(sys.argv[0])
try:
    opts, args = getopt.getopt(argv,"c:",["once","help"])
except getopt.GetoptError:
    print (usage)
    sys.exit(2)
for opt, arg in opts:
    if opt == '-c':
        config_file = arg
    elif opt == '--once':
        runOnce = True
    elif opt == '--help':
        print (usage)
        sys.exit(0)
    else:
        print (usage)
        sys.exit(2)

if args:
    print('Unhadled arguments!')
    print (usage)
    sys.exit(2)

'''
Read Config
'''
# get the config from FHS conform dir
config_path = "/etc/ds-repltest/"
CONFIG = os.path.join(os.path.dirname(config_path), config_file)
if not os.path.isfile(CONFIG):
    # developing stage
    config_path ="etc/"
    CONFIG = os.path.join(os.path.dirname(myldap.__file__), "{}{}".format(config_path, config_file))

if not os.path.isfile(CONFIG):
    # Try to copy dist file in first config file
    distconf = os.path.join(os.path.dirname(CONFIG), "{}.dist".format(config_file))
    if os.path.isfile(distconf):
        print("First run? I don't find <{}>, but <{}.dist> exists. I try to rename it.".format(config_file, config_file))
        os.rename(distconf, os.path.join(os.path.dirname(distconf), config_file))

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

    email_parameters = setting.load_yaml(CONFIG, "Email")
    web_parameters = setting.load_yaml(CONFIG, "Web")
    LDAP_INSTANCES = setting.load_yaml(CONFIG, "INSTANCES")
    ENTRY = setting.load_yaml(CONFIG, "TEST_ENTRY")
    NET_TIMEOUT = setting.load_yaml(CONFIG, "TIMEOUT")
    SLEEPTIME = setting.load_yaml(CONFIG, "TIMEWAIT")
    UPDATE_SLEEPTIME = setting.load_yaml(CONFIG, "UPDATE_TIMEWAIT")
else:
    sys.exit("Please check the config file! Config path: {}.\nHint: put a '{}' file in {} path.".format(CONFIG, config_file, config_path))
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
if runOnce:
    (RESULT, testError) = myldap.replTest(LDAP_INSTANCES, rdn, ENTRY, NET_TIMEOUT, SLEEPTIME, UPDATE_SLEEPTIME, log, LOGSTDOUT)
    if testError:
        print ("FAIL. Some errors occur. Check at the log for more details.")
        if email_parameters['SEND']:
            log.info('Sending mail to notify errors')
            (emailSent, emailErr) = setting.notifyEmail(email_parameters)
            if not emailSent:
                log.error('Unable to send email: {}'.format(emailErr))
        sys.exit(255)
    else:
        print ("Test completed successfully!")
        sys.exit(0)

# Run in systemd
if systemd.daemon.booted():
    extend_time = myldap.time_to_notify(LDAP_INSTANCES, NET_TIMEOUT, SLEEPTIME, UPDATE_SLEEPTIME) * 1000000
    systemd.daemon.notify('EXTEND_TIMEOUT_USEC={}'.format(extend_time))
    systemd.daemon.notify('STATUS=Please wait. Check on progress...')
    log.debug('Systemd will wait up to {}s for end of checks.'.format(extend_time/1000000))

(RESULT, testError) = myldap.replTest(LDAP_INSTANCES, rdn, ENTRY, NET_TIMEOUT, SLEEPTIME, UPDATE_SLEEPTIME, log, LOGSTDOUT)
current_time = datetime.now()

if testError:
    print ("FAIL. Some errors occur. Check at the log for more details.")
    if email_parameters['SEND']:
        log.info('Sending mail to notify errors')
        (emailSent, emailErr) = setting.notifyEmail(email_parameters)
        if not emailSent:
            log.error('Unable to send email: {}'.format(emailErr))
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
    ''' Select the right icon taken from https://freeiconshop.com/icon/
        and https://icons-for-free.com/ '''
    if selector is None:
        return url_for('static', filename='undef.png')
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
    try:
        serve(app, host=web_parameters['HOST'], port=web_parameters['PORT'])
    except Exception as exc:
        log.error('Unable to start the webserver: {}'.format(exc))

if systemd.daemon.booted():
    systemd.daemon.notify('STOPPING=1')
    systemd.daemon.notify('STATUS=ds-repltest stopping.')

