import os
import json
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from mutagen import File
import uuid
from datetime import datetime

app = Flask(__name__)

# 配置
UPLOAD_FOLDER = 'uploads'
DATA_FILE = 'music_data.json'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'flac', 'm4a', 'aac', 'ogg'}
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# 确保上传文件夹存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_music_info(file_path):
    """提取音乐文件的元数据信息"""
    try:
        audio_file = File(file_path)
        if audio_file is None:
            return None
        
        # 获取文件扩展名以确定格式
        file_ext = os.path.splitext(file_path)[1].lower()
        
        title = None
        artist = None
        album = None
        
        # 根据不同格式使用不同的标签键
        if file_ext in ['.mp3']:
            # MP3 使用 ID3 标签
            title = audio_file.get('TIT2', [None])[0] if audio_file.get('TIT2') else None
            artist = audio_file.get('TPE1', [None])[0] if audio_file.get('TPE1') else None
            album = audio_file.get('TALB', [None])[0] if audio_file.get('TALB') else None
        elif file_ext in ['.flac', '.ogg']:
            # FLAC 和 OGG 使用 Vorbis Comments
            title = audio_file.get('TITLE', [None])[0] if audio_file.get('TITLE') else None
            artist = audio_file.get('ARTIST', [None])[0] if audio_file.get('ARTIST') else None
            album = audio_file.get('ALBUM', [None])[0] if audio_file.get('ALBUM') else None
        elif file_ext in ['.m4a', '.aac']:
            # M4A/AAC 使用 MP4 标签
            title = audio_file.get('\xa9nam', [None])[0] if audio_file.get('\xa9nam') else None
            artist = audio_file.get('\xa9ART', [None])[0] if audio_file.get('\xa9ART') else None
            album = audio_file.get('\xa9alb', [None])[0] if audio_file.get('\xa9alb') else None
        elif file_ext in ['.wav']:
            # WAV 文件通常没有标准的元数据标签，或使用 ID3
            if hasattr(audio_file, 'tags') and audio_file.tags:
                title = audio_file.get('TIT2', [None])[0] if audio_file.get('TIT2') else None
                artist = audio_file.get('TPE1', [None])[0] if audio_file.get('TPE1') else None
                album = audio_file.get('TALB', [None])[0] if audio_file.get('TALB') else None
        
        # 如果没有找到标题，使用原始文件名（去掉扩展名）
        if not title:
            original_filename = os.path.basename(file_path)
            # 从存储的文件名找到对应的原始文件名
            # 这里我们需要从文件名中提取，但更好的方法是传递原始文件名
            title = os.path.splitext(original_filename)[0]
        
        # 如果没有艺术家信息
        if not artist:
            artist = "未知艺术家"
            
        # 如果没有专辑信息
        if not album:
            album = "未知专辑"
            
        return {
            'title': str(title) if title else "未知标题",
            'artist': str(artist) if artist else "未知艺术家",
            'album': str(album) if album else "未知专辑"
        }
    except Exception as e:
        print(f"提取音乐信息时出错: {e}")
        return None

def load_music_data():
    """加载音乐数据"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_music_data(data):
    """保存音乐数据"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': '没有选择文件'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400
    
    if file and allowed_file(file.filename):
        # 生成唯一的文件名
        file_extension = file.filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        try:
            file.save(file_path)
            
            # 提取音乐信息
            music_info = extract_music_info(file_path)
            if music_info is None:
                os.remove(file_path)  # 删除无效文件
                return jsonify({'error': '无法读取音乐文件信息'}), 400
            
            # 创建音乐记录
            music_record = {
                'id': str(uuid.uuid4()),
                'filename': unique_filename,
                'original_name': file.filename,
                'title': music_info['title'],
                'artist': music_info['artist'],
                'album': music_info['album'],
                'url': f'/api/audio/{unique_filename}',
                'upload_time': datetime.now().isoformat()
            }
            
            # 保存到数据文件
            music_data = load_music_data()
            music_data.append(music_record)
            save_music_data(music_data)
            
            return jsonify({
                'message': '上传成功',
                'music': music_record
            })
            
        except Exception as e:
            if os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({'error': f'上传失败: {str(e)}'}), 500
    
    return jsonify({'error': '不支持的文件格式'}), 400

@app.route('/api/music')
def get_music_list():
    """获取音乐列表"""
    music_data = load_music_data()
    return jsonify(music_data)

@app.route('/api/audio/<filename>')
def serve_audio(filename):
    """提供音乐文件访问"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/delete/<music_id>', methods=['DELETE'])
def delete_music(music_id):
    """删除音乐文件"""
    music_data = load_music_data()
    music_to_delete = None
    
    for i, music in enumerate(music_data):
        if music['id'] == music_id:
            music_to_delete = music_data.pop(i)
            break
    
    if music_to_delete:
        # 删除文件
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], music_to_delete['filename'])
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # 保存更新后的数据
        save_music_data(music_data)
        return jsonify({'message': '删除成功'})
    
    return jsonify({'error': '音乐不存在'}), 404

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
