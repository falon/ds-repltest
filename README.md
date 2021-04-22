# ds-repltest
A 389ds replication checker. With this tool you can test your LDAP replication.

At this time the tool doesn't autodiscover the replication topology. You must
replicate it in the configuration file.

ds-repltest read the configuration and it tests every supplier and consumer for the replication.
Finally it writes a brief HTML summary and detailed syslog.

## Knowing the config file
It's a YAML file, so you have to pay attention to spaces.
The core part is INSTANCES. We suggest to name them with the same name of the Directory Server instances.

Every instance has one or more suppliers, one or more consumers where you want to check the replication.
You can see at your replication agreements to discover your topology. At the moment I haven't implemented an autodiscovery.

Every instance has one or more **root DN**, corresponding to a database on the Directory Server.
For every root DN you have to specify one or more supplier hosts.

For every supplier we provide the following keys:
- port: the LDAP port.
- protocol: interface to ldap server (at the moment only 'ldap' is supported).
- bind: the bind DN with write access to the rootDN.
- pwd: the password of bind dn user.
- replica: is an array of suppliers hosts. Each suppliers could have a replication agreement dn if the replica is not always in synch. The replica dn is used to force the update to the supplier.

We assume that `bind` and `pwd` are the same for every consumer too.

If at least an error occurs, you can send a short email message. See at  the `Email` section of the config file.

## How it works
For each supplier a TEST_ENTRY will be written on each root dn. After TIMEWAIT ds-repltest check on each consumer if the TEST ENTRY is replicated as well.
For non always in-synch consumers, ds-repltest forces the update and waits an UPDATE_TIMEWAIT seconds to allow the replica propagation.

Finally ds-repltest opens an HTML server where to write a brief test results summary.

By default, on el8 based systemd, the check repeats every 12h (see at `RuntimeMaxSec`) and **ds-repltest** notifies systemd to wait for the end of check through `EXTEND_TIMEOUT_USEC`.

`EXTEND_TIMEOUT_USEC` is evaluated runtime reading at the configuration file.

## INSTALL
On Centos/RHEL 8 simply create the repo:

```
curl -1sLf \
  'https://dl.cloudsmith.io/public/csi/dsrepltest/cfg/setup/bash.rpm.sh' \
  | sudo -E bash
```

If you have a modular python, you may have to add

`module_hotfixes=true`

under

`[csi-dsrepltest]` section of `/etc/yum.repos.d/csi-dsrepltest.repo`.

Then run

`dnf install python3-ds-repltest`

Now you can modify your `/etc/ds-repltest/ds-repltest.yaml` and run `systemct start ds-repltest.service --no-block`

The checks could takes several minutes to perform. During this time the status is

`"Please wait. Check on progress..."`

and at the end you will see:

`"All checks completed with success! You can see the results on log or at the web page."` if there are no errors.

If there are some errors you will see:

`"Checks completed with some errors! You can see the results on log or at the web page."`

Anyway, you can now point to `http://<host>:8080` to see the results with your favourite browser, where `<host>` is the fqdn of the host running **ds-repltet**.

You can customize the host and port where listen to through the `Web` config var.



### Note for EL7
On systemd version < 236 the `EXTEND_TIMEOUT_USEC` doesn't work, and `RuntimeMaxSec` is unknown.
You can modify **/usr/lib/systemd/system/ds-repltest.service** in this way:
```
#RuntimeMaxSec=12h
TimeoutStartSec=1200
```
You can modify the timeout in order to complete your checks.
Don't forget `systemctl daemon-reload`.

## OPTIONAL ARGUMENTS
### --once
Alternatively to systemd, the check could run once by command line and then exit. Run the command in this way:

    ds-repltest.py --once

In this mode ds-repltest run the checks and exits without open a permanent webserver. The exit status is 0 only if no errors occur.

### -c <alt config file>
You can specify an alternative config file in place of `ds-repltest.yaml`. Add the optional argument `-c <config file name>`.

Put your config file in the `/etc/ds-repltest` path.
