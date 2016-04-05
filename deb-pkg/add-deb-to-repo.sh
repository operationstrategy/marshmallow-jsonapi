#!/usr/bin/expect -f
set timeout 2
set passphrase "Master keys do not normally have expiration dates, but set this value as long as you expect to use this key."

# USAGE: add-deb-to-repo.sh  /var/repositories main trusty mypackage_0.1-1_all.deb

spawn reprepro -b [lindex $argv 0] [lindex $argv 1] [lindex $argv 2] [lindex $argv 3]
expect {
        "*passphrase:*" {
                send -- "$passphrase\r"
        }
}
expect {
        "*passphrase:*" {
                send -- "$passphrase\r"
        }
}
interact
