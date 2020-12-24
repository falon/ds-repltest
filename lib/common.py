import yaml
import logging
import logging.handlers
import sys

loggerName = 'ds-repltest'

def load_yaml(file, part):
     with open(file, 'r') as ymlfile:
         config_parameters = yaml.load(ymlfile, Loader=yaml.SafeLoader)[part]
     return config_parameters

def set_log(handler_type, socket, facility, level='INFO', stdout=False, filepath=False):
    log = logging.getLogger(loggerName)
    log.setLevel(level)
    formatter_syslog = logging.Formatter('%(module)s[%(process)d]: %(message)s')
    formatter_stdout = logging.Formatter('%(asctime)s %(module)s[%(process)d]: %(levelname)s: %(message)s')
    formatter_file   = logging.Formatter('%(asctime)s %(module)s[%(process)d]: %(message)s')

    if handler_type == 'syslog':
        handler_syslog = logging.handlers.SysLogHandler(address=socket, facility=facility)
        handler_syslog.setFormatter(formatter_syslog)
        handler_syslog.setLevel(level)
        log.addHandler(handler_syslog)
    if handler_type == 'file':
        if not filepath:
            return False
        oldumask = os.umask(0o0026)
        handler_file = logging.handlers.WatchedFileHandler(filepath, encoding='utf8')
        handler_file.setFormatter(formatter_file)
        handler_file.setLevel(level)
        log.addHandler(handler_file)
        os.umask(oldumask)
    if stdout:
        handler_out = logging.StreamHandler(sys.stdout)
        handler_out.setLevel(level)
        handler_out.setFormatter(formatter_stdout)
        log.addHandler(handler_out)
    return True
