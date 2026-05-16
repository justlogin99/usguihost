import os
import sys
import time
import random
import requests
import tempfile
import subprocess
import shutil
import re
import datetime
from xvfbwrapper import Xvfb
from DrissionPage import ChromiumPage, ChromiumOptions

try:
    import speech_recognition as sr
    from pydub import AudioSegment
except ImportError:
    pass

# ==============================================================================
# Telegram 通知模块
# ==============================================================================
def send_tg_message(token, chat_id, message):
    if not token or not chat_id:
        print("⚠️ 未配置 TG_TOKEN 或 TG_CHAT_ID，跳过通知。")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    safe_message = message.replace('<b>', '').replace('</b>', '')
    payload = {"chat_id": chat_id, "text": safe_message, "parse_mode": "None"}
    try:
        requests.post(url, json=payload, timeout=10)
        print("✅ Telegram 通知发送成功！")
    except Exception as e:
        print(f"❌ Telegram 通知请求异常: {e}")

# ==============================================================================
# 语音验证码破解模块 (保持不变)
# ==============================================================================
class RecaptchaAudioSolver:
    def __init__(self, page):
        self.page = page
        self.log_func = print

    def log(self, msg):
        self.log_func(f"[Solver] {msg}")

    def human_type(self, ele, text):
        ele.click()
        time.sleep(random.uniform(0.1, 0.3))
        ele.clear()
        for char in text:
            ele.input(char, clear=False)
            time.sleep(random.uniform(0.08, 0.25))
        time.sleep(random.uniform(0.3, 0.8))

    def solve(self, bframe):
        self.log("🎧 启动过盾流程...")
        try:
            audio_btn = bframe.ele('#recaptcha-audio-button', timeout=3)
            if audio_btn:
                self.page.actions.move_to(audio_btn, duration=random.uniform(0.5, 1.2))
                time.sleep(random.uniform(0.2, 0.5))
                audio_btn.click()
                self.log("🖱️ 点击了音频破解按钮")
            else:
                self.log("❌ 未找到验证按钮，可能被 Google 屏蔽")
                return False

            time.sleep(random.uniform(3, 5))
            src = None
            for attempt in range(3):
                src = self.get_audio_source(bframe)
                if src: break
                err_msg = bframe.ele('.rc-audiochallenge-error-message', timeout=1)
                if err_msg and err_msg.states.is_displayed:
                    error_txt = err_msg.text
                    if error_txt and "try again" not in error_txt.lower():
                        self.log(f"⛔ Google 拒绝提供音频: {error_txt}")
                self.log(f"⚠️ 第 {attempt+1} 次获取TOKEN失败，尝试点击刷新...")
                reload_btn = bframe.ele('#recaptcha-reload-button', timeout=2)
                if reload_btn:
                    self.page.actions.move_to(reload_btn, duration=random.uniform(0.3, 0.8))
                    time.sleep(random.uniform(0.2, 0.5))
                    reload_btn.click()
                    time.sleep(random.uniform(4, 7))

            if not src:
                self.log("❌ 最终无法获取链接 (IP 可能被暂时风控)")
                return False

            self.log("📥 正在下载并处理音频数据...")
            r = requests.get(src, timeout=15)
            with open("audio.mp3", 'wb') as f:
                f.write(r.content)

            try:
                sound = AudioSegment.from_mp3("audio.mp3")
                sound.export("audio.wav", format="wav")
            except Exception as e:
                self.log(f"❌ ffmpeg 转码失败: {e}")
                return False

            key_text = ""
            recognizer = sr.Recognizer()
            with sr.AudioFile("audio.wav") as source:
                audio_data = recognizer.record(source)
            try:
                key_text = recognizer.recognize_google(audio_data)
                self.log(f"🗣️ 识别结果: [{key_text}]")
            except Exception as e:
                self.log("❌ 语音识别失败 (可能音频含糊或引擎无响应)")
                return False

            input_box = bframe.ele('#audio-response', timeout=2)
            if input_box:
                self.human_type(input_box, key_text)

            verify_btn = bframe.ele('#recaptcha-verify-button', timeout=2)
            if verify_btn:
                self.page.actions.move_to(verify_btn, duration=random.uniform(0.5, 1.0))
                time.sleep(random.uniform(0.2, 0.5))
                verify_btn.click()
                self.log("🚀 提交验证...")
                time.sleep(4)

                err_check = bframe.ele('.rc-audiochallenge-error-message', timeout=1)
                if err_check and err_check.states.is_displayed:
                    self.log(f"❌ 验证未通过: {err_check.text}")
                    return False
                return True

            return False
        except Exception as e:
            self.log(f"💥 异常: {e}")
            return False
        finally:
            for f in ["audio.mp3", "audio.wav"]:
                if os.path.exists(f): os.remove(f)

    def get_audio_source(self, bframe):
        try:
            link1 = bframe.ele('.rc-audiochallenge-ndownload-link', timeout=0.5)
            if link1: return link1.attr('href')
            link2 = bframe.ele('xpath://a[contains(@href, ".mp3")]', timeout=0.5)
            if link2: return link2.attr('href')
            audio_src = bframe.ele('#audio-source', timeout=0.5)
            if audio_src: return audio_src.attr('src')
            return None
        except:
            return None

# ==============================================================================
# 核心续期业务逻辑 (纯净版 - 每次调用都是独立环境)
# ==============================================================================
def renew_host2play(url, proxy_url=None, user_data_dir=None):
    print("启动 Xvfb 虚拟桌面...")
    vdisplay = Xvfb(width=1280, height=720, colordepth=24)
    vdisplay.start()
    success = False
    msg = ""
    page = None
    try:
        co = ChromiumOptions()
        co.set_browser_path('/usr/bin/google-chrome')
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-dev-shm-usage')
        co.set_argument('--disable-gpu')
        co.set_argument('--disable-setuid-sandbox')
        co.set_argument('--disable-software-rasterizer')
        co.set_argument('--disable-extensions')
        co.set_argument('--no-first-run')
        co.set_argument('--no-default-browser-check')
        co.set_argument('--disable-popup-blocking')
        co.set_argument('--window-size=1280,720')
        co.set_argument('--disable-blink-features=AutomationControlled') # 关键反检测

        if user_data_dir:
            co.set_user_data_path(user_data_dir)
        co.auto_port()
        co.headless(False)

        if proxy_url:
            if "://" not in proxy_url:
                proxy_url = f"http://{proxy_url}"
            co.set_proxy(proxy_url)

        page = ChromiumPage(co)

        def take_screenshot(name):
            try:
                page.get_screenshot(name=f"{name}.png")
            except Exception as e:
                print(f"⚠️ 截图失败: {e}")

        print("🛡️ 注入 WebGL 硬件欺骗与反侦察指纹...")
        page.add_init_js("""
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel(R) UHD Graphics 630';
                return getParameter.apply(this, [parameter]);
            };
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
        """)

        print(f"🌐 访问续期目标网址: {url}")
        page.get(url, retry=3)
        time.sleep(random.uniform(5, 8))
        take_screenshot(f"1_page_loaded")

        print("🧹 清理遮挡元素...")
        page.run_js("""
            const cssSelectors = ['ins.adsbygoogle', 'iframe[src*="ads"]', '.modal-backdrop'];
            cssSelectors.forEach(sel => { document.querySelectorAll(sel).forEach(el => el.remove()); });
        """)
        time.sleep(2)

        consent_btn = page.ele('tag:button@@text():Consent', timeout=2)
        if consent_btn:
            consent_btn.click()
            time.sleep(3)

        print("🤸 积累真实的鼠标轨迹和滚动数据...")
        for _ in range(3):
            scroll_y = random.randint(200, 600)
            page.scroll.down(scroll_y)
            time.sleep(random.uniform(0.5, 1.5))
            page.actions.move(random.randint(100, 800), random.randint(100, 500))
            time.sleep(random.uniform(0.5, 1.0))
        time.sleep(random.uniform(1.0, 2.0))

        print("🖱️ 打开续期弹窗...")
        renew_btn1 = page.ele('xpath://button[contains(text(), "Renew server")]', timeout=3)
        if renew_btn1:
            try: renew_btn1.click()
            except: renew_btn1.click(by_js=True)
        else:
            page.run_js("document.querySelectorAll('button').forEach(b => {if(b.textContent.includes('Renew server')) b.click();});")
        time.sleep(3)

        for _ in range(8):
            if page.ele('text:Expires in:', timeout=0.5) or page.ele('text:Deletes on:', timeout=0.5):
                break
            time.sleep(1)

        renew_btn2 = page.ele('xpath://button[contains(text(), "Renew server")]', timeout=2)
        if renew_btn2:
            try: renew_btn2.click()
            except: renew_btn2.click(by_js=True)
        time.sleep(random.uniform(7, 10))
        take_screenshot(f"2_before_captcha")

        solved_captcha = False
        anchor_frame = page.get_frame('xpath://iframe[contains(@src, "recaptcha/api2/anchor")]', timeout=5)
        if anchor_frame:
            print("✅ 锁定 reCAPTCHA 框架")
            anchor_box = None
            for _ in range(20):
                anchor_box = anchor_frame.ele('#recaptcha-anchor', timeout=1)
                if anchor_box: break
                time.sleep(1)

            if not anchor_box:
                msg = "❌ host2 reCAPTCHA checkbox 超时"
                return success, msg

            print("🖱️ 物理模拟点击 reCAPTCHA checkbox...")
            page.actions.move_to(anchor_box, duration=random.uniform(0.5, 1.5))
            time.sleep(random.uniform(0.2, 0.6))
            anchor_box.click()
            time.sleep(random.uniform(4, 7))

            checked = anchor_box.attr('aria-checked')
            if checked == 'true':
                print("✅ reCAPTCHA 已自动验证通过！")
                solved_captcha = True
            else:
                print("🎲 需要手动破解音频验证码...")
                bframe = page.get_frame('xpath://iframe[contains(@src, "recaptcha/api2/bframe")]', timeout=5)
                if bframe:
                    solver = RecaptchaAudioSolver(page)
                    if solver.solve(bframe):
                        solved_captcha = True
                        take_screenshot(f"3_captcha_solved")
                    else:
                        take_screenshot(f"3_error_captcha_failed")
                        msg = "❌ host2play 音频验证码破解失败"
                else:
                    msg = "❌ host2 未找到 reCAPTCHA bframe"
        else:
            print("⚠️ 未发现 reCAPTCHA iframe")
            msg = "❌ host2 未找到 reCAPTCHA 验证码区域"

        if solved_captcha:
            print("🚀 验证完成，点击最终 Renew...")
            final_btn = page.ele('xpath://button[normalize-space(text())="Renew"]', timeout=3)
            if final_btn:
                try: final_btn.click()
                except: final_btn.click(by_js=True)
                time.sleep(10)
                take_screenshot(f"4_final_success")
                msg = "🎉 host2play 续期操作成功！"
                success = True
            else:
                msg = "❌ host2play 找不到最终 Renew 按钮"
        else:
            if "操作成功" not in msg:
                msg = "❌ host2play 无法通过 reCAPTCHA"

    except Exception as e:
        msg = f"💥 host2play 运行异常: {str(e)[:200]}"
    finally:
        # 关键：无论成功失败，必须彻底退出浏览器，释放系统资源
        if page:
            try: page.quit()
            except: pass
        vdisplay.stop()
        return success, msg

# ==============================================================================
# 主控逻辑：自适应时间分片 + 熔断机制
# ==============================================================================
def restart_singbox():
    print("♻️ 正在重启 sing-box...")
    try:
        subprocess.run(['pkill', '-f', 'sing-box run'], stderr=subprocess.DEVNULL)
        time.sleep(2)
        subprocess.Popen(['./sing-box', 'run', '-c', 'config.json'], stdout=open('singbox.log', 'a'), stderr=subprocess.STDOUT)
        time.sleep(5)
        check_process = subprocess.run(['pgrep', '-f', 'sing-box run'], stdout=subprocess.DEVNULL)
        if check_process.returncode != 0:
            print("❌ sing-box 启动失败！")
            try:
                with open("singbox.log", "r") as f: print(f.read()[-500:])
            except: pass
            return False
        print("✅ sing-box 重启成功")
        return True
    except Exception as e:
        print(f"❌ 重启 sing-box 异常: {e}")
        return False

def check_proxy_connectivity(proxy_url, max_retries=2, timeout=5):
    print(f"🔍 正在测试代理连通性 ({max_retries}次重试)...")
    proxies = {"http": proxy_url, "https": proxy_url}
    test_url = "https://api.ipify.org"
    for attempt in range(max_retries):
        try:
            resp = requests.get(test_url, proxies=proxies, timeout=timeout)
            if resp.status_code == 200:
                raw_ip = resp.text.strip()
                # 将 IP 隐藏：例如 220.93.154.85 变成 220.93.154.* 
                # (api.ipify.org 仅返回IP，若带有端口也会将最后一段及端口替换成星号)
                masked_ip = re.sub(r'(\d+\.\d+\.\d+)\.\d+(:\d+)?', r'\1.*', raw_ip)
                return True, masked_ip
        except requests.exceptions.ProxyError:
            return False, "Proxy Refused"
        except: pass
    return False, "Timeout/Unreachable"

if __name__ == "__main__":
    renew_url = os.getenv("RENEW_URL")
    tg_token = os.getenv("TG_TOKEN")
    tg_chat_id = os.getenv("TG_CHAT_ID")
    local_proxy_url = "http://127.0.0.1:8080"

    if not renew_url:
        print("❌ 缺少 RENEW_URL")
        sys.exit(1)

    # 1. 获取总节点数量
    try:
        result = subprocess.run(['python', 'proxy_handler.py', '--count'], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            print("❌ 解析节点时发生错误")
            sys.exit(1)
        numbers = re.findall(r'\d+', result.stdout.strip())
        if not numbers:
            print("❌ 没有解析出任何可用节点")
            sys.exit(1)
        total_nodes = int(numbers[0])
    except Exception as e:
        print(f"❌ 获取节点数量失败: {e}")
        sys.exit(1)

    # ✨✨✨ 核心新增：自适应时间分片算法 ✨✨✨
    if total_nodes == 0:
        print("❌ 没有可用节点，程序终止")
        sys.exit(1)
        
    if total_nodes == 1:
        daily_index = 0
        print("📌 单节点模式，跳过时间分片，直接使用唯一节点")
    else:
        # 动态计算今天的时间分段数
        if total_nodes <= 5:
            segments = total_nodes * 2  # 5个及以下节点，保证每天轮转2次
        else:
            segments = total_nodes      # 超过5个节点，每天轮转1次足够冷却
            
        minutes_per_segment = 1440 / segments
        now = datetime.datetime.now()
        current_minutes = now.hour * 60 + now.minute
        current_segment = int(current_minutes / minutes_per_segment)
        daily_index = current_segment % total_nodes
        
        print(f"⚔️ 检测到 {total_nodes} 个节点，启动自适应排期策略...")
        print(f"📅 今日时间被切分为 {segments} 段 (每段 {minutes_per_segment:.1f} 分钟)")
        print(f"⏰ 当前时间处于第 {current_segment + 1} 段，首选节点索引: {daily_index}")

    final_success = False
    final_msg = "❌ 所有节点均尝试完毕，续期失败"

    # 2. 核心重试循环 (从时间分片算出的首选节点开始，穷举到完)
    for i in range(total_nodes):
        node_idx = (daily_index + i) % total_nodes
        print(f"\n{'='*50}")
        print(f"🚀 第 {i+1}/{total_nodes} 次尝试 (当前节点索引: {node_idx})...")

        gen_result = subprocess.run(['python', 'proxy_handler.py', '--index', str(node_idx)], capture_output=True, text=True)
        if gen_result.returncode != 0: continue

        if not restart_singbox():
            final_msg = f"💥 致命错误：节点 {node_idx} 导致 sing-box 启动失败，流程熔断。"
            break

        is_alive, ip_info = check_proxy_connectivity(local_proxy_url)
        if not is_alive:
            print(f"🚫 节点 {node_idx} 代理不通 ({ip_info})，跳过！")
            continue
        else:
            print(f"✅ 节点 {node_idx} 代理连通正常！出口 IP: {ip_info}")

        clean_user_data_dir = tempfile.mkdtemp()
        is_success, result_message = renew_host2play(renew_url, local_proxy_url, clean_user_data_dir)
        print(f"📝 节点 {node_idx} (IP: {ip_info}) 执行结果: {result_message}")
        
        try: shutil.rmtree(clean_user_data_dir, ignore_errors=True)
        except: pass

        if is_success:
            final_success = True
            final_msg = f"🎉 续期成功！(节点 {node_idx}, IP: {ip_info}) - {result_message}"
            break
        else:
            print("🛡️ 当前 IP 未过风控，准备下一个节点浴火重生...")

    # 3. 流程结束，发送通知
    print(f"\n{'='*50}")
    print(f"🏁 最终结果: {final_msg}")
    send_tg_message(tg_token, tg_chat_id, final_msg)

    if not final_success:
        sys.exit(1)
