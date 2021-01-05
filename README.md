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

## How it works
For each supplier a TEST_ENTRY will be written on each root dn. After TIMEWAIT ds-repltest check on each consumer if the TEST ENTRY is replicated as well.
For non always in-synch consumers, ds-repltest forces the update and waits an UPDATE_TIMEWAIT seconds to allow the replica propagation.

Finally ds-repltest opens an HTML server where to write a brief test results summary.
