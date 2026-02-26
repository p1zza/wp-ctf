<?php
// Отключаем фильтрацию HTML в комментариях через хук init (после загрузки всех плагинов)

add_action('init', function() {
    // Удаляем фильтры KSES
    remove_filter('pre_comment_content', 'wp_filter_kses');
    remove_filter('pre_comment_content', 'wp_filter_kses', 10);
    remove_filter('comment_text', 'wp_filter_kses');
    remove_filter('comment_text_rss', 'wp_filter_kses');
    
    // Удаляем force_balance_tags
    remove_filter('pre_comment_content', 'force_balance_tags', 25);
    
    // Удаляем wp_filter_post_kses
    remove_filter('pre_comment_content', 'wp_filter_post_kses');
}, 100); // Высокий приоритет, выполняется после загрузки всех плагинов

// Добавляем фильтр-заглушку с приоритетом 0 (выполняется первым)
add_filter('pre_comment_content', function($content) {
    return $content;
}, 0);

// Авто-одобрение комментариев
add_filter('pre_comment_approved', function($approved, $commentdata) {
    return 1;
}, 999, 2);

// Отключаем проверку на флуд
remove_action('check_comment_flood', 'check_comment_flood_db', 10);