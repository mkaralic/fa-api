from flask import Flask, request, jsonify, send_file
from flask_socketio import SocketIO, emit
from flask_cors import CORS
# Koristio sam os modul za rad sa fajlovima i direktorijumima, zipfile modul za rad sa ZIP fajlovima i time modul za pauziranje izvršavanja programa
import os
import zipfile
import tempfile
import time

def create_app():
    # Kreiranje Flask aplikacije i SocketIO objekta
    app = Flask(__name__)
    CORS(app, origins="http://127.0.0.1:4200") # Dodavanje CORS podrške. Bez ovoga Angular aplikacija ne bi mogla da pristupi API-ju
    app.config['UPLOAD_FOLDER'] = './uploads'
    app.config['ZIP_FOLDER'] = './zips'
    socketio = SocketIO(app, cors_allowed_origins="*")

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['ZIP_FOLDER'], exist_ok=True)

    # Definisanje ruta, koristio sa root URL gde god je to bilo moguće
    @app.route('/', methods=['GET'])
    def list_files():
        # Prikazivanje svih ZIP fajlova u ZIP_FOLDER direktorijumu
        files = [f for f in os.listdir(app.config['ZIP_FOLDER']) if f.endswith('.zip')]
        return jsonify({'files': files})

    @app.route('/', methods=['POST'])
    def upload_file():
        # Upload fajla u delovima, kako bi se pratio progres upload-a. Klijent pravi delove i računa njihov broj i šalje te delove.
        file_chunk = request.files['file']
        filename = file_chunk.filename
        chunk_index = int(request.form['chunkIndex'])
        total_chunks = int(request.form['totalChunks'])

        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        # Otvaranje fajla u append modu i upisivanje delova u fajl
        with open(file_path, 'ab') as f:
            f.write(file_chunk.read())

        # Emitovanje progres upload-a
        progress = int((chunk_index + 1) / total_chunks * 100)
        socketio.emit('status', {'status': 'upload_progress', 'progress': progress})

        # Ako je poslednji deo fajla primljen, poziva se funkcija za zipovanje fajla
        if chunk_index + 1 == total_chunks:
            zip_path = get_unique_zip_path(app.config['ZIP_FOLDER'], filename)
            chunked_zip(file_path, zip_path, socketio)
            socketio.emit('file_list_updated')

        return jsonify({'status': 'chunk_received'}), 200

    def get_unique_zip_path(zip_folder, filename):
        '''Funkcija koja vraća putanju do ZIP fajla i automatski kreira novo ime u slučaju da ime već postoji'''
        base_name = filename
        count = 1
        zip_path = os.path.join(zip_folder, f"{base_name}.zip")
        while os.path.exists(zip_path):
            zip_path = os.path.join(zip_folder, f"{base_name}({count}).zip")
            count += 1
        return zip_path

    def chunked_zip(input_file, output_zip, socketio):
        '''Funkcija koja zipuje fajl u delovima'''
        CHUNK_SIZE = 1024 * 1024
        # Otvaranje ZIP fajla u write modu i upisivanje delova fajla u ZIP
        with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Otvaranje fajla u read binary modu i čitanje delova fajla
            with open(input_file, 'rb') as f:
                total_size = os.path.getsize(input_file)
                bytes_written = 0
                # Otvaranje zip fajla u write modu i upisivanje delova fajla u zip
                with zf.open(os.path.basename(input_file), 'w') as zip_entry:
                    chunk = f.read(CHUNK_SIZE)
                    while chunk:
                        # Upisivanje delova fajla u zip
                        zip_entry.write(chunk)
                        bytes_written += len(chunk)
                        progress = (bytes_written / total_size) * 100
                        # Emitovanje progresa zipovanja u procentima
                        socketio.emit('status', {'status': 'zip_progress', 'progress': progress})
                        # Pauziranje izvršavanja programa na 0.2 sekunde kako bi se mogao pratiti progres
                        time.sleep(0.2)
                        # Čitamo sledeći segment
                        chunk = f.read(CHUNK_SIZE)  

        socketio.emit('status', {'status': 'zip_completed'})

    @app.route('/download/<filename>', methods=['GET'])
    def download_file(filename):
        zip_path = os.path.join(app.config['ZIP_FOLDER'], filename)
        if os.path.exists(zip_path):
            return send_file(zip_path, as_attachment=True)
        return jsonify({'error': 'File not found'}), 404

    @app.route('/<filename>', methods=['DELETE'])
    def delete_file(filename):
        '''Brisanje ZIP fajla iz ZIP_FOLDER direktorijuma'''
        # Koristi se ista putanja ali se dodaje DELETE metoda
        zip_path = os.path.join(app.config['ZIP_FOLDER'], filename)
        if os.path.exists(zip_path):
            os.remove(zip_path)
            socketio.emit('file_list_updated')
            return jsonify({'status': 'file_deleted'}), 200
        return jsonify({'error': 'File not found'}), 404

    return app, socketio

if __name__ == '__main__':
    app, socketio = create_app()
    socketio.run(app, host='0.0.0.0', port=5000)
