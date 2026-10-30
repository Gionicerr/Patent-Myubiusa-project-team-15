#!/usr/bin/env bash
# Project-local caches and the environment's existing proxy; no credentials are copied.
set -euo pipefail
cd "$(dirname "$0")/.."
export GRADLE_USER_HOME="$PWD/.tooling/gradle-home"
export ANDROID_USER_HOME="$PWD/.tooling/android-home"
mkdir -p "$ANDROID_USER_HOME/cache" "$GRADLE_USER_HOME"
if [[ -d "$PWD/.tooling/sdk" ]]; then export ANDROID_HOME="$PWD/.tooling/sdk"; fi
if [[ -x "$PWD/.tooling/jdk/bin/javac" ]]; then
  export JAVA_HOME="$PWD/.tooling/jdk"
fi
proxy_args=()
# Trust the managed environment's CA in addition to the vendor's standard roots.
if [[ -n "${CODEX_PROXY_CERT:-}" && -f "$CODEX_PROXY_CERT" && -n "${JAVA_HOME:-}" ]]; then
  trust="$PWD/.tooling/cloud-cacerts"
  if [[ ! -f "$trust" ]]; then
    cp "$JAVA_HOME/lib/security/cacerts" "$trust"
    "$JAVA_HOME/bin/keytool" -importcert -noprompt -alias cloud-environment -file "$CODEX_PROXY_CERT" -keystore "$trust" -storepass changeit >/dev/null 2>&1
  fi
  proxy_args+=(-Djavax.net.ssl.trustStore="$trust" -Djavax.net.ssl.trustStorePassword=changeit)
fi
if [[ -n "${HTTPS_PROXY:-}" ]]; then
  read -r proxy_host proxy_port < <(python3 -c 'import os,urllib.parse; u=urllib.parse.urlsplit(os.environ["HTTPS_PROXY"]); print(u.hostname, u.port or 80)')
  proxy_args+=(-Dhttp.proxyHost="$proxy_host" -Dhttp.proxyPort="$proxy_port" -Dhttps.proxyHost="$proxy_host" -Dhttps.proxyPort="$proxy_port" '-Dhttp.nonProxyHosts=localhost|127.*')
fi
runner=./gradlew
if [[ ! -f "$runner" ]]; then runner="$PWD/.tooling/gradle-8.13/bin/gradle"; fi
exec "$runner" "${proxy_args[@]}" "$@"
