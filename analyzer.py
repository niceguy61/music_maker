import os
import logging
import numpy as np
import json
import librosa
from mutagen import File
from mutagen.mp3 import MP3
import pandas as pd
from datetime import datetime

class LofiMusicAnalyzer:
    def __init__(self, base_path):
        self.base_path = base_path
        self.output_dir = os.path.join(os.getcwd(), 'csv_output')
        os.makedirs(self.output_dir, exist_ok=True)
        self.tracks = []
        self.episodes = []
        self.track_episodes = []
        
    def analyze_genre(self, y, sr):
        """오디오 특성을 분석하여 장르 판별"""
        try:
            # tempo 처리 수정
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            if isinstance(tempo, np.ndarray):
                tempo = float(tempo[0])  # 배열의 첫 번째 요소만 사용
            else:
                tempo = float(tempo)
                
            y_harmonic, y_percussive = librosa.effects.hpss(y)
            percussive_rms = float(np.sqrt(np.mean(y_percussive**2)))
            
            chroma = librosa.feature.chroma_stft(y=y_harmonic, sr=sr)
            chroma_complexity = float(np.std(chroma))
            
            if percussive_rms > 0.1 and 70 <= tempo <= 100:
                genre = 'Lo-fi Hip Hop'
                sub_genre = 'Hip Hop'
            else:
                genre = 'Lo-fi Jazz'
                sub_genre = 'Jazz'
                
            return {
                'genre': genre,
                'sub_genre': sub_genre,
                'tempo': round(tempo, 2),
                'drum_intensity': round(percussive_rms, 3),
                'harmonic_complexity': round(chroma_complexity, 3)
            }
            
        except Exception as e:
            logging.error(f"장르 분석 실패: {str(e)}")
            return {
                'genre': 'Lo-fi',
                'sub_genre': 'Unknown',
                'tempo': 0,
                'drum_intensity': 0,
                'harmonic_complexity': 0
            }
            
    def adjust_bpm(self, bpm):
        """BPM을 60-100 범위 내로 조정"""
        if bpm == 0:
            return 0
            
        while bpm > 100:
            bpm = bpm / 2
            
        while bpm < 60:
            bpm = bpm * 2
            
        return round(bpm, 2)
        
    def analyze_folders(self):
        """폴더 분석 및 트랙 정보 수집"""
        # 기존 CSV 파일이 있다면 로드
        if os.path.exists(os.path.join(self.output_dir, 'tracks.csv')):
            existing_tracks = pd.read_csv(os.path.join(self.output_dir, 'tracks.csv')).to_dict('records')
            existing_episodes = pd.read_csv(os.path.join(self.output_dir, 'episodes.csv')).to_dict('records')
            existing_track_episodes = pd.read_csv(os.path.join(self.output_dir, 'track_episodes.csv')).to_dict('records')
            
            # 기존 데이터 복원
            self.tracks = existing_tracks
            self.episodes = existing_episodes
            self.track_episodes = existing_track_episodes
            
            # 마지막 ID들 찾기
            track_id = max([t['track_id'] for t in existing_tracks]) + 1 if existing_tracks else 1
            episode_id = max([e['episode_id'] for e in existing_episodes]) + 1 if existing_episodes else 1
            track_episode_id = max([te['track_episode_id'] for te in existing_track_episodes]) + 1 if existing_track_episodes else 1
            
            # 기존 트랙 맵과 에피소드 맵 생성
            track_map = {f"{t['title']}_{t['artist']}": t['track_id'] for t in existing_tracks}
            episode_map = {e['episode_name']: e['episode_id'] for e in existing_episodes}
            
            # 기존 분석된 폴더 목록
            analyzed_folders = set(e['episode_name'] for e in existing_episodes)
            logging.info(f"기존 분석된 폴더: {sorted(analyzed_folders)}")
        else:
            track_id = 1
            episode_id = 1
            track_episode_id = 1
            track_map = {}
            episode_map = {}
            analyzed_folders = set()
            
        def folder_sort_key(folder_name):
            try:
                if folder_name.endswith('th'):
                    return int(folder_name[:-2])
                elif folder_name.endswith(('st', 'nd', 'rd')):
                    return int(folder_name[:-2])
                return 0
            except:
                return 0
                
        # 현재 폴더 목록 가져오기
        current_folders = sorted([
            f for f in os.listdir(self.base_path)
            if os.path.isdir(os.path.join(self.base_path, f))
            and f not in ['temp', 'video_result', 'python']
        ], key=folder_sort_key)
        
        # 새로 추가된 폴더만 분석
        new_folders = [f for f in current_folders if f not in analyzed_folders]
        if not new_folders:
            logging.info("새로 추가된 폴더가 없습니다.")
            return
            
        logging.info(f"새로 분석할 폴더: {sorted(new_folders)}")
        
        for folder_name in new_folders:
            folder_path = os.path.join(self.base_path, folder_name)
            logging.info(f"폴더 분석 중: {folder_name}")
            
            # 새로운 에피소드 추가
            if folder_name not in episode_map:
                self.episodes.append({
                    'episode_id': episode_id,
                    'episode_name': folder_name,
                    'created_at': datetime.fromtimestamp(os.path.getctime(folder_path)).strftime('%Y-%m-%d %H:%M:%S')
                })
                episode_map[folder_name] = episode_id
                episode_id += 1
                
            mp3_files = sorted([
                f for f in os.listdir(folder_path)
                if f.endswith('.mp3') and f.startswith('ES_')
            ])
            
            for order, file_name in enumerate(mp3_files, 1):
                file_path = os.path.join(folder_path, file_name)
                logging.info(f"파일 분석 중: {file_name}")
                
                try:
                    name_parts = file_name.replace('ES_', '').split(' - ')
                    if len(name_parts) >= 2:
                        title = name_parts[0].strip()
                        artist = name_parts[-1].replace('.mp3', '').strip()
                    else:
                        title = os.path.splitext(file_name)[0].replace('ES_', '')
                        artist = 'Unknown'
                        
                    track_key = f"{title}_{artist}"
                    
                    # 이미 분석된 트랙인지 확인
                    if track_key not in track_map:
                        audio_features = self.get_audio_features(file_path)
                        
                        track_info = {
                            'track_id': track_id,
                            'title': title,
                            'artist': artist,
                            'bpm': audio_features['bpm'],
                            'duration_ms': audio_features['duration_ms'],
                            'file_name': file_name,
                            'folder_name': folder_name,
                            'genre': audio_features['genre'],
                            'sub_genre': audio_features['sub_genre'],
                            'drum_intensity': audio_features['drum_intensity'],
                            'harmonic_complexity': audio_features['harmonic_complexity']
                        }
                        
                        self.tracks.append(track_info)
                        track_map[track_key] = track_id
                        current_track_id = track_id
                        track_id += 1
                    else:
                        current_track_id = track_map[track_key]
                        
                    self.track_episodes.append({
                        'track_episode_id': track_episode_id,
                        'track_id': current_track_id,
                        'episode_id': episode_map[folder_name],
                        'order_in_episode': order
                    })
                    track_episode_id += 1
                    
                except Exception as e:
                    logging.error(f"파일 처리 실패: {file_name} - {str(e)}")
                    continue
                    
            logging.info(f"{folder_name} 폴더 처리 완료: {len(mp3_files)}개 파일")
            
        # 분석 결과 저장
        self.save_to_csv()
        logging.info(f"전체 분석 완료: 기존 {len(analyzed_folders)}개 + 신규 {len(new_folders)}개 = 총 {len(analyzed_folders) + len(new_folders)}개 폴더")
        
    def get_audio_features(self, file_path):
        """오디오 파일 분석"""
        try:
            y, sr = librosa.load(file_path, duration=60)
            audio = MP3(file_path)
            duration_ms = int(audio.info.length * 1000)
            
            genre_info = self.analyze_genre(y, sr)
            bpm = self.adjust_bpm(genre_info['tempo'])
            
            return {
                'bpm': bpm,
                'duration_ms': duration_ms,
                'genre': genre_info['genre'],
                'sub_genre': genre_info['sub_genre'],
                'drum_intensity': genre_info['drum_intensity'],
                'harmonic_complexity': genre_info['harmonic_complexity']
            }
            
        except Exception as e:
            logging.error(f"오디오 분석 실패: {file_path} - {str(e)}")
            return {
                'bpm': 0,
                'duration_ms': 0,
                'genre': 'Unknown',
                'sub_genre': 'Unknown',
                'drum_intensity': 0,
                'harmonic_complexity': 0
            }
            
    def save_to_csv(self):
        """분석 결과를 CSV로 저장"""
        try:
            pd.DataFrame(self.tracks).to_csv(
                os.path.join(self.output_dir, 'tracks.csv'),
                index=False,
                encoding='utf-8-sig'
            )
            
            pd.DataFrame(self.episodes).to_csv(
                os.path.join(self.output_dir, 'episodes.csv'),
                index=False,
                encoding='utf-8-sig'
            )
            
            pd.DataFrame(self.track_episodes).to_csv(
                os.path.join(self.output_dir, 'track_episodes.csv'),
                index=False,
                encoding='utf-8-sig'
            )
            
            logging.info(f"CSV 파일 저장 완료: {self.output_dir}")
        except Exception as e:
            logging.error(f"CSV 저장 실패: {str(e)}")
            
    def format_srt_timestamp(self, ms):
        """밀리초를 SRT 타임스탬프 형식(HH:MM:SS,mmm)으로 변환"""
        hours = ms // 3600000
        ms = ms % 3600000
        minutes = ms // 60000
        ms = ms % 60000
        seconds = ms // 1000
        ms = ms % 1000
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"