# OSPFv3 lab profile

This profile enables only Zebra and OSPFv3 (`ospf6d`). The default
`/etc/frr/daemons` intentionally remains conservative and does not enable
OSPFv3 automatically.

On a lab router, back up the active daemon selection and install this profile:

```sh
sudo cp -a /etc/frr/daemons /etc/frr/daemons.pre-ospfv3
sudo install -o root -g frr -m 0640 etc/frr/profiles/ospfv3-lab/daemons /etc/frr/daemons
sudo systemctl restart frr
sudo systemctl --no-pager --full status frr
sudo vtysh -c 'show ipv6 ospf6'
```

Use this only on a test router after providing an OSPFv3 configuration and
IPv6-enabled interfaces. It does not configure addresses, areas, neighbors,
or NLS sessions. Restore the backup to return to the previous daemon selection.
