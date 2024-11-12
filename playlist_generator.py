import os
import json
import logging
import random
import time
import boto3
from datetime import datetime, timedelta
import pandas as pd
from botocore.exceptions import ClientError

class PlaylistGenerator:
    def __init__(self, csv_dir, base_path, start_bpm=70, end_bpm=85, play_minutes=120):
        self.csv_dir = csv_dir
        self.base_path = base_path
        self.tracks = None
        self.start_bpm = start_bpm
        self.end_bpm = end_bpm
        self.target_duration_ms = play_minutes * 60 * 1000
        self.session = self.get_aws_session()
        self.bedrock = self.session.client('bedrock-runtime', region_name='ap-northeast-2')
        
    def get_aws_session(self):
        """AWS 세션 생성"""
        try:
            session = boto3.Session(profile_name='sso')
            return session
        except Exception as e:
            logging.error(f"AWS 프로파일 로드 실패: {e}")
            raise
            
    def create_playlist(self):
        """플레이리스트 생성"""
        if not self.load_tracks_from_csv():
            return None
            
        # BPM 범위로 트랙 필터링
        suitable_tracks = [
            track for track in self.tracks
            if self.start_bpm <= track['bpm'] <= self.end_bpm
        ]
        
        if not suitable_tracks:
            logging.error("적절한 BPM 범위의 트랙이 없습니다.")
            return None
            
        # 트랙 사용 이력 로드
        history_file = os.path.join(self.csv_dir, 'track_usage_history.csv')
        if os.path.exists(history_file):
            history_df = pd.read_csv(history_file)
            usage_counts = history_df['track_id'].value_counts()
        else:
            usage_counts = pd.Series(dtype=int)
            
        # 사용 횟수가 적은 순서로 정렬 (같은 사용 횟수면 BPM으로 정렬)
        suitable_tracks.sort(key=lambda x: (usage_counts.get(x['track_id'], 0), x['bpm']))
        
        playlist = []
        current_duration = 0
        used_tracks = set()
        
        # 목표 시간에 도달할 때까지 반복
        while current_duration < self.target_duration_ms:
            # 사용 가능한 트랙 필터링 (3회 미만 사용된 트랙만)
            available_tracks = [
                t for t in suitable_tracks
                if t['track_id'] not in used_tracks and
                usage_counts.get(t['track_id'], 0) < 3
            ]
            
            if not available_tracks:
                # 모든 트랙을 다 사용했거나, 남은 트랙이 없는 경우
                logging.warning(f"더 이상 사용 가능한 트랙이 없습니다. 현재 재생시간: {str(timedelta(milliseconds=current_duration))}")
                break
                
            # 남은 시간을 고려하여 적절한 길이의 트랙 선택
            remaining_time = self.target_duration_ms - current_duration
            
            # 남은 시간에 맞는 트랙 찾기
            suitable_duration_tracks = [
                t for t in available_tracks
                if t['duration_ms'] <= remaining_time
            ]
            
            if not suitable_duration_tracks:
                # 남은 시간에 맞는 트랙이 없으면 가장 짧은 트랙 선택
                track = min(available_tracks, key=lambda x: x['duration_ms'])
            else:
                # 남은 시간에 맞는 트랙 중 첫 번째 선택
                track = suitable_duration_tracks[0]
                
            usage_count = usage_counts.get(track['track_id'], 0)
            logging.info(f"트랙 선택: {track['title']} (이전 사용: {usage_count}회, 길이: {str(timedelta(milliseconds=track['duration_ms']))})")
            
            playlist.append(track)
            used_tracks.add(track['track_id'])
            current_duration += track['duration_ms']
            
            # 현재 진행상황 로깅
            progress_percent = (current_duration / self.target_duration_ms) * 100
            logging.info(f"현재 진행률: {progress_percent:.1f}% ({str(timedelta(milliseconds=current_duration))} / {str(timedelta(milliseconds=self.target_duration_ms))})")
            
        if playlist:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M')
            
            # 챕터 생성
            chapters = self.generate_chapters(playlist)
            if chapters:
                self.save_chapter_files(chapters, timestamp)
                
            # Bedrock 프롬프트 생성 및 응답 받기
            prompt = self.create_rag_prompt(playlist, self.target_duration_ms)
            content = self.get_bedrock_response(prompt)
            
            if content:
                # 결과 저장
                self.save_results(playlist, content)
                
                # 다음 에피소드 폴더 생성 및 파일 복사
                episode_result = self.create_next_episode_folder(playlist)
                if episode_result:
                    logging.info(f"다음 에피소드 준비 완료: {episode_result['folder_name']}")
                    
                return {
                    'playlist': playlist,
                    'content': content,
                    'chapters': chapters,
                    'next_episode': episode_result
                }
                
        return None
        
    def load_tracks_from_csv(self):
        """CSV에서 트랙 정보 로드"""
        try:
            tracks_df = pd.read_csv(os.path.join(self.csv_dir, 'tracks.csv'))
            self.tracks = tracks_df.to_dict('records')
            logging.info(f"로드된 트랙 수: {len(self.tracks)}")
            return True
        except Exception as e:
            logging.error(f"CSV 로드 실패: {e}")
            return False
            
    def generate_chapters(self, playlist):
        """플레이리스트로부터 YouTube 챕터와 SRT 타임스탬프 생성"""
        try:
            chapters = []
            current_ms = 0
            
            for track in playlist:
                # YouTube 챕터용 타임스탬프 (HH:MM:SS)
                hours = current_ms // 3600000
                minutes = (current_ms % 3600000) // 60000
                seconds = (current_ms % 60000) // 1000
                chapter_timestamp = f'{hours:02d}:{minutes:02d}:{seconds:02d}'
                
                # SRT용 타임스탬프 (HH:MM:SS,mmm)
                srt_start = self.format_srt_timestamp(current_ms)
                srt_end = self.format_srt_timestamp(current_ms + track['duration_ms'])
                
                chapters.append({
                    'timestamp': chapter_timestamp,
                    'srt_start': srt_start,
                    'srt_end': srt_end,
                    'title': track['title'],
                    'artist': track['artist'],
                    'duration_ms': track['duration_ms']
                })
                
                current_ms += track['duration_ms']
                
            return chapters
            
        except Exception as e:
            logging.error(f"챕터 생성 실패: {str(e)}")
            return None
            
    def create_rag_prompt(self, suitable_tracks, target_duration_ms):
        """RAG 데이터를 활용한 프롬프트 생성"""
        try:
            # 전체 트랙 정보를 RAG 데이터로 구성
            tracks_info = []
            for track in suitable_tracks:
                tracks_info.append(
                    f"- {track['title']} (아티스트: {track['artist']}, "
                    f"BPM: {track['bpm']}, "
                    f"장르: {track['genre']}, "
                    f"길이: {str(timedelta(milliseconds=track['duration_ms']))}, "
                    f"드럼강도: {track['drum_intensity']}, "
                    f"하모닉복잡도: {track['harmonic_complexity']})"
                )
                
            target_duration = str(timedelta(milliseconds=target_duration_ms))
            tracks_list = "\n".join(tracks_info)
            
            prompt = f"""당신은 로파이 힙합/재즈 플레이리스트 큐레이터입니다.
            아래 조건과 트랙 목록을 기반으로 최적의 플레이리스트를 생성해주세요.
            
            조건:
            1. 목표 재생시간: {target_duration}
            2. BPM 범위: {self.start_bpm}-{self.end_bpm}
            3. 트랙 선택 기준:
            - BPM의 자연스러운 흐름
            - 장르의 적절한 분배
            - 드럼강도와 하모닉복잡도의 조화
            - 아티스트 중복 최소화
            
            사용 가능한 트랙 목록:
            {tracks_list}
            
            다음 형식으로 응답해주세요:
            1. 플레이리스트 설명:
            - 분위기 설명
            - 장르 구성 설명
            
            2. 유튜브 콘텐츠:
            - 제목: (감성적이고 매력적인 제목)
            - 설명: (플레이리스트 특징과 분위기)
            - 해시태그: (해당 플레이리스트와 어울리게 5 ~ 10개로 생성, 쉼표로 split 할것)
            """
            
            return prompt
            
        except Exception as e:
            logging.error(f"RAG 프롬프트 생성 실패: {str(e)}")
            return None
            
    def get_bedrock_response(self, prompt):
        """Bedrock Claude 3 Sonnet API 호출"""
        max_retries = 5
        base_delay = 1  # 기본 1초 대기
        
        for attempt in range(max_retries):
            try:
                body = json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "temperature": 0.7,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                })
                
                response = self.bedrock.invoke_model(
                    modelId="anthropic.claude-3-5-sonnet-20240620-v1:0",
                    body=body,
                    contentType="application/json",
                    accept="application/json"
                )
                
                response_body = json.loads(response.get('body').read())
                return response_body['content'][0]['text']
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'ThrottlingException':
                    if attempt < max_retries - 1:  # 마지막 시도가 아닌 경우에만 재시도
                        # 지수 백오프 with jitter 적용
                        delay = (base_delay * (2 ** attempt)) + (random.random() * 0.1)
                        logging.warning(f"요청 제한으로 {delay:.2f}초 대기 후 재시도 ({attempt + 1}/{max_retries})")
                        time.sleep(delay)
                        continue
                logging.error(f"Bedrock API 호출 실패: {e}")
                logging.error(f"상세 에러: {str(e)}")
                return None
            except Exception as e:
                logging.error(f"Bedrock API 호출 실패: {e}")
                logging.error(f"상세 에러: {str(e)}")
                return None
                
    def save_results(self, playlist, content):
        """결과 저장"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M')
            
            # 플레이리스트 저장
            pd.DataFrame(playlist).to_csv(
                os.path.join(self.csv_dir, f'playlist_tracks_{timestamp}.csv'),
                index=False,
                encoding='utf-8-sig'
            )
            
            # 유튜브 콘텐츠 저장
            with open(os.path.join(self.csv_dir, f'youtube_content_{timestamp}.txt'), 'w', encoding='utf-8') as f:
                f.write(content)
                
            # 트랙 사용 이력 저장
            history_file = os.path.join(self.csv_dir, 'track_usage_history.csv')
            
            # 기존 사용 이력 로드 또는 새로 생성
            if os.path.exists(history_file):
                history_df = pd.read_csv(history_file)
            else:
                history_df = pd.DataFrame(columns=['track_id', 'title', 'artist', 'used_at', 'playlist_id'])
                
            # 새로운 사용 이력 추가
            new_records = []
            for track in playlist:
                new_records.append({
                    'track_id': track['track_id'],
                    'title': track['title'],
                    'artist': track['artist'],
                    'used_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'playlist_id': timestamp
                })
                
            # 기존 이력과 새로운 이력 합치기
            updated_history = pd.concat([
                history_df,
                pd.DataFrame(new_records)
            ], ignore_index=True)
            
                        # 사용 이력 저장
            updated_history.to_csv(history_file, index=False, encoding='utf-8-sig')
            
            logging.info("결과 저장 완료")
            logging.info(f"트랙 사용 이력 업데이트: {len(new_records)}곡")
            
        except Exception as e:
            logging.error(f"결과 저장 실패: {e}")
            
    def format_srt_timestamp(self, ms):
        """밀리초를 SRT 타임스탬프 형식(HH:MM:SS,mmm)으로 변환"""
        hours = ms // 3600000
        ms = ms % 3600000
        minutes = ms // 60000
        ms = ms % 60000
        seconds = ms // 1000
        ms = ms % 1000
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"
        
    def save_chapter_files(self, chapters, timestamp):
        """챕터 정보를 SRT와 TXT 형식으로 저장"""
        try:
            # TXT 파일 생성
            txt_path = os.path.join(self.csv_dir, f'youtube_chapters_{timestamp}.txt')
            with open(txt_path, 'w', encoding='utf-8') as f:
                for chapter in chapters:
                    f.write(f"{chapter['timestamp']} {chapter['title']} - {chapter['artist']}\n")
                    
            # SRT 파일 생성
            srt_path = os.path.join(self.csv_dir, f'youtube_chapters_{timestamp}.srt')
            with open(srt_path, 'w', encoding='utf-8') as f:
                for i, chapter in enumerate(chapters, 1):
                    f.write(f"{i}\n")
                    f.write(f"{chapter['srt_start']} --> {chapter['srt_end']}\n")
                    f.write(f"{chapter['title']} - {chapter['artist']}\n\n")
                    
            logging.info(f"챕터 파일 생성 완료: {txt_path}, {srt_path}")
            return True
            
        except Exception as e:
            logging.error(f"챕터 파일 저장 실패: {str(e)}")
            return False
            
    def create_next_episode_folder(self, playlist):
        """다음 에피소드 폴더 생성 및 선택된 트랙 복사"""
        try:
            # 현재 존재하는 폴더 확인
            folders = [f for f in os.listdir(self.base_path)
                      if os.path.isdir(os.path.join(self.base_path, f))
                      and f not in ['temp', 'video_result', 'python']]
                      
            # 숫자로 끝나는 폴더 찾기
            episode_folders = []
            for folder in folders:
                if folder.endswith(('th', 'st', 'nd', 'rd')):
                    try:
                        num = int(''.join(filter(str.isdigit, folder)))
                        episode_folders.append((num, folder))
                    except:
                        continue
                        
            if not episode_folders:
                next_num = 1
                suffix = 'st'
            else:
                current_max = max(num for num, _ in episode_folders)
                next_num = current_max + 1
                
                # 접미사 결정
                if next_num % 10 == 1 and next_num != 11:
                    suffix = 'st'
                elif next_num % 10 == 2 and next_num != 12:
                    suffix = 'nd'
                elif next_num % 10 == 3 and next_num != 13:
                    suffix = 'rd'
                else:
                    suffix = 'th'
                    
            # 새 폴더 생성
            new_folder_name = f"{next_num}{suffix}"
            new_folder_path = os.path.join(self.base_path, new_folder_name)
            os.makedirs(new_folder_path, exist_ok=True)
            
            # 선택된 트랙 복사
            copied_files = []
            for track in playlist:
                src_path = os.path.join(self.base_path, track['folder_name'], track['file_name'])
                dst_path = os.path.join(new_folder_path, track['file_name'])
                
                if os.path.exists(src_path):
                    import shutil
                    shutil.copy2(src_path, dst_path)
                    copied_files.append(track['file_name'])
                    
            logging.info(f"새 에피소드 폴더 생성: {new_folder_name}")
            logging.info(f"복사된 파일 수: {len(copied_files)}")
            
            return {
                'folder_name': new_folder_name,
                'copied_files': copied_files
            }
            
        except Exception as e:
            logging.error(f"에피소드 폴더 생성 실패: {str(e)}")
            return None
            
    def update_episode_records(self, playlist, new_folder_name):
        """에피소드 및 트랙-에피소드 레코드 업데이트"""
        try:
            # 기존 레코드 로드
            episodes_df = pd.read_csv(os.path.join(self.csv_dir, 'episodes.csv'))
            track_episodes_df = pd.read_csv(os.path.join(self.csv_dir, 'track_episodes.csv'))
            
            # 새 에피소드 ID
            new_episode_id = max(episodes_df['episode_id']) + 1
            
            # 새 에피소드 레코드 추가
            new_episode = {
                'episode_id': new_episode_id,
                'episode_name': new_folder_name,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            episodes_df = pd.concat([episodes_df, pd.DataFrame([new_episode])], ignore_index=True)
            
            # 새 트랙-에피소드 레코드 추가
            new_track_episode_id = max(track_episodes_df['track_episode_id']) + 1
            new_track_episodes = []
            
            for order, track in enumerate(playlist, 1):
                new_track_episodes.append({
                    'track_episode_id': new_track_episode_id + order - 1,
                    'track_id': track['track_id'],
                    'episode_id': new_episode_id,
                    'order_in_episode': order
                })
                
            track_episodes_df = pd.concat([
                track_episodes_df,
                pd.DataFrame(new_track_episodes)
            ], ignore_index=True)
            
            # CSV 파일 업데이트
            episodes_df.to_csv(os.path.join(self.csv_dir, 'episodes.csv'), index=False, encoding='utf-8-sig')
            track_episodes_df.to_csv(os.path.join(self.csv_dir, 'track_episodes.csv'), index=False, encoding='utf-8-sig')
            
            logging.info(f"에피소드 레코드 업데이트 완료: {new_folder_name}")
            return True
            
        except Exception as e:
            logging.error(f"에피소드 레코드 업데이트 실패: {str(e)}")
            return False
    
    def process_existing_tracks(self, playlist_file):
        """기존 플레이리스트 파일을 처리하여 RAG 프롬프트와 SRT 생성"""
        try:
            # 플레이리스트 파일 로드
            playlist_df = pd.read_csv(os.path.join(self.csv_dir, playlist_file))
            
            # 타임스탬프 추출
            timestamp = playlist_file.replace('playlist_tracks_', '').replace('.csv', '')
            
            # 트랙 정보 로드
            if not self.load_tracks_from_csv():
                return None
                
            # 플레이리스트의 트랙 정보 구성
            playlist = []
            total_duration = 0
            
            for _, row in playlist_df.iterrows():
                track_info = next(
                    (t for t in self.tracks if t['track_id'] == row['track_id']),
                    None
                )
                if track_info:
                    playlist.append(track_info)
                    total_duration += track_info['duration_ms']
                    
            if not playlist:
                logging.error("플레이리스트에서 유효한 트랙을 찾을 수 없습니다.")
                return None
                
            # 챕터 생성
            chapters = self.generate_chapters(playlist)
            if chapters:
                self.save_chapter_files(chapters, timestamp)
                
            # RAG 프롬프트 생성 및 Bedrock 응답 받기
            prompt = self.create_rag_prompt(playlist, total_duration)
            content = self.get_bedrock_response(prompt)
            
            if content:
                # 유튜브 콘텐츠 저장
                content_file = os.path.join(self.csv_dir, f'youtube_content_{timestamp}.txt')
                with open(content_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                    
                return {
                    'playlist': playlist,
                    'content': content,
                    'chapters': chapters,
                    'timestamp': timestamp
                }
                
            return None
            
        except Exception as e:
            logging.error(f"기존 트랙 처리 실패: {str(e)}")
            return None