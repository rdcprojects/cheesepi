#!/usr/bin/env python
""" Copyright (c) 2015, Swedish Institute of Computer Science
  All rights reserved.
  Redistribution and use in source and binary forms, with or without
  modification, are permitted provided that the following conditions are met:
  * Redistributions of source code must retain the above copyright
    notice, this list of conditions and the following disclaimer.
  * Redistributions in binary form must reproduce the above copyright
    notice, this list of conditions and the following disclaimer in the
    documentation and/or other materials provided with the distribution.
  * Neither the name of The Swedish Institute of Computer Science nor the
    names of its contributors may be used to endorse or promote products
    derived from this software without specific prior written permission.

 THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
 ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
 WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 DISCLAIMED. IN NO EVENT SHALL THE SWEDISH INSTITUTE OF COMPUTER SCIENCE BE LIABLE
 FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
 (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
 LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
 ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
 SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

Authors: ljjm@sics.se
Testers:
Description: Handles all configuration file duties, including initialising
a local config file (if one does not exist, and initialising logging options
"""

import os
import sys
import json
import uuid
import urllib
import logging
from pprint import PrettyPrinter

import cheesepi.log

# Globals
cheesepi_dir = os.path.dirname(os.path.realpath(__file__))
config_file = os.path.join(cheesepi_dir, "cheesepi.conf")

logger = cheesepi.log.get_logger()

# Store log in user's home directory
# if not os.access(log_file, os.W_OK):
    # print("Error: can not open log file {}".format(log_file))
    # sys.exit(1)
# LOG_LEVEL = logging.ERROR
# LOG_STDOUT = False
# LOG_FORMAT = "%(asctime)s-%(name)s:%(levelname)s; %(message)s"
# log_file = os.path.join(LOG_DIR, ".cheesepi.log")
# logging.basicConfig(filename=log_file, level=LOG_LEVEL, format=LOG_FORMAT)
# logger = logging.getLogger(__file__)

def get_logger(source=""):
    """Return logger for the specific file"""
    return logging.getLogger(source)

def get_home():
    if 'HOME' in os.environ:
        return os.environ['HOME']
    return "/root"

def update_logging():
    global log_file
    global LOG_LEVEL
    global LOG_STDOUT
    global log_formatter

    if config_defined('log_file'):
        # TODO should allow for log files in different directories, like /var/log
        filename = get('log_file')
        log_file = os.path.join(LOG_DIR, filename)
    if config_defined('LOG_LEVEL'):
        LOG_LEVEL = int(get('LOG_LEVEL'))
    if config_defined('LOG_STDOUT'):
        LOG_STDOUT = config_true('LOG_STDOUT')
    if config_defined('log_format'):
        log_formatter = logging.Formatter(get('log_format'))

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(LOG_LEVEL)

    # Remove old handlers
    for handler in root_logger.handlers:
        root_logger.removeHandler(handler)

    if log_file is not None:
        # Add log_file handler
        file_handler = logging.FileHandler(log_file, 'a')
        file_handler.setFormatter(log_formatter)
        root_logger.addHandler(file_handler)

    if LOG_STDOUT:
        # Add stdout handler
        out_handler = logging.StreamHandler(sys.stdout)
        out_handler.setFormatter(log_formatter)
        root_logger.addHandler(out_handler)

def ensure_default_config(clobber=False):
    """If config file does not exist, try to copy from default.
       Also add a local secret to the file."""
    if os.path.isfile(config_file) and not clobber:
        return

    print("Warning: Copying cheesepi.default.conf file to a local version: {}".format(config_file))
    default_config = os.path.join(cheesepi_dir, "cheesepi.default.conf")
    # Can we find the default config file?
    if os.path.isfile(default_config):
        uuid = generate_uuid()
        secret = generate_uuid()
        replace = {
            "_UUID_": uuid,
            "_SECRET_": secret,
        }
        try:
            copyfile(default_config, config_file, replace=replace)
        except Exception as exception:
            print("Error: Problem copying config file - check permissions of {}\n{}".format(
                cheesepi_dir, exception))
            sys.exit(1)
    else:
        logger.error("Can not find default config file!")

def generate_uuid():
    """Generate a uuid, to use for identification and data signing"""
    return str(uuid.uuid4())

def read_config():
    # ensure we have a config file to read
    ensure_default_config()
    try:
        fd = open(config_file)
        lines = fd.readlines()
        fd.close()
    except Exception as exception:
        logger.error("Error: can not read config file: "+str(exception))
        # should copy from default location!
        sys.exit(1)
    return lines

def get_config():
    import re
    config = {}
    lines = read_config()
    for line in lines:
        # strip comment and badly formed lines
        if re.match(r'^\s*#', line) or not re.search('=', line):
            continue
        # logger.debug(line)
        (key, value_string) = line.split("=", 1)
        value = value_string.strip()
        if value == "true":
            value = True
        if value == "false":
            value = False
        config[clean(key)] = value
    config['cheesepi_dir'] = cheesepi_dir
    config['config_file'] = config_file
    config['version'] = version()
    return config

def create_default_schedule(schedule_filename):
    """If schedule file does not exist, try to copy from default."""
    # is there already a local schedule file?
    print("Warning: Copying default schedule file to a local version")
    default_schedule = os.path.join(cheesepi_dir, "schedule.default.dat")
    # Can we find the default schedule file?
    if os.path.isfile(default_schedule):
        #try:
        copyfile(default_schedule, schedule_filename)
        #except Exception as e:
        #	msg = "Problem copying schedule file - check permissions of {}: {}".format(
        # (cheesepi_dir, str(e))
        #	logger.error(msg)
        #	sys.exit(1)
    else:
        logger.error("Can not find default schedule file schedule.default.conf!")
        sys.exit(1)

def load_local_schedule():
    schedule_filename = os.path.join(cheesepi_dir, config['schedule'])
    if not os.path.isfile(schedule_filename):
        create_default_schedule(schedule_filename)

    lines = []
    with open(schedule_filename) as f:
        lines = f.readlines()

    schedule = []
    for line in lines:
        if line.strip() == "" or line.strip().startswith("#"):
            continue # skip this comment line
        try:
            spec = json.loads(line)
            schedule.append(spec)
        except Exception as exception:
            logger.error("JSON task spec not parsed: " + line)
    return schedule

def load_remote_schedule():
    """See if we can grab a schedule from the central server
    this should (in future) include authentication"""
    # try:
        # url = 'http://cheesepi.sics.se/schedule.dat'
        # response = urllib.urlopen(url)
        # schedule = response.read()
        # return schedule
    # except urllib.HTTPError as exception:
        # message = "The CheesePi controller server '{}' couldn\'t fulfill the request. Code: {}"
        # logger.error(message.format(url, str(exception.code)))
    # except urllib.URLError as exception:
        # logger.error('We failed to reach the central server: ' + exception.reason)
    # except:
        # logger.error("Unrecognised problem when downloading remote schedule...")
    return None

def set_last_updated(dao=None):
    if dao is None:
        dao = cheesepi.storage.get_dao()
    dao.write_user_attribute("last_updated", cheesepi.utils.now())

def get_last_updated(dao=None):
    """When did we last update our code from the central server?"""
    if dao is None:
        dao = cheesepi.storage.get_dao()
    last_updated = dao.read_user_attribute("last_updated")
    # convert to seconds
    return last_updated

def get_update_period():
    """How frequently should we update?"""
    return 259200

def should_update(dao=None):
    """Should we update our code?"""
    if not config_true('auto_update'):
        return False
    last_updated = get_last_updated(dao)
    update_period = get_update_period()
    if last_updated < (cheesepi.utils.now() - update_period):
        return True
    return False

def set_last_dumped(dao=None):
    if dao is None:
        dao = cheesepi.storage.get_dao()
    dao.write_user_attribute("last_dumped", cheesepi.utils.now())

def get_last_dumped(dao=None):
    """When did we last dump our data to the central server?"""
    if dao is None:
        dao = cheesepi.storage.get_dao()
    last_dumped = dao.read_user_attribute("last_dumped")
    # convert to seconds
    return last_dumped

def get_dump_period():
    """How frequently should we dump?"""
    return 86400

def should_dump(dao=None):
    """Should we update our code?"""
    last_dumped = get_last_dumped(dao)
    dump_period = get_dump_period()
    if last_dumped < (cheesepi.utils.now()-dump_period):
        return True
    return False

def copyfile(from_file, to_file, replace={}):
    """Copy a file <from_file> to <to_file> replacing all occurrences"""
    logger.info(from_file + " " + to_file + " " + str(replace))
    with open(from_file, "rt") as fin, open(to_file, "wt") as fout:
        for line in fin:
            for occurence, replacement in replace.items():
                line = line.replace(occurence, replacement)
            fout.write(line)

def get_controller():
    if "controller" in config:
        return config['controller']
    return "http://cheesepi.sics.se"

def get_cheesepi_dir():
    return config['cheesepi_dir']

def make_databases():
    cmd = get_cheesepi_dir()+"/install/make_influx_DBs.sh"
    logger.warning("Making databases: " + cmd)
    os.system(cmd)

def version():
    """Which version of CheesePi are we running?"""
    with open(os.path.join(cheesepi_dir, 'VERSION')) as f:
        return f.read().strip()

def get(key):
    key = clean(key)
    if key in config:
        return config[key]
    return None

def get_landmarks():
    """Who shall we ping/httping?"""
    if not config_defined('landmarks'):
        return []
    landmark_string = config['landmarks']
    landmarks = landmark_string.split()
    return landmarks

def get_dashboard_port():
    # TODO: should read from config file
    return "8080"

def config_defined(key):
    """Is the specified key defined and true in the config object?"""
    key = clean(key)
    if key in config:
        return True
    return False

def config_equal(key, value):
    """Is the specified key equal to the given value?"""
    key = clean(key)
    value = clean(value)
    if key in config:
        if config[key] == value:
            return True
    return False

def config_true(key):
    """Is the specified key defined and true in the config object?"""
    key = clean(key)
    if key in config:
        if config[key] == "true":
            return True
    return False

# clean the identifiers
def clean(identifier):
    return identifier.strip().lower()

def main():
    printer = PrettyPrinter(indent=4)
    printer.pprint(config)


# Some accounting to happen on every import (mostly for config file making)
config = get_config()
#update_logging()

if __name__ == "__main__":
    main()
