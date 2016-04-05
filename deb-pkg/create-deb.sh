#!/bin/bash


if [ -z "$1" ]; then
  echo "No debian packagename supplied"
  exit;
fi


# ---------------------------------
# Protect against unbound variables
# as we are using rm -Rf with a var 
# and dont want a misspelling to 
# ruin an otherwise fine day.
# ---------------------------------
set -u
# echo uninit = $UNINIT

APPNAME="marshmallow-jsonapi"
BUILDNAME="$1"
SRC=deb-pkg/new-package-source
DIST=deb-pkg/new-package-dist
SYSROOT=${SRC}/sysroot
DEBIAN=${SRC}/DEBIAN
HOME=`pwd`


# when running from jenkins,
# the PWD=/mnt/disk1/jenkins/workspace/audio-transcoder
# echo PWD = `pwd`


# ---------------------
# clean the destination
# ---------------------
echo clean destination dir
sudo rm -rf ${DIST}
mkdir -p ${DIST}
rc=$?; 
if [[ $rc != 0 ]]; then 
  echo "FAIL: mkdir -p ${DIST}"
  exit $rc; 
fi


# --------------------
# clean the source dir 
# --------------------
echo clean source dir
sudo rm -rf ${SRC}
mkdir -p ${SRC}


# --------------------
# and copy in the control files
# --------------------
echo copying in the DEBIAN control files
rsync -a deb-pkg/deb-src/DEBIAN ${SRC}
rc=$?;
if [[ $rc != 0 ]]; then
  echo "FAIL: rsync -av deb-pkg/deb-src/* ${SRC}/"
  exit $rc;
fi

echo copy in the app control files
rsync -a deb-pkg/deb-src/*  --exclude 'DEBIAN' ${SYSROOT}
if [[ $rc != 0 ]]; then
  echo "FAIL: rsync of app control files"
  exit $rc;
fi

echo copying in the app
mkdir -p ${SYSROOT}/opt/orange/${APPNAME}/
rsync -a *  --exclude '*.deb' --exclude 'deb-pkg' ${SYSROOT}/opt/orange/${APPNAME}/
if [[ $rc != 0 ]]; then
  echo "FAIL: rsync of app"
  exit $rc;
fi



# ----------------------------------------
# fixup the permissions and owner
# ensure owned by the freeipa orange user.
# ----------------------------------------
echo "adjusting permissions (takes a minute)"
find ${SRC}/ -type d -exec chmod 0755 {} \;
find ${SRC}/ -type f -exec chmod go-w {} \;
sudo chown -R orange:orange ${SYSROOT}
if [[ $rc != 0 ]]; then
  echo "FAIL: chown to orange"
  exit $rc;
fi


# --------------------------------
# we need the size of both dirs
# for the package definition later
# --------------------------------
let SIZE=`du -s ${SYSROOT} | sed s'/\s\+.*//'`+8
echo size = $SIZE


# ----------------------
# a deb package is simply 
# two tarballs and a controlfile
# 
# create the app tarball
# ----------------------
echo create app tarball
pushd ${SYSROOT} > /dev/null
/bin/tar czf ${HOME}/${DIST}/data.tar.gz [a-z]*
if [[ $rc != 0 ]]; then
  echo "FAIL: tar app"
  exit $rc;
fi
popd > /dev/null

# -----------------------
# fix up the control file
# -----------------------
sudo sed s"/SIZE/${SIZE}/" -i ${DEBIAN}/control
if [[ $rc != 0 ]]; then
  echo "FAIL: sed control file"
  exit $rc;
fi

sudo sed s"/VERSION/${BUILDNAME}/" -i ${DEBIAN}/control
if [[ $rc != 0 ]]; then
  echo "FAIL: sed control file 2"
  exit $rc;
fi

# -------------------------------
# create the config files tarball
# -------------------------------
echo create the config tarball
pushd ${DEBIAN} > /dev/null
/bin/tar czf ${HOME}/${DIST}/control.tar.gz *
if [[ $rc != 0 ]]; then
  echo "FAIL: tar control"
  exit $rc;
fi
popd > /dev/null

# ------------------------
# need this, dont know why
# ------------------------
echo 2.0 > ${DIST}/debian-binary

# -----------------------------------
# these files should be owned by root
# -----------------------------------
echo control files owned by root
find ${DIST}/ -type d -exec chmod 0755 {} \;
find ${DIST}/ -type f -exec chmod go-w {} \;
sudo chown -R root:root ${DIST}/
if [[ $rc != 0 ]]; then
  echo "FAIL: chown root"
  exit $rc;
fi

# --------------------
# create the deb file!
# --------------------
echo create the debian package file
ar r ./${BUILDNAME}.deb  ${DIST}/debian-binary ${DIST}/control.tar.gz ${DIST}/data.tar.gz
if [[ $rc != 0 ]]; then
  echo "FAIL: ar"
  exit $rc;
fi

# ---------------------
# if we are here its because we
# now have a good deb file
# ---------------------
# deb-pkg/add-deb-to-repo.sh /var/repositories main trusty ${BUILDNAME}



echo done.
