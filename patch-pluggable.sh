#!/bin/bash

PLUGGABLE_FILE='/var/www/html/wp-includes/pluggable.php'

if [ ! -f "$PLUGGABLE_FILE" ]; then
    echo "Error: pluggable.php not found at $PLUGGABLE_FILE"
    exit 1
fi

echo "Patching pluggable.php..."

cp "$PLUGGABLE_FILE" "${PLUGGABLE_FILE}.bak"

sed -i 's/setcookie( \$auth_cookie_name, \$auth_cookie, \$expire, PLUGINS_COOKIE_PATH, COOKIE_DOMAIN, \$secure, true );/setcookie( \$auth_cookie_name, \$auth_cookie, \$expire, PLUGINS_COOKIE_PATH, COOKIE_DOMAIN, \$secure, false );/g' "$PLUGGABLE_FILE"

sed -i 's/setcookie( \$auth_cookie_name, \$auth_cookie, \$expire, ADMIN_COOKIE_PATH, COOKIE_DOMAIN, \$secure, true );/setcookie( \$auth_cookie_name, \$auth_cookie, \$expire, ADMIN_COOKIE_PATH, COOKIE_DOMAIN, \$secure, false );/g' "$PLUGGABLE_FILE"

sed -i 's/setcookie( LOGGED_IN_COOKIE, \$logged_in_cookie, \$expire, COOKIEPATH, COOKIE_DOMAIN, \$secure_logged_in_cookie, true );/setcookie( LOGGED_IN_COOKIE, \$logged_in_cookie, \$expire, COOKIEPATH, COOKIE_DOMAIN, \$secure_logged_in_cookie, false );/g' "$PLUGGABLE_FILE"

sed -i 's/setcookie( LOGGED_IN_COOKIE, \$logged_in_cookie, \$expire, SITECOOKIEPATH, COOKIE_DOMAIN, \$secure_logged_in_cookie, true );/setcookie( LOGGED_IN_COOKIE, \$logged_in_cookie, \$expire, SITECOOKIEPATH, COOKIE_DOMAIN, \$secure_logged_in_cookie, false );/g' "$PLUGGABLE_FILE"

echo "Changes applied. Verifying:"
grep -n "setcookie.*false" "$PLUGGABLE_FILE" | head -10

echo "pluggable.php patched successfully"