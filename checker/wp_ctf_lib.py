import requests
import json
import os
import re
import random
import time
from checklib import *
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

PORT = 8080 

CREDENTIALS_FILE = '/tmp/wp_ctf_credentials.json'

WP_PATHS = {
    'home': '/',
    'login': '/login/',
    'admin': '/wp-admin/',
    'register': '/register/',
    'logout': '/wp-login.php?action=logout',
    'posts': '/?p=1',  
    'xmlrpc': '/xmlrpc.php'
}

class CheckMachine:
    def __init__(self, checker):
        self.checker = checker
        self.base_url = f'http://{self.checker.host}:{PORT}'

    def _save_credentials(self, username, password, flag=None):
        creds = {}
        if os.path.exists(CREDENTIALS_FILE):
            with open(CREDENTIALS_FILE, 'r') as f:
                creds = json.load(f)
        creds[username] = {'password': password, 'flag': flag}
        with open(CREDENTIALS_FILE, 'w') as f:
            json.dump(creds, f)

    def _get_credentials(self, username):
        if os.path.exists(CREDENTIALS_FILE):
            with open(CREDENTIALS_FILE, 'r') as f:
                creds = json.load(f)
                data = creds.get(username)
                if isinstance(data, dict):
                    return data.get('password'), data.get('flag')
                return data, None  # обратная совместимость
        return None, None

    def _load_comments(self):
        """Загрузка комментариев из файла comments.json"""
        comments_file = os.path.join(os.path.dirname(__file__), 'comments.json')
        default_comments = ["Great post!", "Nice article", "Thanks for sharing"]
        
        try:
            with open(comments_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [str(c) for c in data if c]
                elif isinstance(data, dict) and 'comments' in data:
                    return [str(c) for c in data['comments'] if c]
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        
        return default_comments

    def _get_random_comment(self):
        """Получить случайный комментарий из файла"""
        comments = self._load_comments()
        return random.choice(comments)

    def ping(self):
        paths_to_check = [
            WP_PATHS['home'],           
            WP_PATHS['login'],          
            WP_PATHS['register'],       
            WP_PATHS['admin'],          
            WP_PATHS['posts'], 
            WP_PATHS['xmlrpc']           
        ]
        
        for path in paths_to_check:
            try:
                r = requests.get(f'{self.base_url}{path}', timeout=5)
                if r.status_code >= 500:
                    self.checker.cquit(Status.DOWN, f'Path {path} returning 5xx')
            except requests.exceptions.RequestException as e:
                self.checker.cquit(Status.DOWN, f'Cannot connect to {path}', str(e))
        
        r = requests.get(f'{self.base_url}{WP_PATHS["home"]}', timeout=5)
        if 'wordpress' not in r.text.lower() and 'wp-content' not in r.text:
            self.checker.cquit(Status.MUMBLE, 'WordPress not detected')

    def login_admin(self, username='admin', password='supersecret123'):    
        login_url = f'{self.base_url}/wp-login.php'
        session = requests.Session()
        r = session.get(login_url, timeout=10)
        
        if r.status_code != 200:
            raise Exception(f'Failed to load login page: {r.status_code}')
        data = {
            'log': username,
            'pwd': password,
            'wp-submit': 'Log In',
            'redirect_to': f'{self.base_url}/wp-admin/',
            'testcookie': '1'
        }
        
        headers = {
            'Origin': self.base_url,
            'Referer': login_url,
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        r = session.post(login_url, data=data, headers=headers, allow_redirects=False, timeout=10)
        if r.status_code not in [200, 302]:
            raise Exception(f'Admin login failed with status: {r.status_code}')
        
        if r.status_code == 200:
            error_match = re.search(r'<div[^>]*id="login_error"[^>]*>(.*?)</div>', r.text, re.DOTALL)
            if error_match:
                error_text = re.sub(r'<[^>]+>', '', error_match.group(1))
                raise Exception(f'Login error: {error_text.strip()}')
        
        has_auth = False
        for cookie in session.cookies:
            if 'wordpress_logged_in' in cookie.name:
                has_auth = True
                break
        
        if not has_auth:
            raise Exception('No wordpress_logged_in cookie found. Login failed.')
        
        print(f'Login successful. Got cookies: {[c.name for c in session.cookies]}')
        return session

    def register(self, username, password, email=None, role='author'):    
        """
        Регистрация пользователя через фронтенд-форму на странице ?page_id=4
        """
        register_url = f'{self.base_url}{WP_PATHS["register"]}'
        
        session = requests.Session()
        
        r = session.get(register_url, timeout=10)
        
        if r.status_code != 200:
            raise Exception(f'Failed to load registration page: {r.status_code}')
        
        data = {
            'username': username,
            'password': password,
            'cr_register': 'Зарегистрироваться'  
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': self.base_url,
            'Referer': register_url,
        }
        
        r = session.post(register_url, data=data, headers=headers, timeout=10)
        
        if r.status_code != 200:
            raise Exception(f'Registration request failed: {r.status_code}')
        
        response_text = r.text.lower()
        
        success_indicators = [
            'регистрация завершена',
            'registration complete',
            'success',
            'успешно',
            'logout' in response_text, 
            'привет' in response_text,  
        ]
        
        if any(indicator if isinstance(indicator, bool) else indicator in response_text 
            for indicator in success_indicators):
            print(f'User {username} registered successfully via frontend')
            return True
        
        # Пользователь уже существует
        exists_indicators = [
            'уже существует',
            'already exists',
            'username уже зарегистрирован',
            'username is already registered',
            'email уже зарегистрирован',
            'email is already registered'
        ]
        
        if any(indicator in response_text for indicator in exists_indicators):
            print(f'User {username} already exists')
            return 'exists'
        
        # Ошибка регистрации
        error_match = re.search(r'<div[^>]*class="[^"]*(?:error|alert)[^"]*"[^>]*>(.*?)</div>', 
                            r.text, re.DOTALL | re.IGNORECASE)
        if error_match:
            error_text = re.sub(r'<[^>]+>', '', error_match.group(1))
            raise Exception(f'Registration error: {error_text.strip()}')
        
        # Если не удалось определить статус, считаем что успешно
        if 'wp-login.php' not in r.url and 'login' not in r.url.lower():
            #print(f'User {username} probably registered (no error detected)')
            return True
        
        raise Exception('Registration failed - unexpected redirect')
    
    def login(self, username, password):
        """Вход через фронтенд-форму на странице ?page_id=5"""
        login_url = f'{self.base_url}{WP_PATHS["login"]}'

        session = requests.Session()
        
        # Получаем страницу входа для cookies
        r = session.get(login_url, timeout=5)
        self.checker.check_response(r, 'Cannot load login page')

        # Формируем данные для входа
        data = {
            'username': username,
            'password': password,
            'cr_login': 'Войти'
        }

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': self.base_url,
            'Referer': login_url,
        }

        r = session.post(login_url, data=data, headers=headers, allow_redirects=True, timeout=10)

        # Отладка: выводим cookies и URL
        #print(f'[DEBUG] After login: URL={r.url}')
        #print(f'[DEBUG] Cookies: {[f"{c.name}={c.value[:20]}..." for c in session.cookies]}')
        
        # Проверяем наличие auth cookie WordPress
        has_auth = False
        for cookie in session.cookies:
            if 'wordpress_logged_in' in cookie.name:
                has_auth = True
                break
        
        # Проверяем по контенту страницы
        response_text = r.text.lower()
        has_welcome = any([
            'logout' in response_text,
            'привет' in response_text,
            'welcome' in response_text,
            'личный кабинет' in response_text,
            'dashboard' in response_text,
            'wp-admin' in r.url,
        ])
        
        #print(f'[DEBUG] has_auth cookie: {has_auth}')
        #print(f'[DEBUG] has_welcome content: {has_welcome}')
        
        if not has_auth and not has_welcome:
            # Проверяем ошибки
            error_indicators = [
                'неверный' in response_text,
                'invalid' in response_text,
                'incorrect' in response_text,
                'ошибка' in response_text,
                'error' in response_text,
            ]
            if any(error_indicators):
                self.checker.cquit(Status.MUMBLE, 'Login failed - invalid credentials')
            else:
                self.checker.cquit(Status.MUMBLE, 'Login failed - no auth indicators')

        return session

    def put_flag(self, flag_id, flag, vuln=None):
        """
        1. Создает учетку
        2. Публичный пост с title=flag_id
        3. Приватный комментарий с флагом к ПОСТУ №1 через REST API
        """
        username = f'user_{flag_id[:8]}'
        password = flag_id[:20]
        email = f'{username}@local.local'
        
        self._save_credentials(username, password, flag)
        
        try:
            # Регистрация и логин
            result = self.register(username, password, email)
            if result == 'exists':
                session = self.login(username, password)
            else:
                session = self.login(username, password)
            
            self.session = session
            
            # Публичный пост с title=flag_id
            random_content = self._get_random_comment()
            post_id = self._create_public_post(flag_id, random_content)
            #print(f'[+] Created public post #{post_id} with title={flag_id}')
            
            # ПРИВАТНЫЙ КОММЕНТАРИЙ С ФЛАГОМ К ПОСТУ №1 ЧЕРЕЗ REST API
            self._post_private_comment_rest(1, flag)
            
            #print(f'[+] Posted private comment with flag to post #1 via REST')
            
            return username[5:]
            
        except Exception as e:
            self.checker.cquit(Status.MUMBLE, 'put_flag failed', str(e))

    def _post_private_comment_rest(self, post_id, flag):
        """
        Публикация приватного комментария через REST API (без Selenium)
        """
        # Получаем nonce для комментариев
        post_url = f'{self.base_url}/?p={post_id}'
        r = self.session.get(post_url, timeout=10)
        
        # Ищем nonce
        nonce_match = re.search(r'name="_wp_unfiltered_html_comment"[^>]*value=["\']([^"\']+)["\']', r.text)
        nonce = nonce_match.group(1) if nonce_match else ''
        
        # Отправляем комментарий через обычный POST (как форма)
        data = {
            'private_comment': '1',
            'comment': flag,
            'submit': 'Post Comment',
            'comment_post_ID': str(post_id),
            'comment_parent': '0',
            '_wp_unfiltered_html_comment': nonce
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': self.base_url,
            'Referer': post_url,
        }
        
        r = self.session.post(
            f'{self.base_url}/wp-comments-post.php',
            data=data,
            headers=headers,
            timeout=10
        )
        
        if r.status_code in [200, 302]:
            # Проверяем что комментарий появился
            check_r = self.session.get(post_url, timeout=10)
            if flag in check_r.text:
                return True
        
        raise Exception(f'Failed to post comment: {r.status_code}')


    def _create_public_post(self, title, content):
        """Создание публичного поста через REST API"""
        # Получаем nonce из админки
        r = self.session.get(f'{self.base_url}/wp-admin/post-new.php', timeout=10)
        
        if r.status_code != 200:
            raise Exception(f'Failed to load post-new.php: {r.status_code}')
        
        if 'wp-login.php' in r.url:
            raise Exception('Session not working - redirected to login')
        
        nonce = None
        nonce_match = re.search(r'"restNonce":"([^"]+)"', r.text)
        if nonce_match:
            nonce = nonce_match.group(1)
        else:
            nonce_match = re.search(r'wpApiSettings\s*=\s*\{[^}]*"nonce"\s*:\s*"([^"]+)"', r.text)
            if nonce_match:
                nonce = nonce_match.group(1)
        
        if not nonce:
            # Пробуем альтернативные способы
            nonce_match = re.search(r'<meta[^>]*name="api-nonce"[^>]*content="([^"]+)"', r.text)
            if nonce_match:
                nonce = nonce_match.group(1)
            if not nonce:
                nonce_match = re.search(r'name="_wpnonce"[^>]*value="([^"]+)"', r.text)
                if nonce_match:
                    nonce = nonce_match.group(1)
        
        if not nonce:
            raise Exception(f'Could not get REST API nonce')
        
        #print(f'[+] Got REST nonce: {nonce}')
        
        # Создаем публичный пост
        rest_url = f'{self.base_url}/index.php?rest_route=/wp/v2/posts'
        post_data = {
            'title': title,
            'content': content,
            'status': 'publish'  # Публичный пост
        }
        
        headers = {
            'X-WP-Nonce': nonce,
            'Content-Type': 'application/json'
        }
        
        r = self.session.post(rest_url, json=post_data, headers=headers, timeout=10)
        
        if r.status_code in [200, 201]:
            response_json = r.json()
            post_id = response_json.get('id')
            if post_id:
                return post_id
            else:
                raise Exception('No post id in response')
        else:
            raise Exception(f'REST API error: {r.status_code} - {r.text[:200]}')

    def _post_private_comment_to_post(self, post_id, flag):
        """
        Публикация приватного комментария с флагом к указанному посту
        Аналогично вашему curl запросу
        """
        post_url = f'{self.base_url}/?p={post_id}'
        
        # Получаем страницу поста для nonce
        r = self.session.get(post_url, timeout=10)
        
        if r.status_code != 200:
            raise Exception(f'Failed to load post page: {r.status_code}')
        
        # Ищем nonce для комментария
        nonce_match = re.search(r'name="_wp_unfiltered_html_comment"[^>]*value=["\']([^"\']+)["\']', r.text)
        nonce = nonce_match.group(1) if nonce_match else ''
        
        # Формируем данные как в вашем curl
        data = {
            'private_comment': '1',
            'comment': flag,
            'submit': 'Post Comment',
            'comment_post_ID': str(post_id),
            'comment_parent': '0',
            '_wp_unfiltered_html_comment': nonce
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': self.base_url,
            'Referer': post_url,
        }
        
        r = self.session.post(
            f'{self.base_url}/wp-comments-post.php',
            data=data,
            headers=headers,
            timeout=10,
            allow_redirects=True
        )
        
        # Проверяем успешность (обычно редирект на тот же пост)
        if r.status_code in [200, 302]:
            # Проверяем, что комментарий появился
            check_r = self.session.get(post_url, timeout=10)
            if flag in check_r.text:
                #print(f'[+] Private comment verified on post #{post_id}')
                return True
            else:
                # Может быть moderation
                #print(f'[!] Comment posted but flag not visible (may be pending moderation)')
                return True
        
        raise Exception(f'Failed to post comment: {r.status_code}')

    def get_flag(self, flag_id, flag=None, vuln=None):
        """
        1. Логинится через requests (получаем куки)
        2. Selenium с куками: открывает пост #1
        3. Ищет flag_value в приватных комментариях поста #1
        """
        username = f'user_{flag_id[:8]}'
        password = flag_id[:20]
        expected_flag = flag  # flag_value из параметра
        
        #print(f'[DEBUG] get_flag: flag_id={flag_id}, username={username}, expected_flag={expected_flag}')
        
        try:
            posts = self._get_all_posts()
            #print(f'[+] Found {len(posts)} posts via REST API')
            
            if not posts:
                self.checker.cquit(Status.CORRUPT, 'No posts found')
            
            # Selenium: просто проходим по всем постам (без поиска флага)
            self._selenium_fast_browse(username, password, posts, expected_flag)
            
            # Возвращаем expected_flag — checker.py сам проверит через assert_eq
        except Exception as e:
            self.checker.cquit(Status.MUMBLE, 'Cant get flag', str(e))


        try:
            # Логинимся через requests (получаем куки)
            session = self.login(username, password)
            self.session = session
            
            # Получаем куки из сессии
            cookies = session.cookies.get_dict()
            #print(f'[DEBUG] Got cookies from login: {list(cookies.keys())}')
            
            # Selenium с куками: открываем пост #1 и ищем флаг
            flag_value = self._selenium_check_post1_with_cookies(cookies, expected_flag)
            
            if not flag_value:
                self.checker.cquit(Status.CORRUPT, 'Flag not found in post #1')
            
            #print(f'[+] Found flag: {flag_value[:50]}...')
            return flag_value
            
        except Exception as e:
            self.checker.cquit(Status.MUMBLE, 'get_flag failed', str(e))


    def _selenium_check_post1_with_cookies(self, cookies, expected_flag):
        """
        Selenium: 
        1. Устанавливает куки из requests-сессии
        2. Открывает пост #1
        3. Ищет expected_flag в приватных комментариях (внутри .wp-block-comment-content)
        """
        from selenium.webdriver.common.by import By
        import time
        
        #print(f'[*] Starting Selenium check for post #1 with cookies...')
        driver = None
        
        try:
            driver = self._init_selenium(headless=True)
            driver.implicitly_wait(0)
            
            # Устанавливаем куки
            driver.get(self.base_url)
            time.sleep(0.5)
            
            for name, value in cookies.items():
                try:
                    driver.add_cookie({'name': name, 'value': value, 'domain': self.checker.host})
                except:
                    pass
            
            # Открываем пост #1
            post1_url = f'{self.base_url}/?p=1'
            driver.get(post1_url)
            time.sleep(1)
            
            # Прокрутка вниз
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            
            # Ищем приватные комментарии с флагом
            # Сначала ищем все приватные комментарии
            private_comments = driver.find_elements(By.CSS_SELECTOR, "li.private-comment")
            #print(f'[DEBUG] Found {len(private_comments)} private comments')
            
            for comment in private_comments:
                try:
                    # Ищем контент внутри приватного комментария
                    content_elem = comment.find_element(By.CSS_SELECTOR, ".wp-block-comment-content")
                    text = content_elem.text.strip()
                    #print(f'[DEBUG] Private comment content: {text[:50]}...')
                    
                    if expected_flag and expected_flag in text:
                        #print(f'[+] FOUND FLAG: {text[:50]}...')
                        return text
                except:
                    # Если нет .wp-block-comment-content, берем весь текст комментария
                    text = comment.text.strip()
                    #print(f'[DEBUG] Full comment text: {text[:80]}...')
                    if expected_flag and expected_flag in text:
                        #print(f'[+] FOUND FLAG: {text[:50]}...')
                        return text
            
            # Fallback: ищем по всей странице
            if expected_flag and expected_flag in driver.page_source:
                #print(f'[+] FOUND FLAG in page source')
                return expected_flag
            return None
            
        except Exception as e:
            self.checker.cquit(Status.MUMBLE, 'check post 1 failed', str(e))
            raise
            
        finally:
            if driver:
                driver.quit()
                #print('[*] Browser closed')

    def _selenium_fast_browse(self, username, password, posts, expected_flag):
        """
        Асинхронный просмотр постов в Selenium с явной передачей куки для каждого поста.
        """
        from selenium.webdriver.common.by import By
        import time
        import requests
        
        #print(f"Starting fast Selenium browse for {len(posts)} posts...")
        driver = None
        foundflag = None
        
        try:
            # 1. Получаем свежие куки через проверенный requests-логин
            session = self.login(username, password)
            auth_cookies = session.cookies.get_dict()
            #print(f"Got {len(auth_cookies)} auth cookies from requests")
            #print(f"Cookies: {list(auth_cookies.keys())}")
            
            # 2. Инициализируем драйвер
            driver = self._init_selenium(headless=True)
            driver.set_page_load_timeout(30)
            
            # 3. Сначала открываем базовый URL для инициализации домена
            driver.get(self.base_url)
            time.sleep(1)
            
            # 4. Устанавливаем куки на базовый домен
            for name, value in auth_cookies.items():
                try:
                    driver.add_cookie({
                        'name': name,
                        'value': value,
                        'domain': self.checker.host,  # Точный домен
                        'path': '/'
                    })
                    #print(f"[+] Added cookie: {name}")
                except Exception as e:
                    self.checker.cquit(Status.MUMBLE, 'Failed to add cookie', str(e))
                    #print(f"[!] Failed to add cookie {name}: {e}")
            
            # Проверяем установку куки
            current_cookies = driver.get_cookies()
            #print(f"[DEBUG] Cookies after setup: {[c['name'] for c in current_cookies]}")
            
            # 5. Цикл по постам
            for post in posts:
                if foundflag:
                    break
                    
                post_id = post.get('id')
                # Используем относительный URL или строим свой
                postlink = f"{self.base_url}/?p={post_id}"
                
                #print(f"\n--- Processing post {post_id} ---")
                
                # 6. Переходим на пост (куки уже установлены на домен)
                try:
                    driver.get(postlink)
                    time.sleep(2)
                except Exception as e:
                    self.checker.cquit(Status.MUMBLE, 'Cant get post {post_id}', str(e))
                    #print(f"[!] Failed to load post {post_id}: {e}")
                    continue
                
                # 7. Проверяем, не сбросилась ли авторизация (редирект на логин)
                current_url = driver.current_url
                #print(f"[DEBUG] Current URL: {current_url}")
                
                if 'login' in current_url.lower() or 'page_id=5' in current_url:
                    #print("[!] Redirected to login - session lost, restoring cookies...")
                    # Восстанавливаем куки
                    driver.get(self.base_url)
                    time.sleep(0.5)
                    for name, value in auth_cookies.items():
                        try:
                            driver.add_cookie({
                                'name': name,
                                'value': value,
                                'domain': self.checker.host,
                                'path': '/'
                            })
                        except:
                            pass
                    # Пробуем снова
                    driver.get(postlink)
                    time.sleep(2)
                    
                    # Проверяем еще раз
                    if 'login' in driver.current_url.lower():
                        #print("[!] Still on login page, skipping post")
                        continue
                
                # 8. Проверяем авторизацию по наличию logout или приветствия
                page_source = driver.page_source.lower()
                is_logged_in = any([
                    'logout' in page_source,
                    'привет' in page_source,
                    'welcome' in page_source,
                    'личный кабинет' in page_source,
                    'dashboard' in page_source
                ])
                #print(f"[DEBUG] Logged in indicators: {is_logged_in}")
                
                # 9. Прокрутка страницы для загрузки комментариев
                try:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1)
                except Exception as e:
                    self.checker.cquit(Status.MUMBLE, 'Reading posts error', str(e))
                    #print(f"[!] Scroll error: {e}")
                
            
            #print(f"\n[+] Finished browsing {len(posts)} posts")
            return foundflag
            
        except Exception as e:
            self.checker.cquit(Status.MUMBLE, 'Error reading posts', str(e))
            #print(f"[-] Selenium error: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            if driver:
                driver.quit()
                #print("[*] Browser closed.")


    def _get_all_posts(self):
        """Получает все посты через REST API (публичные)"""
        rest_url = f'{self.base_url}/index.php?rest_route=/wp/v2/posts&per_page=100'
        
        r = requests.get(rest_url, timeout=10)
        if r.status_code == 200:
            return r.json()
        return []


    def _selenium_browse_posts(self, username, password, posts, expected_flag):
        """
        Selenium: 
        1. Логинится
        2. Ищет флаг в приватных комментариях ВО ВСЕХ постах (не только #1)
        3. В каждом посте пишет случайный комментарий
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        import time
        
        #print(f'[*] Starting Selenium to browse {len(posts)} posts...')
        driver = None
        found_flag = None
        
        # Селекторы для приватных комментариев (обновленные)
        private_selectors = [
            ".private-comment",
            ".comment.private", 
            "li.private-comment",
            ".wp-block-comment-content",  # контент комментария
            ".comment-content"
        ]
        
        # Селекторы для формы комментария
        form_selectors = [  # ← исправлено: form_selectors, не form_selecters
            "#commentform textarea",
            "form.comment-form textarea",
            "#respond form textarea",
            "textarea#comment",
            "textarea[name='comment']"
        ]
        
        try:
            driver = self._init_selenium(headless=True)
            
            # Логинимся через фронтенд
            login_url = f'{self.base_url}{WP_PATHS["login"]}'
            #print(f'[*] Logging in via Selenium')
            
            driver.get(login_url)
            
            wait = WebDriverWait(driver, 10)
            username_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
            password_field = driver.find_element(By.ID, "password")
            submit_btn = driver.find_element(By.CSS_SELECTOR, "input[type='submit']")
            
            username_field.send_keys(username)
            password_field.send_keys(password)
            submit_btn.click()
            
            time.sleep(3)
            
            # Проверяем успешность входа
            if 'login' in driver.current_url.lower() or 'page_id=5' in driver.current_url:
                page_source = driver.page_source.lower()
                if 'logout' not in page_source and 'привет' not in page_source:
                    raise Exception('Selenium login failed')
            
            #print('[+] Selenium login successful')
            
            # Проходим по ВСЕМ постам в цикле, ищем флаг в каждом
            for post in posts:
                post_id = post.get('id')
                post_link = post.get('link') or f'{self.base_url}/?p={post_id}'
                
               #print(f'[*] Opening post #{post_id}: {post_link}')
                driver.get(post_link)
                time.sleep(2)
                
                # Скроллим вниз к комментариям
                height = driver.execute_script("return document.body.scrollHeight")
                step = 500
                current = 0
                
                while current < height:
                    current += step
                    driver.execute_script(f"window.scrollTo(0, {current});")
                    time.sleep(0.3)
                
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                
                # ИЩЕМ ПРИВАТНЫЙ КОММЕНТАРИЙ С ФЛАГОМ в этом посте
                #print(f'[*] Checking for private comments in post #{post_id}...')
                
                for selector in private_selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        #print(f'[DEBUG] Found {len(elements)} elements with selector {selector}')
                        
                        for elem in elements:
                            text = elem.text.strip()
                            #print(f'[DEBUG] Element text: {text[:100]}...')
                            
                            # Проверяем содержит ли текст ожидаемый флаг
                            if text and expected_flag and expected_flag in text:
                                #print(f'[+] FOUND FLAG in post #{post_id}: {text[:50]}...')
                                found_flag = text
                                break
                            # Или проверяем что это похоже на флаг (длина, формат)
                            elif text and len(text) > 5 and not found_flag:
                                None
                                #print(f'[DEBUG] Potential flag: {text[:50]}...')
                                
                    except Exception as e:
                        self.checker.cquit(Status.MUMBLE, 'Error with selector {selector}', str(e))
                        #print(f'[DEBUG] Error with selector {selector}: {e}')
                        continue
                    
                    if found_flag:
                        break
                
                # Пишем случайный комментарий в этот пост
                random_comment = self._get_random_comment()
                #print(f'[*] Posting random comment to post #{post_id}: {random_comment[:30]}...')
                
                comment_posted = False
                for selector in form_selectors:  # ← исправлено: form_selectors
                    try:
                        comment_field = driver.find_element(By.CSS_SELECTOR, selector)
                        submit_btn = driver.find_element(By.CSS_SELECTOR, "input[type='submit'], button[type='submit'], #submit")
                        
                        comment_field.clear()
                        comment_field.send_keys(random_comment)
                        submit_btn.click()
                        comment_posted = True
                        #print(f'[+] Random comment posted to post #{post_id}')
                        time.sleep(2)
                        break
                    except Exception as e:
                        self.checker.cquit(Status.MUMBLE, 'Could not post with selector {selector}', str(e))
                        #print(f'[DEBUG] Could not post with selector {selector}: {e}')
                        continue
                
                if not comment_posted:
                    #print(f'[!] Could not post comment to post #{post_id}')
                
                # Если нашли флаг, продолжаем писать комменты в остальные посты
                # но можно и выйти: if found_flag: break
            
            #print(f'[+] Finished browsing all posts')
                    return found_flag
            
        except Exception as e:
            self.checker.cquit(Status.MUMBLE, 'Error while reading posts', str(e))
            #print(f'[-] Selenium error: {e}')
            raise
            
        finally:
            if driver:
                driver.quit()
                #print('[*] Browser closed')

    

    def _init_selenium(self, headless=True):
        """Инициализация Selenium драйвера"""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        
        chrome_options = Options()
        
        if headless:
            chrome_options.add_argument("--headless")
        
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        chrome_bin = os.getenv('CHROME_BIN')
        chromedriver_path = os.getenv('CHROMEDRIVER_PATH')
        
        if chrome_bin and chromedriver_path:
            chrome_options.binary_location = chrome_bin
            service = Service(chromedriver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
        else:
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                from selenium.webdriver.chrome.service import Service as ChromeService
                service = ChromeService(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
            except ImportError:
                raise Exception("Install: pip install webdriver-manager")
        
        driver.implicitly_wait(10)
        return driver


def main():
    """
    Тестовый запуск чекера без аргументов командной строки.
    """
    import sys
    import os
    
    DEFAULT_HOST = "localhost"
    DEFAULT_PORT = 8080
    
    host = os.environ.get('WP_HOST', DEFAULT_HOST)
    port = int(os.environ.get('WP_PORT', str(DEFAULT_PORT)))
    
    test_flag_id = "test_flag_12345"
    test_flag = "CTF{test_flag_12345678901234567890}"
    
    '''
    print("=" * 60)
    print("WordPress CTF Checker - Test Mode")
    print("=" * 60)
    print(f"Target: http://{host}:{port}")
    print(f"Test Flag ID: {test_flag_id}")
    print(f"Test Flag: {test_flag}")
    print("=" * 60)
    '''
    
    class TestChecker:
        def __init__(self, host):
            self.host = host
            
        def cquit(self, status, public='', private=''):
            #print(f"[Status: {status}] {public}")
            if private:
                None 
                #print(f"  Private: {private}")
            sys.exit(0)
            
        def check_response(self, response, message):
            if response.status_code != 200:
                self.cquit(Status.DOWN, message, f"Status: {response.status_code}")
    
    checker = TestChecker(host)
    machine = CheckMachine(checker)
    
    machine.base_url = f'http://{host}:{port}'
    
    #print("\n[1] Testing PING...")
    try:
        machine.ping()
       # print("[+] PING OK - WordPress is accessible")
    except SystemExit:
        #print("[-] PING FAILED")
        return
    except Exception as e:
        #print(f"[-] PING ERROR: {e}")
        return
    
    #print("\n[2] Testing PUT FLAG...")
    try:
        result = machine.put_flag(test_flag_id, test_flag)
       #print(f"[+] PUT OK - Returned: {result}")
        flag_id = result
    except SystemExit:
        #print(f"[-] PUT FAILED")
        return
    except Exception as e:
        #print(f"[-] PUT ERROR: {e}")
        return
    
    #print("\n[3] Testing GET FLAG...")
    try:
        retrieved_flag = machine.get_flag(flag_id, test_flag)
        #print(f"[+] GET OK - Retrieved: {retrieved_flag}")
        
        if retrieved_flag == test_flag:
            None
            #print("[+] FLAG VERIFICATION: SUCCESS - Flags match!")
        else:
            None
            #print(f"[-] FLAG VERIFICATION: FAILED")
            #print(f"    Expected: {test_flag}")
            #print(f"    Got:      {retrieved_flag}")
    except SystemExit:
        #print(f"[-] GET FAILED")
        return
    except Exception as e:
        #print(f"[-] GET ERROR: {e}")
        return
    
    '''
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)
    '''

if __name__ == '__main__':
    import sys
    if len(sys.argv) <= 1:
        main()
    else:
        None
        #print("Use: python3 checker.py <action> <host> <flag_id> <flag> <vuln>")
        #print("Or run without arguments for test mode")