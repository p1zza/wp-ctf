<?php
/**
 * Plugin Name: Custom Registration
 * Description: Простая форма регистрации и логина
 * Version: 1.0
 */

add_shortcode('custom_register', 'cr_registration_form');

function cr_registration_form() {
    if (is_user_logged_in()) {
        return '<p>Вы уже авторизованы. <a href="' . wp_logout_url() . '">Выйти</a></p>';
    }
    
    $output = '';
    
    if ($_SERVER['REQUEST_METHOD'] == 'POST' && isset($_POST['cr_register'])) {
        $username = sanitize_user($_POST['username']);
        $password = $_POST['password'];
        
        $errors = new WP_Error();
        
        if (empty($username)) {
            $errors->add('empty_username', 'Введите логин');
        }
        if (empty($password)) {
            $errors->add('empty_password', 'Введите пароль');
        }
        if (strlen($password) < 6) {
            $errors->add('password_length', 'Пароль должен быть не менее 6 символов');
        }
        
        if (username_exists($username)) {
            $errors->add('username_exists', 'Такой пользователь уже существует');
        }
        
        if (empty($errors->errors)) {
            $user_id = wp_create_user($username, $password);
            
            if (!is_wp_error($user_id)) {
                wp_set_current_user($user_id);
                wp_set_auth_cookie($user_id);
                
                $output .= '<p style="color: green;">Регистрация успешна! Перенаправление...</p>';
                $output .= '<script>setTimeout(function(){ window.location.href = "/"; }, 1500);</script>';
                return $output;
            } else {
                $output .= '<p style="color: red;">Ошибка: ' . $user_id->get_error_message() . '</p>';
            }
        } else {
            foreach ($errors->get_error_messages() as $error) {
                $output .= '<p style="color: red;">' . $error . '</p>';
            }
        }
    }
    
    $output .= '
    <form method="post" action="">
        <p>
            <label for="username">Логин:</label><br>
            <input type="text" name="username" id="username" required style="width: 100%; padding: 8px;">
        </p>
        <p>
            <label for="password">Пароль:</label><br>
            <input type="password" name="password" id="password" required style="width: 100%; padding: 8px;">
        </p>
        <p>
            <input type="submit" name="cr_register" value="Зарегистрироваться" style="padding: 10px 20px; background: #0073aa; color: white; border: none; cursor: pointer;">
        </p>
    </form>
    <p>Уже есть аккаунт? <a href="/login/">Войти</a></p>
    ';
    
    return $output;
}

add_shortcode('custom_login', 'cr_login_form');

function cr_login_form() {
    if (is_user_logged_in()) {
        return '<p>Вы авторизованы как ' . wp_get_current_user()->display_name . '. <a href="' . wp_logout_url() . '">Выйти</a></p>';
    }
    
    $output = '';
    
    if ($_SERVER['REQUEST_METHOD'] == 'POST' && isset($_POST['cr_login'])) {
        $username = sanitize_user($_POST['username']);
        $password = $_POST['password'];
        
        $user = wp_authenticate($username, $password);
        
        if (!is_wp_error($user)) {
            wp_set_current_user($user->ID);
            wp_set_auth_cookie($user->ID);
            
            $output .= '<p style="color: green;">Вход выполнен! Перенаправление...</p>';
            $output .= '<script>setTimeout(function(){ window.location.href = "/"; }, 1000);</script>';
            return $output;
        } else {
            $output .= '<p style="color: red;">Неверный логин или пароль</p>';
        }
    }
    
    $output .= '
    <form method="post" action="">
        <p>
            <label for="username">Логин:</label><br>
            <input type="text" name="username" id="username" required style="width: 100%; padding: 8px;">
        </p>
        <p>
            <label for="password">Пароль:</label><br>
            <input type="password" name="password" id="password" required style="width: 100%; padding: 8px;">
        </p>
        <p>
            <input type="submit" name="cr_login" value="Войти" style="padding: 10px 20px; background: #0073aa; color: white; border: none; cursor: pointer;">
        </p>
    </form>
    <p>Нет аккаунта? <a href="/register/">Зарегистрироваться</a></p>
    ';
    
    return $output;
}

add_action('wp_head', 'cr_styles');

function cr_styles() {
    echo '
    <style>
        form[method="post"] {
            max-width: 400px;
            margin: 20px 0;
            padding: 20px;
            border: 1px solid #ddd;
            background: #f9f9f9;
        }
        form[method="post"] label {
            font-weight: bold;
        }
        form[method="post"] input[type="text"],
        form[method="post"] input[type="password"] {
            margin-top: 5px;
            margin-bottom: 15px;
            border: 1px solid #ccc;
            border-radius: 4px;
        }
        form[method="post"] input[type="submit"]:hover {
            background: #005177 !important;
        }
    </style>
    ';
}