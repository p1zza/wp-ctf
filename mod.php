<?php
add_action('init', function() {
    remove_filter('pre_comment_content', 'wp_filter_kses');
    remove_filter('comment_text', 'wp_filter_kses');
    remove_filter('comment_text_rss', 'wp_filter_kses');
    remove_filter('pre_comment_content', 'wp_filter_post_kses');
    remove_filter('pre_comment_content', 'force_balance_tags', 25);
}, 100);

add_filter('pre_comment_content', function($content) {
    return $content;
}, 0);

add_filter('pre_comment_approved', function($approved, $commentdata) {
    return 1;
}, 999, 2);

add_action('init', function() {
    remove_action('check_comment_flood', 'check_comment_flood_db', 10);
}, 20);

add_action('comment_form_logged_in_after', 'xss_private_checkbox');
add_action('comment_form_after_fields', 'xss_private_checkbox');

function xss_private_checkbox() {
    echo '<p class="comment-form-private">
        <label>
            <input type="checkbox" name="private_comment" value="1">
            Приватный комментарий (виден только мне и администратору)
        </label>
    </p>';
}

add_action('comment_post', 'xss_save_private', 10, 2);

function xss_save_private($comment_id, $approved) {
    if (!empty($_POST['private_comment']) && $_POST['private_comment'] === '1') {
        update_comment_meta($comment_id, '_private_comment', '1');
    }
}

add_filter('comments_array', 'xss_filter_private', 999, 2);

function xss_filter_private($comments, $post_id) {
    if (current_user_can('administrator') || current_user_can('manage_options')) {
        return $comments;
    }
    
    if (is_admin() && !defined('DOING_AJAX')) {
        return $comments;
    }
    
    $current_user_id = get_current_user_id();
    $filtered = [];
    
    foreach ($comments as $comment) {
        $is_private = get_comment_meta($comment->comment_ID, '_private_comment', true);
        
        if (empty($is_private) || $is_private !== '1') {
            $filtered[] = $comment;
            continue;
        }
        
        $post = get_post($post_id);
        $is_post_author = ($post && $post->post_author == $current_user_id);
        $is_comment_author = ($comment->user_id == $current_user_id);
        
        if ($is_comment_author || $is_post_author) {
            $filtered[] = $comment;
        }
    }
    
    return $filtered;
}

add_filter('the_comments', 'xss_filter_the_comments', 999, 2);

function xss_filter_the_comments($comments, $query) {
    if (is_admin() && !defined('DOING_AJAX')) {
        return $comments;
    }
    if (current_user_can('administrator')) {
        return $comments;
    }
    
    $current_user_id = get_current_user_id();
    $filtered = [];
    
    foreach ($comments as $comment) {
        $is_private = get_comment_meta($comment->comment_ID, '_private_comment', true);
        
        if (empty($is_private) || $is_private !== '1') {
            $filtered[] = $comment;
            continue;
        }
        
        $post = get_post($comment->comment_post_ID);
        $is_post_author = ($post && $post->post_author == $current_user_id);
        $is_comment_author = ($comment->user_id == $current_user_id);
        
        if ($is_comment_author || $is_post_author) {
            $filtered[] = $comment;
        }
    }
    
    return $filtered;
}

add_filter('pre_get_comments', 'xss_filter_admin_comments', 999);

function xss_filter_admin_comments($query) {
    if (!is_admin() || defined('DOING_AJAX')) {
        return;
    }
    
    if (current_user_can('administrator') || current_user_can('manage_options')) {
        return;
    }
    
    $current_user_id = get_current_user_id();
    if (!$current_user_id) {
        return;
    }
    
    $user_posts = get_posts([
        'author' => $current_user_id,
        'post_type' => 'any',
        'posts_per_page' => -1,
        'fields' => 'ids'
    ]);
    
    $meta_query = [
        'relation' => 'OR',
        [
            'key' => '_private_comment',
            'compare' => 'NOT EXISTS'
        ],
        [
            'key' => '_private_comment',
            'value' => '1',
            'compare' => '='
        ]
    ];
    
    if (!empty($user_posts)) {
        $meta_query[] = [
            'key' => '_private_comment',
            'value' => '1',
            'compare' => '='
        ];
    }
    
    $query->query_vars['meta_query'] = $meta_query;
    
    add_filter('comments_clauses', function($clauses, $comment_query) use ($current_user_id, $user_posts) {
        global $wpdb;
        
        $private_condition = '';
        
        if (!empty($user_posts)) {
            $posts_in = implode(',', array_map('intval', $user_posts));
            $private_condition = $wpdb->prepare(
                " OR (cmt.meta_value = '1' AND ({$wpdb->comments}.user_id = %d OR {$wpdb->comments}.comment_post_ID IN ({$posts_in}))) ",
                $current_user_id
            );
        } else {
            $private_condition = $wpdb->prepare(
                " OR (cmt.meta_value = '1' AND {$wpdb->comments}.user_id = %d) ",
                $current_user_id
            );
        }
        
        if (!strpos($clauses['join'], 'commentmeta')) {
            $clauses['join'] .= " LEFT JOIN {$wpdb->commentmeta} cmt ON {$wpdb->comments}.comment_ID = cmt.comment_id AND cmt.meta_key = '_private_comment' ";
        }
        
        $clauses['where'] .= $wpdb->prepare(
            " AND (cmt.meta_value IS NULL OR cmt.meta_value != '1' {$private_condition}) ",
            $current_user_id
        );
        
        return $clauses;
    }, 999, 2);
}

add_filter('get_comments_number', 'xss_fix_count', 999, 2);

function xss_fix_count($count, $post_id) {
    if (is_admin() || current_user_can('administrator')) {
        return $count;
    }
    
    $comments = get_comments([
        'post_id' => $post_id,
        'status' => 'approve',
        'include_unapproved' => []
    ]);
    
    $current_user_id = get_current_user_id();
    $post = get_post($post_id);
    $is_post_author = ($post && $post->post_author == $current_user_id);
    $visible = 0;
    
    foreach ($comments as $comment) {
        $is_private = get_comment_meta($comment->comment_ID, '_private_comment', true);
        
        if (empty($is_private) || $is_private !== '1') {
            $visible++;
        } elseif ($comment->user_id == $current_user_id || $is_post_author) {
            $visible++;
        }
    }
    
    return $visible;
}

add_action('wp_head', 'xss_private_css');

function xss_private_css() {
    echo '<style>
        .comment-form-private {
            margin: 10px 0;
            padding: 10px;
            background: #f0f0f0;
            border-radius: 4px;
        }
        .private-comment {
            background-color: #fff3cd !important;
            border-left: 4px solid #ffc107 !important;
            padding: 10px;
        }
        .private-comment::before {
            content: "🔒 Приватный комментарий";
            display: block;
            font-size: 12px;
            color: #856404;
            margin-bottom: 5px;
            font-weight: bold;
        }
    </style>';
}

add_filter('comment_class', 'xss_private_class', 10, 4);

function xss_private_class($classes, $class, $comment_id, $post_id) {
    $is_private = get_comment_meta($comment_id, '_private_comment', true);
    if ($is_private === '1') {
        $classes[] = 'private-comment';
    }
    return $classes;
}

add_action('template_redirect', 'xss_protect_direct');

function xss_protect_direct() {
    if (!is_singular()) return;
    
    $comment_id = isset($_GET['c']) ? intval($_GET['c']) : 0;
    if (!$comment_id) return;
    
    $comment = get_comment($comment_id);
    if (!$comment) return;
    
    $is_private = get_comment_meta($comment_id, '_private_comment', true);
    if ($is_private !== '1') return;
    
    $current_user_id = get_current_user_id();
    $post = get_post($comment->comment_post_ID);
    $is_post_author = ($post && $post->post_author == $current_user_id);
    
    if ($comment->user_id != $current_user_id && !$is_post_author && !current_user_can('administrator')) {
        wp_die('Этот комментарий приватный.', 'Доступ запрещён', ['response' => 403]);
    }
}