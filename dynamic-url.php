<?php
/**
 * Plugin Name: Dynamic URL
 * Description: Forces WordPress to use current domain dynamically
 * Version: 1.0
 */

if (!defined('ABSPATH')) {
    exit;
}

$current_host = $_SERVER['HTTP_HOST'] ?? 'localhost';
$current_scheme = (isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on') ? 'https' : 'http';
$current_url = $current_scheme . '://' . $current_host;

define('WP_HOME', $current_url);
define('WP_SITEURL', $current_url);

remove_action('template_redirect', 'redirect_canonical');

add_filter('home_url', 'dynamic_url_make_relative', 10, 2);
add_filter('site_url', 'dynamic_url_make_relative', 10, 2);
add_filter('post_link', 'dynamic_url_make_relative', 10, 1);
add_filter('page_link', 'dynamic_url_make_relative', 10, 1);
add_filter('post_type_link', 'dynamic_url_make_relative', 10, 1);
add_filter('term_link', 'dynamic_url_make_relative', 10, 1);
add_filter('author_link', 'dynamic_url_make_relative', 10, 1);

function dynamic_url_make_relative($url, $path = '') {
    return preg_replace('#^https?://[^/]+#', '', $url);
}

add_filter('get_the_guid', 'dynamic_url_fix_guid');
function dynamic_url_fix_guid($guid) {
    $current_host = $_SERVER['HTTP_HOST'] ?? 'localhost';
    $current_scheme = (isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on') ? 'https' : 'http';
    return preg_replace('#https?://localhost:\d+#', $current_scheme . '://' . $current_host, $guid);
}

add_filter('the_content', 'dynamic_url_fix_content');
add_filter('the_excerpt', 'dynamic_url_fix_content');
add_filter('widget_text_content', 'dynamic_url_fix_content');

function dynamic_url_fix_content($content) {
    if (empty($content)) {
        return $content;
    }
    $current_host = $_SERVER['HTTP_HOST'] ?? 'localhost';
    $content = preg_replace('#https?://localhost:\d+#', '//' . $current_host, $content);
    return $content;
}

add_filter('rest_prepare_post', 'dynamic_url_fix_rest_response', 10, 3);
add_filter('rest_prepare_page', 'dynamic_url_fix_rest_response', 10, 3);

function dynamic_url_fix_rest_response($response, $post, $request) {
    $data = $response->get_data();
    $current_host = $_SERVER['HTTP_HOST'] ?? 'localhost';
    $current_scheme = (isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on') ? 'https' : 'http';
    
    if (isset($data['link'])) {
        $data['link'] = preg_replace('#https?://localhost:\d+#', $current_scheme . '://' . $current_host, $data['link']);
    }
    
    if (isset($data['guid']['rendered'])) {
        $data['guid']['rendered'] = preg_replace('#https?://localhost:\d+#', $current_scheme . '://' . $current_host, $data['guid']['rendered']);
    }
    
    $response->set_data($data);
    return $response;
}