from flask import Flask, render_template_string, send_from_directory
import os
import json

app = Flask(__name__)

# 정적 파일 서빙을 위한 라우트
@app.route('/styles.css')
def styles():
    return send_from_directory('.', 'styles.css', mimetype='text/css')

@app.route('/script.js')
def script():
    return send_from_directory('.', 'script.js', mimetype='application/javascript')

@app.route('/energy_data.json')
def energy_data():
    return send_from_directory('.', 'energy_data.json', mimetype='application/json')

# 메인 페이지 라우트
@app.route('/')
def index():
    # HTML 파일 읽기
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        return html_content
    except FileNotFoundError:
        return '''
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>A청사 에너지 분석</title>
        </head>
        <body>
            <h1>파일을 찾을 수 없습니다</h1>
            <p>index.html 파일이 존재하지 않습니다.</p>
        </body>
        </html>
        '''

# API 엔드포인트 (선택사항)
@app.route('/api/energy-data')
def api_energy_data():
    try:
        with open('energy_data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        return {"error": "데이터 파일을 찾을 수 없습니다"}, 404

# 헬스체크 엔드포인트
@app.route('/health')
def health_check():
    return {"status": "healthy", "message": "A청사 에너지 분석 시스템이 정상 작동 중입니다"}

# 404 에러 핸들러
@app.errorhandler(404)
def not_found(error):
    return '''
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>페이지를 찾을 수 없습니다</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                text-align: center;
                padding: 2rem;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-direction: column;
            }
            h1 { font-size: 3rem; margin-bottom: 1rem; }
            p { font-size: 1.2rem; margin-bottom: 2rem; }
            a { 
                color: white; 
                text-decoration: none; 
                background: rgba(255,255,255,0.2);
                padding: 1rem 2rem;
                border-radius: 10px;
                transition: background 0.3s;
            }
            a:hover { background: rgba(255,255,255,0.3); }
        </style>
    </head>
    <body>
        <h1>404</h1>
        <p>요청하신 페이지를 찾을 수 없습니다.</p>
        <a href="/">홈으로 돌아가기</a>
    </body>
    </html>
    ''', 404

# 500 에러 핸들러
@app.errorhandler(500)
def internal_error(error):
    return '''
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>서버 오류</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                text-align: center;
                padding: 2rem;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-direction: column;
            }
            h1 { font-size: 3rem; margin-bottom: 1rem; }
            p { font-size: 1.2rem; margin-bottom: 2rem; }
            a { 
                color: white; 
                text-decoration: none; 
                background: rgba(255,255,255,0.2);
                padding: 1rem 2rem;
                border-radius: 10px;
                transition: background 0.3s;
            }
            a:hover { background: rgba(255,255,255,0.3); }
        </style>
    </head>
    <body>
        <h1>500</h1>
        <p>서버에서 오류가 발생했습니다.</p>
        <a href="/">홈으로 돌아가기</a>
    </body>
    </html>
    ''', 500

if __name__ == '__main__':
    # 개발 환경에서 실행
    app.run(debug=True, host='0.0.0.0', port=5000)
