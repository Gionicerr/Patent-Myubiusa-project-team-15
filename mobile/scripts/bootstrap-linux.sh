#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .tooling/downloads
python3 - <<'PY'
from pathlib import Path
import urllib.request as u, xml.etree.ElementTree as E, hashlib, zipfile, tarfile
base=Path('.tooling')
def download(url,path):
    if not path.exists():
        temp=path.with_suffix('.part')
        with u.urlopen(url,timeout=120) as r, temp.open('wb') as f:
            while block:=r.read(1024*1024): f.write(block)
        temp.replace(path)
if not (base/'sdk/cmdline-tools/19.0/bin/sdkmanager').exists():
    with u.urlopen('https://dl.google.com/android/repository/repository2-1.xml',timeout=60) as r: root=E.fromstring(r.read())
    package=next(p for p in root.findall('remotePackage') if p.attrib['path']=='cmdline-tools;19.0')
    archive=next(a for a in package.findall('archives/archive') if a.findtext('host-os')=='linux')
    name=archive.findtext('complete/url'); expected=archive.findtext('complete/checksum')
    path=base/'downloads'/name; download('https://dl.google.com/android/repository/'+name,path)
    assert hashlib.sha1(path.read_bytes()).hexdigest()==expected, 'Android tools checksum mismatch'
    target=base/'sdk/cmdline-tools'; target.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path) as z:z.extractall(target)
    (target/'cmdline-tools').rename(target/'19.0')
    for script in (target/'19.0/bin').iterdir():script.chmod(0o755)
if not (base/'jdk/bin/javac').exists():
    name='OpenJDK17U-jdk_x64_linux_hotspot_17.0.21_9.tar.gz'
    url='https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.21%2B9/'+name
    with u.urlopen(url+'.sha256.txt',timeout=60) as r: expected=r.read().decode().split()[0]
    path=base/'downloads'/name; download(url,path)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==expected, 'JDK checksum mismatch'
    with tarfile.open(path) as t:
        root=t.getmembers()[0].name.split('/')[0]
        t.extractall(base,filter='data')
    (base/root).rename(base/'jdk')
version='8.13'
if not (base/f'gradle-{version}/bin/gradle').exists():
    url=f'https://services.gradle.org/distributions/gradle-{version}-bin.zip'
    with u.urlopen(url+'.sha256',timeout=60) as r: expected=r.read().decode().strip()
    path=base/'downloads'/f'gradle-{version}-bin.zip'; download(url,path)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==expected, 'Gradle checksum mismatch'
    with zipfile.ZipFile(path) as z:z.extractall(base)
    (base/f'gradle-{version}/bin/gradle').chmod(0o755)
PY
export ANDROID_USER_HOME="$PWD/.tooling/android-home"
mkdir -p "$ANDROID_USER_HOME/cache"
proxy_args=()
if [[ -n "${HTTPS_PROXY:-}" ]]; then
  read -r proxy_host proxy_port < <(python3 -c 'import os,urllib.parse; u=urllib.parse.urlsplit(os.environ["HTTPS_PROXY"]); print(u.hostname, u.port or 80)')
  proxy_args=(--proxy=http --proxy_host="$proxy_host" --proxy_port="$proxy_port")
fi
export ANDROID_HOME="$PWD/.tooling/sdk"
"$ANDROID_HOME/cmdline-tools/19.0/bin/sdkmanager" "${proxy_args[@]}" --sdk_root="$ANDROID_HOME" --licenses < <(yes 2>/dev/null)
"$ANDROID_HOME/cmdline-tools/19.0/bin/sdkmanager" "${proxy_args[@]}" --sdk_root="$ANDROID_HOME" 'platforms;android-36' 'build-tools;35.0.0' 'platform-tools'
printf 'sdk.dir=%s\n' "$ANDROID_HOME" > local.properties
printf '\nSDK ready. Run ./gradlew :app:assembleDebug :app:testDebugUnitTest\n'
