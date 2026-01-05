from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import tempfile
import uuid
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# Temporary storage for downloads
DOWNLOAD_DIR = tempfile.gettempdir()

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'yt-dlp-api'})

@app.route('/api/info', methods=['POST'])
def get_video_info():
    """Get video information without downloading"""
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Get available formats
            formats = []
            if 'formats' in info:
                for f in info['formats']:
                    if f.get('vcodec') != 'none' or f.get('acodec') != 'none':
                        formats.append({
                            'format_id': f.get('format_id'),
                            'ext': f.get('ext'),
                            'quality': f.get('quality', 0),
                            'resolution': f.get('resolution', 'audio only'),
                            'filesize': f.get('filesize'),
                            'vcodec': f.get('vcodec'),
                            'acodec': f.get('acodec'),
                            'format_note': f.get('format_note', '')
                        })
            
            return jsonify({
                'success': True,
                'info': {
                    'id': info.get('id'),
                    'title': info.get('title'),
                    'uploader': info.get('uploader'),
                    'duration': info.get('duration'),
                    'thumbnail': info.get('thumbnail'),
                    'description': info.get('description', '')[:200],
                    'view_count': info.get('view_count'),
                    'upload_date': info.get('upload_date'),
                },
                'formats': formats[:20]  # Limit to top 20 formats
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    """Download video and return download URL"""
    try:
        data = request.get_json()
        url = data.get('url')
        format_type = data.get('format', 'mp4')  # mp4, mp3, best
        quality = data.get('quality', '720')  # 720, 1080, best
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Generate unique filename
        file_id = str(uuid.uuid4())
        output_template = os.path.join(DOWNLOAD_DIR, f'{file_id}.%(ext)s')
        
        # Configure yt-dlp options based on format
        ydl_opts = {
            'outtmpl': output_template,
            'quiet': True,
        }
        
        if format_type == 'mp3':
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        elif format_type == 'mp4':
            if quality == 'best':
                ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            else:
                ydl_opts['format'] = f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best'
        else:
            ydl_opts['format'] = 'best'
        
        # Download the video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Find the downloaded file
            downloaded_file = None
            for ext in ['mp4', 'mp3', 'webm', 'mkv']:
                potential_file = os.path.join(DOWNLOAD_DIR, f'{file_id}.{ext}')
                if os.path.exists(potential_file):
                    downloaded_file = potential_file
                    break
            
            if not downloaded_file:
                return jsonify({'error': 'Download completed but file not found'}), 500
            
            file_size = os.path.getsize(downloaded_file)
            
            return jsonify({
                'success': True,
                'file_id': file_id,
                'filename': f"{info.get('title', 'video')}.{os.path.splitext(downloaded_file)[1][1:]}",
                'size': file_size,
                'download_url': f'/api/file/{os.path.basename(downloaded_file)}',
                'title': info.get('title'),
                'duration': info.get('duration')
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/file/<filename>', methods=['GET'])
def get_file(filename):
    """Serve the downloaded file"""
    try:
        file_path = os.path.join(DOWNLOAD_DIR, filename)
        
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
        
        # Get original filename from query param
        original_name = request.args.get('name', filename)
        
        response = send_file(
            file_path,
            as_attachment=True,
            download_name=original_name
        )
        
        # Delete file after sending (cleanup)
        @response.call_on_close
        def cleanup():
            try:
                os.remove(file_path)
            except:
                pass
        
        return response
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/formats', methods=['POST'])
def get_formats():
    """Get available formats for a video"""
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Organize formats
            video_formats = []
            audio_formats = []
            
            for f in info.get('formats', []):
                format_info = {
                    'format_id': f.get('format_id'),
                    'ext': f.get('ext'),
                    'quality': f.get('format_note', ''),
                    'filesize': f.get('filesize'),
                    'resolution': f.get('resolution', 'N/A')
                }
                
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                    video_formats.append(format_info)
                elif f.get('acodec') != 'none':
                    audio_formats.append(format_info)
            
            return jsonify({
                'success': True,
                'title': info.get('title'),
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration'),
                'video_formats': video_formats[:10],
                'audio_formats': audio_formats[:5]
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
