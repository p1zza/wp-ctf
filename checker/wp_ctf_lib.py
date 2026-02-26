import requests
from checklib import *
import re
import os
import json

PORT = 8080 

# Файл для хранения паролей пользователей (временное решение для тестирования)
CREDENTIALS_FILE = '/tmp/wp_ctf_credentials.json'

WP_PATHS = {
    'home': '/',
    'login': '/wp-login.php',
    'admin': '/wp-admin/',
    'register': '/wp-login.php?action=register',
    'logout': '/wp-login.php?action=logout',
    'posts': '/?p=1',  
    'xmlrpc': '/xmlrpc.php'
}

class CheckMachine:
    def __init__(self, checker):
        self.checker = checker
        self.base_url = f'http://{self.checker.host}:{PORT}'

    def _save_credentials(self, username, password):
        """Сохраняем credentials для использования в get"""
        creds = {}
        if os.path.exists(CREDENTIALS_FILE):
            try:
                with open(CREDENTIALS_FILE, 'r') as f:
                    creds = json.load(f)
            except:
                pass
        creds[username] = password
        with open(CREDENTIALS_FILE, 'w') as f:
            json.dump(creds, f)

    def _get_credentials(self, username):
        """Получаем сохраненный пароль"""
        if os.path.exists(CREDENTIALS_FILE):
            try:
                with open(CREDENTIALS_FILE, 'r') as f:
                    creds = json.load(f)
                    return creds.get(username)
            except:
                pass
        return None

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
        
        # Проверяем наличие auth cookie
        has_auth = False
        for cookie in session.cookies:
            if 'wordpress_logged_in' in cookie.name:
                has_auth = True
                break
        
        if not has_auth:
            raise Exception('No wordpress_logged_in cookie found. Login failed.')
        
        print(f'Login successful. Got cookies: {[c.name for c in session.cookies]}')
        return session

    def register(self, username, password, email, role='author'):    
        admin_url = f'{self.base_url}/wp-admin'
        user_new_url = f'{admin_url}/user-new.php'
        
        session = requests.Session()

        admin_session = self.login_admin()
        # Копируем cookies из admin_session в новую сессию
        for cookie in admin_session.cookies:
            session.cookies.set_cookie(cookie)
        
        r = session.get(user_new_url, timeout=10)
        
        if r.status_code != 200:
            raise Exception(f'Failed to load user-new.php: {r.status_code}')
        
        if 'wp-login.php' in r.url:
            raise Exception('Admin authentication required')
        
        nonce_match = re.search(r'name="_wpnonce_create-user" value="([^"]+)"', r.text)
        if not nonce_match:
            nonce_match = re.search(r'id="_wpnonce_create-user"[^>]*value="([^"]+)"', r.text)
        
        if not nonce_match:
            raise Exception('Could not find _wpnonce_create-user in page')
        
        nonce = nonce_match.group(1)
        print(f'Got nonce: {nonce}')
        
        data = {
            'action': 'createuser',
            '_wpnonce_create-user': nonce,
            '_wp_http_referer': '/wp-admin/user-new.php',
            'user_login': username,
            'email': email,
            'first_name': '',
            'last_name': '',
            'url': '',
            'pass1': password,
            'pass2': password,
            'pw_weak': 'on',  
            'send_user_notification': '0',  
            'role': role,
            'createuser': 'Add User'
        }
        
        headers = {
            'Origin': self.base_url,
            'Referer': user_new_url,
        }
        
        r = session.post(user_new_url, data=data, headers=headers, timeout=10)
        
        if r.status_code != 200:
            raise Exception(f'Failed to create user: {r.status_code}')
        
        # Проверяем успешное создание
        if 'user created' in r.text.lower() or 'пользователь создан' in r.text.lower():
            print(f'User {username} created successfully')
            return True
        
        # Проверяем, что пользователь уже существует
        if 'user already exists' in r.text.lower() or 'username уже существует' in r.text.lower() or \
           'email already exists' in r.text.lower() or 'email уже существует' in r.text.lower() or \
           'This username is already registered' in r.text or 'This email is already registered' in r.text:
            print(f'User {username} already exists, will try to login')
            return 'exists'  # Возвращаем специальный статус
        
        error_match = re.search(r'<div[^>]*class="[^"]*error[^"]*"[^>]*>(.*?)</div>', r.text, re.DOTALL)
        if error_match:
            error_text = re.sub(r'<[^>]+>', '', error_match.group(1))
            raise Exception(f'WordPress error: {error_text.strip()}')
        
        if 'wp-login.php' not in r.url:
            print(f'User {username} probably created (no error detected)')
            return True
        
        raise Exception('User creation failed - redirected to login')
    
    def login(self, username, password):
        """Возвращает Session с установленными cookies вместо dict"""
        login_url = f'{self.base_url}{WP_PATHS["login"]}'

        session = requests.Session()
        r = session.get(login_url, timeout=5)
        self.checker.check_response(r, 'Cannot load login page')

        data = {
            'log': username,
            'pwd': password,
            'rememberme': 'forever',
            'wp-submit': 'Log In',
            'redirect_to': f'{self.base_url}{WP_PATHS["admin"]}',
            'testcookie': '1'
        }

        r = session.post(login_url, data=data, allow_redirects=False, timeout=10)

        # Проверяем наличие auth cookie
        has_auth = False
        for cookie in session.cookies:
            if 'wordpress_logged_in' in cookie.name:
                has_auth = True
                break

        if not has_auth:
            self.checker.cquit(Status.MUMBLE, 'Login failed - no auth cookie')

        return session

    def put_flag(self, flag_id, flag, vuln=None):
        username = f'user_{flag_id[:8]}'
        password = flag[:20]  
        email = f'{username}@ctf.local'
        
        # Сохраняем credentials для get
        self._save_credentials(username, password)
        
        try:
            result = self.register(username, password, email)
            
            # Если пользователь уже существует, пробуем войти
            if result == 'exists':
                print(f'User {username} exists, trying to login...')
                try:
                    session = self.login(username, password)
                    print(f'Login successful for existing user {username}')
                except Exception as login_err:
                    # Если не удалось войти, возможно пароль другой
                    # Пробуем создать пост с текущей сессией (если есть)
                    raise Exception(f'Failed to login existing user: {login_err}')
            else:
                # Новый пользователь - логинимся
                session = self.login(username, password)
            
            # Получаем nonce из HTML админки
            r = session.get(f'{self.base_url}/wp-admin/post-new.php', timeout=10)
            
            nonce = None
            nonce_match = re.search(r'"restNonce":"([^"]+)"', r.text)
            if nonce_match:
                nonce = nonce_match.group(1)
            else:
                nonce_match = re.search(r'wpApiSettings\s*=\s*\{[^}]*"nonce"\s*:\s*"([^"]+)"', r.text)
                if nonce_match:
                    nonce = nonce_match.group(1)
            
            if not nonce:
                raise Exception('Could not get REST API nonce')
            
            print(f'Got REST nonce: {nonce}')
            
            # Создаем пост через REST API
            rest_url = f'{self.base_url}/index.php?rest_route=/wp/v2/posts'
            post_data = {
                'title': flag_id,
                'content': flag,
                'status': 'private'
            }
            
            headers = {
                'X-WP-Nonce': nonce,
                'Content-Type': 'application/json'
            }
            
            r = session.post(rest_url, json=post_data, headers=headers, timeout=10)
            
            if r.status_code in [200, 201]:
                response_json = r.json()
                post_id = response_json.get('id')
                if post_id:
                    print(f'Post created via REST API with ID: {post_id}')
                    return f'{username}:{post_id}'
                else:
                    raise Exception(f'No id in response')
            else:
                raise Exception(f'REST API error: {r.status_code} - {r.text[:200]}')
            
        except Exception as e:
            self.checker.cquit(Status.MUMBLE, 'put_flag failed', str(e))

    def get_flag(self, flag_id, flag=None, vuln=None):
        parts = flag_id.split(':')
        username = parts[0]
        post_id = parts[1] if len(parts) > 1 else None

        try:
            if not post_id:
                self.checker.cquit(Status.CORRUPT, 'No post_id in flag_id')

            password = self._get_credentials(username)
            if not password:
                if flag:
                    password = flag[:20]
                    self._save_credentials(username, password)  
                else:
                    post_url = f'{self.base_url}/?p={post_id}'
                    r = requests.get(post_url, timeout=10)
                    
                    match = re.search(r'<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>(.*?)</div>', r.text, re.DOTALL | re.IGNORECASE)
                    if match:
                        content = match.group(1)
                        flag_found = re.sub(r'<[^>]+>', '', content)
                        flag_found = flag_found.strip()
                        if flag_found:
                            return flag_found
                    
                    self.checker.cquit(Status.CORRUPT, 'No credentials found for user and flag not public')

            session = self.login(username, password)
            
            r = session.get(f'{self.base_url}/wp-admin/post-new.php', timeout=10)
            nonce_match = re.search(r'"restNonce":"([^"]+)"', r.text)
            if not nonce_match:
                nonce_match = re.search(r'wpApiSettings\s*=\s*\{[^}]*"nonce"\s*:\s*"([^"]+)"', r.text)
            
            nonce = nonce_match.group(1) if nonce_match else None
            
            rest_url = f'{self.base_url}/index.php?rest_route=/wp/v2/posts/{post_id}'
            headers = {}
            if nonce:
                headers['X-WP-Nonce'] = nonce
            
            r = session.get(rest_url, headers=headers, timeout=10)
            
            if r.status_code == 200:
                post_data = r.json()
                content = post_data.get('content', {}).get('rendered', '')
                flag_found = re.sub(r'<[^>]+>', '', content)
                flag_found = flag_found.strip()
                if flag_found:
                    return flag_found
            
            post_url = f'{self.base_url}/?p={post_id}'
            r = session.get(post_url, timeout=10)
            
            match = re.search(r'<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>(.*?)</div>', r.text, re.DOTALL | re.IGNORECASE)
            if match:
                content = match.group(1)
                flag_found = re.sub(r'<[^>]+>', '', content)
                flag_found = flag_found.strip()
                if flag_found:
                    return flag_found

            self.checker.cquit(Status.CORRUPT, 'Flag not found in post')

        except Exception as e:
            self.checker.cquit(Status.MUMBLE, 'get_flag failed', str(e))

    def check_flag_in_post(self, post_id, expected_flag):
        post_url = f'{self.base_url}/?p={post_id}'
        r = requests.get(post_url, timeout=10)
        
        if expected_flag in r.text:
            return True
        return False


def main():
    """
    Тестовый запуск чекера без аргументов командной строки.
    Использует localhost:8080 как цель по умолчанию.
    Можно переопределить через переменную окружения WP_HOST или изменить DEFAULT_HOST ниже.
    """
    import sys
    import os
    
    # НАСТРОЙКА: измените здесь хост и порт при необходимости
    DEFAULT_HOST = "localhost"  # <-- Измените на IP вашего WordPress
    DEFAULT_PORT = 8080         # <-- Измените порт если нужно
    
    # Или задайте через переменную окружения: export WP_HOST="192.168.1.100"
    host = os.environ.get('WP_HOST', DEFAULT_HOST)
    port = int(os.environ.get('WP_PORT', str(DEFAULT_PORT)))
    
    test_flag_id = "test_flag_12345"
    test_flag = "CTF{test_flag_12345678901234567890}"
    
    print("=" * 60)
    print("WordPress CTF Checker - Test Mode")
    print("=" * 60)
    print(f"Target: http://{host}:{port}")
    print(f"Test Flag ID: {test_flag_id}")
    print(f"Test Flag: {test_flag}")
    print("=" * 60)
    print()
    print("Чтобы изменить хост, задайте переменную окружения:")
    print('  export WP_HOST="your-host-ip"')
    print('  export WP_PORT="8080"')
    print("=" * 60)
    
    class TestChecker:
        def __init__(self, host):
            self.host = host
            
        def cquit(self, status, public='', private=''):
            print(f"[Status: {status}] {public}")
            if private:
                print(f"  Private: {private}")
            sys.exit(0)
            
        def check_response(self, response, message):
            if response.status_code != 200:
                self.cquit(Status.DOWN, message, f"Status: {response.status_code}")
    
    checker = TestChecker(host)
    machine = CheckMachine(checker)
    
    # Переопределяем base_url с правильным портом
    machine.base_url = f'http://{host}:{port}'
    
    print("\n[1] Testing PING...")
    try:
        machine.ping()
        print("[+] PING OK - WordPress is accessible")
    except SystemExit:
        print("[-] PING FAILED")
        return
    except Exception as e:
        print(f"[-] PING ERROR: {e}")
        return
    
    print("\n[2] Testing PUT FLAG...")
    try:
        result = machine.put_flag(test_flag_id, test_flag)
        print(f"[+] PUT OK - Returned: {result}")
        flag_id = result
    except SystemExit:
        print(f"[-] PUT FAILED")
        return
    except Exception as e:
        print(f"[-] PUT ERROR: {e}")
        return
    
    print("\n[3] Testing GET FLAG...")
    try:
        retrieved_flag = machine.get_flag(flag_id, test_flag)  # Передаем test_flag как второй аргумент
        print(f"[+] GET OK - Retrieved: {retrieved_flag}")
        
        if retrieved_flag == test_flag:
            print("[+] FLAG VERIFICATION: SUCCESS - Flags match!")
        else:
            print(f"[-] FLAG VERIFICATION: FAILED")
            print(f"    Expected: {test_flag}")
            print(f"    Got:      {retrieved_flag}")
    except SystemExit:
        print(f"[-] GET FAILED")
        return
    except Exception as e:
        print(f"[-] GET ERROR: {e}")
        return
    
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == '__main__':
    import sys
    if len(sys.argv) <= 1:
        main()
    else:
        print("Use: python3 checker.py <action> <host> <flag_id> <flag> <vuln>")
        print("Or run without arguments for test mode")