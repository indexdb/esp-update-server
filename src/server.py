from datetime import datetime
from flask import Flask, request, render_template, flash, redirect, url_for, send_from_directory, render_template_string, jsonify, session
from packaging import version
from functools import wraps
from difflib import get_close_matches, SequenceMatcher
import re
import time
import os
import yaml
import json
import uuid
import hashlib

app = Flask(__name__, static_url_path='/static', static_folder='static')
ALLOWED_EXTENSIONS = set(['bin'])
app.config['UPLOAD_FOLDER'] = './bin'
app.config['SECRET_KEY'] = 'Kri57i4n570bb33r3nF1ink3rFyr'
PROJECTS_YAML = app.config['UPLOAD_FOLDER'] + '/projects.yml'
DEVICES_YAML = app.config['UPLOAD_FOLDER'] + '/devices.yml'
USERS_YAML = app.config['UPLOAD_FOLDER'] + '/users.yml'

# Ensure folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ==================== Authentication Functions ====================

def hash_password(password):
    """Hash password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

def load_users():
    """Load users configuration file"""
    try:
        with open(USERS_YAML, 'r', encoding='utf-8') as f:
            users = yaml.load(f, Loader=yaml.FullLoader)
            return users if users else {}
    except FileNotFoundError:
        # Create default user: admin/admin
        default_users = {
            'admin': {
                'password': hash_password('admin'),
                'created': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        }
        save_users(default_users)
        return default_users
    except Exception as e:
        log_event(f"ERROR: Failed to load users.yml: {e}")
        return {}

def save_users(users):
    """Save users configuration file"""
    try:
        with open(USERS_YAML, 'w', encoding='utf-8') as f:
            yaml.dump(users, f, default_flow_style=False, allow_unicode=True)
            return True
    except Exception as e:
        log_event(f"ERROR: Failed to save users.yml: {e}")
        return False

def login_required(f):
    """Login verification decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Please login first')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# ==================== Authentication Routes ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        users = load_users()
        
        if username in users and users[username]['password'] == hash_password(password):
            session['logged_in'] = True
            session['username'] = username
            log_event(f"INFO: User {username} logged in")
            
            # Redirect to the page user wanted to access, or home
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password')
            log_event(f"WARN: Failed login attempt for user {username}")
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    username = session.get('username', 'unknown')
    session.clear()
    log_event(f"INFO: User {username} logged out")
    flash('Logged out successfully')
    return redirect(url_for('login'))

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not all([current_password, new_password, confirm_password]):
            flash('All fields are required')
            return render_template('change_password.html')
        
        if new_password != confirm_password:
            flash('New passwords do not match')
            return render_template('change_password.html')
        
        if len(new_password) < 4:
            flash('New password must be at least 4 characters')
            return render_template('change_password.html')
        
        users = load_users()
        username = session.get('username')
        
        if users[username]['password'] != hash_password(current_password):
            flash('Current password is incorrect')
            return render_template('change_password.html')
        
        users[username]['password'] = hash_password(new_password)
        users[username]['last_password_change'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if save_users(users):
            flash('Password changed successfully')
            log_event(f"INFO: User {username} changed password")
            return redirect(url_for('index'))
        else:
            flash('Failed to change password, please try again')
    
    return render_template('change_password.html')

# ==================== Helper Functions ====================

def guess_project_name(filename, project_keys):
    base = filename.rsplit('.', 1)[0].lower()
    matches = get_close_matches(base, project_keys, n=1, cutoff=0.3)
    return matches[0] if matches else None

def suggest_next_version(current_version):
    if not current_version:
        return "1.0"
    try:
        v = version.parse(current_version)
        major, minor, *_ = (v.release + (0, 0))[:2]

        if minor < 9:
            minor += 1
        else:
            major += 1
            minor = 0

        return f"{major}.{minor}"
    except Exception:
        return "1.0"

def load_devices_yaml():
    """Load devices YAML file"""
    devices = None
    try:
        with open(DEVICES_YAML, 'r', encoding='utf-8') as stream:
            try:
                devices = yaml.load(stream, Loader=yaml.FullLoader)
            except yaml.YAMLError as err:
                flash(f"YAML Error: {err}")
                log_event(f"ERROR: YAML parse error in devices.yml: {err}")
    except FileNotFoundError:
        # If file doesn't exist, create empty device data structure
        devices = {}
        save_devices_yaml(devices)
    except Exception as e:
        flash(f'Error loading devices.yml: {e}')
        log_event(f"ERROR: Exception loading devices.yml: {e}")
    
    return devices if devices else {}

def save_devices_yaml(devices):
    """Save devices YAML file"""
    try:
        with open(DEVICES_YAML, 'w', encoding='utf-8') as outfile:
            yaml.dump(devices, outfile, default_flow_style=False, allow_unicode=True, sort_keys=False)
            return True
    except Exception as e:
        flash(f'Error saving devices.yml: {e}')
        log_event(f"ERROR: Failed to save devices.yml: {e}")
        return False

@app.template_filter('human_time')
def human_time(seconds):
    """Convert seconds to human-readable format: xx min xx sec"""
    if not seconds:
        return '-'
    seconds = int(seconds)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if minutes > 0:
        parts.append(f"{minutes} min")
    if seconds > 0:
        parts.append(f"{seconds} sec")
    if not parts:
        parts.append("0 sec")
    return ' '.join(parts)

def update_device_info(project, mac, action='check', device_ver=None):
    """Update device information - notes can only be edited via web interface"""
    devices = load_devices_yaml()
    current_time = datetime.now()
    current_time_str = current_time.strftime('%Y-%m-%d %H:%M:%S')

    if project not in devices:
        devices[project] = {}
    if mac not in devices[project]:
        devices[project][mac] = {
            'last_check_time': None,
            'last_update_time': None,
            'notes': '',  # Empty by default, only editable via web interface
            'first_seen': current_time_str,
            'check_count': 0,
            'update_count': 0,
            'current_version': None,
            'last_check_interval': None
        }

    device_info = devices[project][mac]

    # Calculate interval since last check
    if device_info['last_check_time']:
        try:
            last_check = datetime.strptime(device_info['last_check_time'], '%Y-%m-%d %H:%M:%S')
            device_info['last_check_interval'] = (current_time - last_check).total_seconds()
        except Exception:
            device_info['last_check_interval'] = None
    else:
        device_info['last_check_interval'] = None

    # Update time and counters
    device_info['last_check_time'] = current_time_str
    device_info['check_count'] = device_info.get('check_count', 0) + 1

    if action == 'update':
        device_info['last_update_time'] = current_time_str
        device_info['update_count'] = device_info.get('update_count', 0) + 1

    if device_ver:
        device_info['current_version'] = device_ver

    save_devices_yaml(devices)

def log_event(msg, filename='log.txt', max_lines=1000, keep_lines=100):
    # Write log entry
    st = datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')
    with open(filename, 'a', encoding='utf-8') as f:
        f.write(st + ' ' + msg + '\n')

    # Check and trim log file
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        if len(lines) > max_lines:
            with open(filename, 'w', encoding='utf-8') as f:
                f.writelines(lines[-keep_lines:])  # Keep only last keep_lines
    except Exception as e:
        print(f"Error trimming log file: {e}")
        
def allowed_ext(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_yaml():
    """Load projects YAML file"""
    projects = None
    try:
        with open(PROJECTS_YAML, 'r', encoding='utf-8') as stream:
            try:
                projects = yaml.load(stream, Loader=yaml.FullLoader)
            except yaml.YAMLError as err:
                flash(str(err))
                log_event(f"ERROR: YAML parse error in projects.yml: {err}")
    except:
        flash('Error: File not found.')
        
    if projects:
        for value in projects.values():
            if value.get('whitelist'):
                for i in range(0, len(value['whitelist'])):
                    value['whitelist'][i] = str(value['whitelist'][i])
                    
    return projects

def save_yaml(projects):
    """Save projects YAML file"""
    try:
        with open(PROJECTS_YAML, 'w', encoding='utf-8') as outfile:
            yaml.dump(projects, outfile, default_flow_style=False, allow_unicode=True)
            return True
    except Exception as e:
        flash(f'Error: Data not saved. {e}')
        log_event(f"ERROR: Failed to save projects.yml: {e}")
        return False

# ==================== Firmware Analysis Functions ====================

def extract_all_strings(filepath, min_length=4, max_length=50):
    """Extract all possible printable strings from firmware file"""
    try:
        with open(filepath, 'rb') as f:
            content = f.read()
        
        strings = []
        current_string = []
        
        for byte in content:
            if 32 <= byte <= 126:  # Printable ASCII
                current_string.append(chr(byte))
            else:
                if len(current_string) >= min_length:
                    s = ''.join(current_string)
                    if len(s) <= max_length:
                        strings.append(s)
                current_string = []
        
        if len(current_string) >= min_length:
            s = ''.join(current_string)
            if len(s) <= max_length:
                strings.append(s)
        
        return strings
    
    except Exception as e:
        print(f"Error extracting strings: {e}")
        return []

def calculate_similarity(strings1, strings2):
    """Calculate similarity between two sets of strings"""
    # Method 1: Common string ratio (weight 40%)
    set1 = set(strings1)
    set2 = set(strings2)
    common_count = len(set1 & set2)
    total_count = len(set1 | set2)
    common_ratio = common_count / total_count if total_count > 0 else 0
    
    # Method 2: String similarity (weight 30%)
    similarity_sum = 0
    comparison_count = 0
    
    for s1 in strings1[:100]:
        for s2 in strings2[:100]:
            if len(s1) > 3 and len(s2) > 3:
                ratio = SequenceMatcher(None, s1, s2).ratio()
                if ratio > 0.6:
                    similarity_sum += ratio
                    comparison_count += 1
    
    avg_similarity = similarity_sum / comparison_count if comparison_count > 0 else 0
    
    # Method 3: Keyword matching (weight 30%)
    keywords1 = [s for s in strings1 if re.match(r'^[A-Z][a-zA-Z0-9_]{2,}$', s)]
    keywords2 = [s for s in strings2 if re.match(r'^[A-Z][a-zA-Z0-9_]{2,}$', s)]
    
    keyword_common = len(set(keywords1) & set(keywords2))
    keyword_total = len(set(keywords1) | set(keywords2))
    keyword_ratio = keyword_common / keyword_total if keyword_total > 0 else 0
    
    # Final score
    final_score = (common_ratio * 0.4 + avg_similarity * 0.3 + keyword_ratio * 0.3) * 100
    
    return final_score

def compare_firmware_with_history(new_firmware_path, projects, upload_folder):
    """Compare new firmware with historical versions"""
    try:
        new_strings = extract_all_strings(new_firmware_path)
        
        if not new_strings:
            return None, 0, {}
        
        scores = {}
        
        for project_name, project_info in projects.items():
            if not project_info.get('file'):
                continue
            
            history_path = os.path.join(upload_folder, project_info['file'])
            
            if not os.path.isfile(history_path):
                continue
            
            history_strings = extract_all_strings(history_path)
            
            if not history_strings:
                continue
            
            score = calculate_similarity(new_strings, history_strings)
            scores[project_name] = score
        
        if not scores:
            return None, 0, {}
        
        best_match = max(scores, key=scores.get)
        best_score = scores[best_match]
        
        return best_match, best_score, scores
    
    except Exception as e:
        print(f"Error comparing firmware: {e}")
        return None, 0, {}

def increment_version(version_str):
    """Increment version by 0.1, format: xx.x"""
    try:
        # Parse version number
        parts = version_str.split('.')
        if len(parts) >= 2:
            major = int(parts[0])
            minor = int(parts[1])
            
            # Add 0.1
            minor += 1
            
            # If minor reaches 10, carry to major
            if minor >= 10:
                major += 1
                minor = 0
            
            return f"{major}.{minor}"
        else:
            return "1.0"
    except:
        return "1.0"

def parse_version_from_firmware(filepath):
    """Parse version number from firmware"""
    try:
        with open(filepath, 'rb') as f:
            content = f.read()
        
        text = content.decode('latin-1', errors='ignore')
        
        # Search for version patterns
        version_patterns = [
            r'\b[vV]?([0-9]+\.[0-9]+(?:\.[0-9]+)?)\b',
            r'VERSION[:\s=]+"?v?([0-9]+\.[0-9]+(?:\.[0-9]+)?)"?',
            r'VER[:\s=]+"?v?([0-9]+\.[0-9]+(?:\.[0-9]+)?)"?',
        ]
        
        for pattern in version_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                for m in matches:
                    if m.count('.') >= 1:
                        return m.lstrip('vV')
        
        return None
        
    except Exception as e:
        print(f"Error parsing version: {e}")
        return None

def parse_firmware_info_smart(filepath, projects, upload_folder):
    """Smart firmware information parsing"""
    result = {
        'version': None,
        'app_name': None,
        'match_method': None,
        'confidence': 0,
        'all_scores': {}
    }
    
    try:
        # Step 1: Try direct parsing
        with open(filepath, 'rb') as f:
            content = f.read()
        
        text = content.decode('latin-1', errors='ignore')
        
        # Search for version number
        version_patterns = [
            r'\b[vV]?([0-9]+\.[0-9]+(?:\.[0-9]+)?)\b',
            r'VERSION[:\s=]+"?v?([0-9]+\.[0-9]+(?:\.[0-9]+)?)"?',
            r'VER[:\s=]+"?v?([0-9]+\.[0-9]+(?:\.[0-9]+)?)"?',
        ]
        
        for pattern in version_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                for m in matches:
                    if m.count('.') >= 1:
                        result['version'] = m.lstrip('vV')
                        break
                if result['version']:
                    break
        
        # Search for app name
        app_patterns = [
            r'APP[:\s=]+"?([A-Za-z][A-Za-z0-9\s_-]{2,30})"?',
            r'FWAPP[:\s=]+"?([A-Za-z][A-Za-z0-9\s_-]{2,30})"?',
            r'\b([A-Z][a-z]+[A-Z][a-zA-Z]+)\b',
        ]
        
        for pattern in app_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                app_name = match.group(1).strip()
                if 3 <= len(app_name) <= 30:
                    result['app_name'] = app_name
                    result['match_method'] = 'direct_parse'
                    result['confidence'] = 70
                    break
        
        # Step 2: If failed, use similarity comparison
        if not result['app_name'] and projects:
            best_match, best_score, all_scores = compare_firmware_with_history(
                filepath, projects, upload_folder
            )
            
            if best_match and best_score > 30:
                result['app_name'] = best_match
                result['match_method'] = 'similarity_match'
                result['confidence'] = best_score
                result['all_scores'] = all_scores
        
        return result
        
    except Exception as e:
        print(f"Error in smart parse: {e}")
        import traceback
        traceback.print_exc()
        return result

# ==================== Routes ====================

@app.context_processor
def utility_processor():
    def format_mac(mac):
        return ':'.join(mac[i:i+2] for i in range(0,12,2))
    return dict(format_mac=format_mac)

@app.route('/bin/<path:filename>')
def send_bin_file(filename, **kwargs):
    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        filename,
        as_attachment=True,
        mimetype='application/octet-stream',
        download_name=filename,
        **kwargs
    )

@app.route('/update', methods=['GET', 'POST'])
def update():
    """OTA Update endpoint - NO LOGIN REQUIRED"""
    projects = load_yaml()
    __dev = request.args.get('dev', default=None)
    
    # Get MAC address
    if 'X_ESP8266_STA_MAC' in request.headers:
        __mac = request.headers['X_ESP8266_STA_MAC']
        __mac = re.sub(r'[^0-9A-fa-f]+', '', __mac.lower())
        log_event("===================== " + __mac.upper() + " =====================")
        log_event("INFO: Update called by ESP8266 with MAC " + __mac)
    elif 'x_ESP32_STA_MAC' in request.headers:
        __mac = request.headers['x_ESP32_STA_MAC']
        __mac = re.sub(r'[^0-9A-fa-f]+', '', __mac.lower())
        log_event("===================== " + __mac.upper() + " =====================")
        log_event("INFO: Update called by ESP32 with MAC " + __mac)
    else:
        __mac = ''
        log_event("===================== " + __mac.upper() + " =====================")
        log_event("WARN: Update called without known headers.")
    
    __ver = request.args.get('ver', default=None)

    # Log basic request info
    log_event("URL: " + request.url)
    log_event("__dev: " + str(__dev))
    log_event("__mac: " + str(__mac))
    log_event("__ver: " + str(__ver))

    if __dev and __mac and __ver:
        __dev = __dev.lower()
        log_event(f"INFO: Dev={__dev}, Ver={__ver}, MAC={__mac}")

        if projects and __dev in projects:
            project_info = projects[__dev]

            # Record device check
            update_device_info(__dev, __mac, 'check', device_ver=__ver)
            
            # Check if update is needed
            if project_info['version'] and version.parse(__ver) != version.parse(project_info['version']):
                firmware_file = os.path.join(app.config['UPLOAD_FOLDER'], project_info['file'])
                if os.path.isfile(firmware_file):
                    project_info['downloads'] += 1
                    save_yaml(projects)
                    
                    # Record actual update
                    update_device_info(__dev, __mac, 'update', device_ver=project_info['version'])
                    log_event(f"INFO: {__dev} ({__mac}) updated from {__ver} to {project_info['version']}")
                    return send_bin_file(project_info['file'])
                else:
                    log_event(f"ERROR: No Firmware File for {__dev}")
                    return 'No Firmware File.', 400
            else:
                log_event(f"INFO: No update needed for {__dev} ({__mac})")
                return 'No update needed.', 304
        else:
            log_event(f"ERROR: Unknown project: {__dev}")
            return 'Error: Unknown project.', 400
    else:
        log_event("ERROR: Invalid parameters.")
        return 'Error: Invalid parameters.', 400

@app.route('/')
@login_required
def index():
    projects = load_yaml()
    return render_template('status.html', projects=projects)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    projects = load_yaml()
    if not projects:
        flash('Please create a project first.')
        return render_template('status.html', projects=projects)

    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Error: No file part.')
            return redirect(request.url)

        file = request.files['file']
        if file.filename == '':
            flash('Error: No file selected.')
            return redirect(request.url)

        if file and allowed_ext(file.filename):
            # Save temporary file
            tmp_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'tmp')
            os.makedirs(tmp_folder, exist_ok=True)
            tmp_filename = str(uuid.uuid4()) + '.bin'
            tmp_filepath = os.path.join(tmp_folder, tmp_filename)
            file.save(tmp_filepath)

            # Initialize default values
            firmware_info = {
                'confidence': 0,
                'all_scores': {},
                'top_scores': {}  # Keep only top 5
            }

            # Use similarity comparison to match project
            guessed_name = None
            suggested_version = "1.0"
            
            try:
                # Compare with all existing project firmwares
                best_match, best_score, all_scores = compare_firmware_with_history(
                    tmp_filepath, 
                    projects, 
                    app.config['UPLOAD_FOLDER']
                )
                
                firmware_info['all_scores'] = all_scores
                firmware_info['confidence'] = best_score
                
                # Keep only top 5 highest similarity scores
                if all_scores:
                    sorted_scores = sorted(all_scores.items(), key=lambda x: x[1], reverse=True)
                    firmware_info['top_scores'] = dict(sorted_scores[:5])
                
                if best_match and best_score > 30:  # At least 30% similarity
                    guessed_name = best_match
                    
            except Exception as e:
                pass
            
            # If no match found, fall back to first project
            if not guessed_name and projects:
                guessed_name = list(projects.keys())[0]
            
            # Auto-suggest version: increment current version by 0.1
            if guessed_name and guessed_name in projects:
                old_ver = projects[guessed_name].get('version')
                if old_ver:
                    try:
                        suggested_version = increment_version(old_ver)
                    except:
                        suggested_version = "1.0"
                else:
                    suggested_version = "1.0"

            return render_template(
                'upload_confirm.html',
                original_filename=file.filename,
                tmp_filename=tmp_filename,
                guessed_name=guessed_name,
                suggested_version=suggested_version,
                firmware_info=firmware_info,
                projects=projects
            )
        else:
            flash('Error: File type not allowed.')
            return redirect(request.url)

    return render_template('upload.html', projects=projects)

@app.route('/upload_confirm', methods=['POST'])
@login_required
def upload_confirm():
    projects = load_yaml()
    tmp_filename = request.form.get('tmp_filename')
    project_name = request.form.get('project')
    version_input = request.form.get('version')

    if not (tmp_filename and project_name and version_input):
        flash('Error: Missing required information.')
        return redirect(url_for('upload'))

    tmp_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'tmp')
    tmp_filepath = os.path.join(tmp_folder, tmp_filename)

    if not os.path.isfile(tmp_filepath):
        flash('Error: Temporary file does not exist.')
        return redirect(url_for('upload'))

    project_name = project_name.lower()
    if project_name not in projects:
        flash('Error: Project does not exist.')
        return redirect(url_for('upload'))

    # Save with final filename
    filename = f"{project_name}_{version_input.replace('.', '_')}.bin"
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    try:
        if os.path.exists(save_path):
            os.remove(save_path)
        os.rename(tmp_filepath, save_path)
    except Exception as e:
        flash(f'Error: Failed to save file: {e}')
        return redirect(url_for('upload'))

    # Delete old firmware file
    old_file = projects[project_name].get('file')
    if old_file and old_file != filename:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], old_file))
        except Exception:
            pass

    # Update project info - PRESERVE download count
    projects[project_name]['version'] = version_input
    projects[project_name]['file'] = filename
    projects[project_name]['downloads'] = projects[project_name].get('downloads', 0)  # Preserve existing count
    projects[project_name]['uploaded'] = datetime.now().strftime('%Y-%m-%d')
    
    if not save_yaml(projects):
        flash('Error: Failed to update project information.')
        return redirect(url_for('upload'))

    flash('Successfully uploaded and updated project firmware.')
    log_event(f"SUCCESS: Uploaded {filename} for project {project_name} version {version_input}")
    return redirect(url_for('index'))

@app.route('/devices')
@login_required
def devices():
    devices = load_devices_yaml()
    projects = load_yaml()
    
    # Fill in default fields for each device to avoid template errors
    for project_devices in devices.values():
        for device in project_devices.values():
            device.setdefault('check_count', 0)
            device.setdefault('update_count', 0)
            device.setdefault('first_seen', '')
            device.setdefault('last_check_time', '')
            device.setdefault('last_update_time', '')
            device.setdefault('notes', '')
            device.setdefault('current_version', '')
            device.setdefault('last_check_interval', None)

    return render_template('devices.html', devices=devices, projects=projects)

@app.route('/devices/edit/<project>/<mac>', methods=['GET', 'POST'])
@login_required
def edit_device(project, mac):
    """Edit device notes"""
    devices = load_devices_yaml()
    
    if request.method == 'POST':
        notes = request.form.get('notes', '')
        if project in devices and mac in devices[project]:
            devices[project][mac]['notes'] = notes
            if save_devices_yaml(devices):
                flash('Device notes updated.')
                log_event(f"INFO: Updated notes for device {mac} on project {project}")
            else:
                flash('Save failed.')
                log_event(f"ERROR: Failed to save notes for device {mac} on project {project}")
        return redirect(url_for('devices'))
    
    device_info = devices.get(project, {}).get(mac, {})
    return render_template('edit_device.html', project=project, mac=mac, device_info=device_info)

@app.route('/devices/delete/<project>/<mac>', methods=['POST'])
@login_required
def delete_device(project, mac):
    """Delete device record"""
    devices = load_devices_yaml()
    
    if project in devices and mac in devices[project]:
        del devices[project][mac]
        # Delete project if no devices left
        if not devices[project]:
            del devices[project]
        
        if save_devices_yaml(devices):
            flash('Device record deleted.')
            log_event(f"INFO: Deleted device {mac} from project {project}")
        else:
            flash('Delete failed.')
            log_event(f"ERROR: Failed to delete device {mac} from project {project}")
    
    return redirect(url_for('devices'))

@app.route('/manage', methods=['GET', 'POST'])
@login_required
def manage():
    projects = load_yaml()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        # Create project
        if action == 'create':
            project_name = request.form.get('name', '').strip()
            if not project_name:
                flash('Error: Project name cannot be empty.')
            elif projects and project_name.lower() in projects:
                flash('Error: Project name already exists.')
            else:
                if not projects:
                    projects = dict()
                projects[project_name.lower()] = {
                    'version': None,
                    'file': None,
                    'uploaded': None,
                    'downloads': 0,
                    'whitelist': None
                }
                if save_yaml(projects):
                    flash(f'Success: Project "{project_name}" created.')
                    log_event(f"INFO: Created project {project_name.lower()}")
                else:
                    flash('Error: Could not save configuration file.')
        
        # Delete project
        elif action == 'delete':
            project_name = request.form.get('name')
            if not project_name or project_name == '--':
                flash('Error: Please select a project to delete.')
            elif projects and project_name in projects.keys():
                old_file = projects[project_name]['file']
                del projects[project_name]
                if save_yaml(projects):
                    flash(f'Success: Project "{project_name}" deleted.')
                    log_event(f"INFO: Deleted project {project_name}")
                    # Delete associated firmware file
                    if old_file:
                        try:
                            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], old_file))
                        except:
                            flash('Warning: Failed to remove old firmware file.')
                else:
                    flash('Error: Could not save configuration file.')
            else:
                flash('Error: Project does not exist.')
        
        # Reload project list
        projects = load_yaml()
        return render_template('manage.html', projects=projects)
    
    return render_template('manage.html', projects=projects)

@app.route('/whitelist', methods=['GET', 'POST'])
@login_required
def whitelist():
    projects = load_yaml()
    if projects and request.method == 'POST':
        if 'Add' in request.form['action']:
            # Ensure valid data.
            if request.form['device'] and request.form['device'] != '--' and request.form['macaddr']:
                # Remove all unwanted characters.
                __mac = str(re.sub(r'[^0-9A-fa-f]+', '', request.form['macaddr']).lower())
                # Check length after clean-up makes up a full address.
                if len(__mac) == 12:
                    # Check that address is not already on a whitelist.
                    value = projects[request.form['device']]
                    if value['whitelist'] and __mac in value['whitelist']:
                        flash('Error: Address already on a whitelist.')
                        return render_template('whitelist.html', projects=projects)
                            
                    # All looks good - add to whitelist.
                    if not projects[request.form['device']]['whitelist']:
                        projects[request.form['device']]['whitelist'] = []
                    projects[request.form['device']]['whitelist'].append(__mac)
                    if save_yaml(projects):
                        flash('Success: Address added.')
                    else:
                        flash('Error: Could not save file.')
                else:
                    flash('Error: Address malformed.')
            else:
                flash('Error: No data entered.')
        elif 'Remove' in request.form['action']:
            projects[request.form['device']]['whitelist'].remove(str(request.form['macaddr']))
            if save_yaml(projects):
                flash('Success: Address removed.')
            else:
                flash('Error: Could not save file.')
        else:
            flash('Error: Unknown action.')

    if projects:
        return render_template('whitelist.html', projects=projects)
    else:
        return render_template('status.html', projects=projects)

@app.route("/logs")
@login_required
def logs():
    try:
        with open("log.txt", "r", encoding='utf-8') as f:
            content = f.read()
        
        devices = load_devices_yaml()  # Load device notes

        # Match separator lines: "2025-08-14 17:07:36 ===================== MAC ====================="
        separator_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} =+ )([A-Fa-f0-9]{12})( =+)'

        # Split while preserving separators
        parts = re.split(separator_pattern, content)
        log_blocks = []
        i = 0
        while i < len(parts):
            if re.match(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', parts[i]):
                # Compose separator line
                header = parts[i] + parts[i+1] + parts[i+2]  # timestamp + MAC + =+
                mac = parts[i+1].lower()
                header = header.replace("=====================","=====")
                
                # Get notes
                note = ""
                for project, project_devices in devices.items():
                    if mac in project_devices:
                        note_text = project_devices[mac].get('notes', '')
                        if note_text:
                            note = f" ({note_text})"
                        break

                header = f"<b>{header}{note}</b>"

                body = ''
                if i + 3 < len(parts):
                    body = parts[i+3]
                log_blocks.append(header + body)
                i += 4
            else:
                # Content at beginning of file that's not a separator
                log_blocks.append(parts[i])
                i += 1

        # Reverse blocks
        log_blocks.reverse()
        content = ''.join(log_blocks)

    except FileNotFoundError:
        content = "Log file not found."
    except Exception as e:
        content = f"Error reading log file: {e}"

    return render_template("logs.html", content=content)

@app.route("/logs/clear", methods=["POST"])
@login_required
def clear_logs():
    try:
        open("log.txt", "w").close()
        flash("Log file cleared.")
        log_event("INFO: Log file cleared by user")
    except Exception as e:
        flash(f"Error clearing log file: {e}")
    return redirect(url_for("logs"))

# ==================== Main ====================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int('5002'), debug=False)