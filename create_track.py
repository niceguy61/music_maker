import os
import logging
from analyzer import LofiMusicAnalyzer
from playlist_generator import PlaylistGenerator
from utils import check_csv_files, setup_logging
import pandas as pd
from datetime import datetime, timedelta

def generate_track_history(csv_dir):
    """기존 플레이리스트 기록을 분석하여 트랙 사용 이력 생성"""
    try:
        # 모든 플레이리스트 파일 찾기
        playlist_files = [f for f in os.listdir(csv_dir)
                        if f.startswith('playlist_tracks_') and f.endswith('.csv')]
        
        # 전체 트랙 정보 로드
        tracks_df = pd.read_csv(os.path.join(csv_dir, 'tracks.csv'))
        
        # 사용 이력 데이터프레임 초기화
        history_records = []
        
        # 각 플레이리스트 파일 처리
        for playlist_file in playlist_files:
            try:
                # 플레이리스트 타임스탬프 추출
                timestamp = playlist_file.replace('playlist_tracks_', '').replace('.csv', '')
                playlist_df = pd.read_csv(os.path.join(csv_dir, playlist_file))
                
                # 플레이리스트의 각 트랙에 대한 사용 기록 생성
                for _, track in playlist_df.iterrows():
                    history_records.append({
                        'track_id': track['track_id'],
                        'title': track['title'],
                        'artist': track['artist'],
                        'used_at': datetime.strptime(timestamp, '%Y%m%d_%H%M').strftime('%Y-%m-%d %H:%M:%S'),
                        'playlist_id': timestamp
                    })
                logging.info(f"플레이리스트 처리 완료: {playlist_file}")
            except Exception as e:
                logging.error(f"플레이리스트 파일 처리 실패: {playlist_file} - {str(e)}")
                continue
        
        # 사용 이력이 없는 트랙들에 대한 초기 기록 생성
        used_track_ids = set(record['track_id'] for record in history_records)
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        for _, track in tracks_df.iterrows():
            if track['track_id'] not in used_track_ids:
                # 1st 폴더의 트랙은 제외
                if track['folder_name'] != '1st':
                    history_records.append({
                        'track_id': track['track_id'],
                        'title': track['title'],
                        'artist': track['artist'],
                        'used_at': current_time,
                        'playlist_id': 'initial'
                    })
        
        # 사용 이력을 CSV로 저장
        history_df = pd.DataFrame(history_records)
        history_file = os.path.join(csv_dir, 'track_usage_history.csv')
        history_df.to_csv(history_file, index=False, encoding='utf-8-sig')
        
        # 사용 통계 출력
        total_tracks = len(tracks_df)
        used_tracks = len(used_track_ids)
        logging.info(f"\n=== 트랙 사용 이력 생성 완료 ===")
        logging.info(f"전체 트랙 수: {total_tracks}")
        logging.info(f"사용된 트랙 수: {used_tracks}")
        logging.info(f"초기 기록 생성 트랙 수: {len(history_records) - len(used_track_ids)}")
        
        return True
    except Exception as e:
        logging.error(f"트랙 사용 이력 생성 실패: {str(e)}")
        return False

def main():
    import sys
    # 로깅 설정
    setup_logging()
    
    base_path = r"F:\audio_lofi_jazz\reference"
    csv_dir = os.path.join(os.getcwd(), 'csv_output')


    if len(sys.argv) > 1:
        folder_name = sys.argv[1]
        process_specific_folder(folder_name, csv_dir, base_path)
    else:
        # CSV 파일 존재 여부 확인
        csv_exists = check_csv_files(csv_dir)
        
        # 기존 데이터 로드 또는 새로 분석 시작
        analyzer = LofiMusicAnalyzer(base_path)
        if csv_exists:
            logging.info("기존 CSV 파일이 존재합니다. 새로운 폴더 확인 중...")
            # 기존 데이터 로드
            existing_tracks_df = pd.read_csv(os.path.join(csv_dir, 'tracks.csv'))
            analyzed_folders = set(existing_tracks_df['folder_name'].unique())
            
            # 현재 폴더 목록 가져오기
            current_folders = set([f for f in os.listdir(base_path)
                                if os.path.isdir(os.path.join(base_path, f))
                                and f not in ['temp', 'video_result', 'python']])
            
            # 새로 추가된 폴더 확인
            new_folders = current_folders - analyzed_folders
            if new_folders:
                logging.info(f"새로 추가된 폴더 발견: {new_folders}")
                analyzer.analyze_folders()  # 전체 분석 실행
                analyzer.save_to_csv()
                logging.info("새로운 폴더 분석 및 CSV 업데이트 완료")
            else:
                logging.info("새로 추가된 폴더가 없습니다.")
        else:
            logging.info("CSV 파일이 없어 전체 음악 분석을 시작합니다.")
            analyzer.analyze_folders()
            analyzer.save_to_csv()
            logging.info("음악 분석 및 CSV 생성 완료")
        
        # 트랙 사용 이력 생성
        history_file = os.path.join(csv_dir, 'track_usage_history.csv')
        if not os.path.exists(history_file):
            logging.info("트랙 사용 이력 생성 시작")
            generate_track_history(csv_dir)
        
        # # 플레이리스트 생성
        # generator = PlaylistGenerator(
        #     csv_dir=csv_dir,
        #     base_path=base_path,
        #     start_bpm=80,
        #     end_bpm=90,
        #     play_minutes=120
        # )
        
        # result = generator.create_playlist()
        # if result:
        #     logging.info("플레이리스트 생성 완료")
        #     logging.info(f"선택된 트랙 수: {len(result['playlist'])}")
            
        #     # 생성된 콘텐츠 정보 출력
        #     if result.get('content'):
        #         logging.info("\n=== 생성된 YouTube 콘텐츠 ===")
        #         content_lines = result['content'].split('\n')
        #         for line in content_lines:
        #             if line.strip():
        #                 logging.info(line.strip())

def process_specific_folder(folder_name, csv_dir, base_path):
    """특정 폴더의 트랙들로 플레이리스트 생성"""
    try:
        # 트랙 정보 로드
        tracks_df = pd.read_csv(os.path.join(csv_dir, 'tracks.csv'))
        
        # 지정된 폴더의 트랙만 필터링
        folder_tracks = tracks_df[tracks_df['folder_name'] == folder_name].to_dict('records')
        
        if not folder_tracks:
            logging.error(f"지정된 폴더 {folder_name}의 트랙을 찾을 수 없습니다.")
            return False
            
        # PlaylistGenerator 초기화
        generator = PlaylistGenerator(
            csv_dir=csv_dir,
            base_path=base_path,
            start_bpm=80,
            end_bpm=90,
            play_minutes=120
        )
        
        # 챕터 생성
        chapters = generator.generate_chapters(folder_tracks)
        if chapters:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M')
            generator.save_chapter_files(chapters, timestamp)
            
        # RAG 프롬프트 생성 및 Bedrock 응답
        total_duration = sum(track['duration_ms'] for track in folder_tracks)
        prompt = generator.create_rag_prompt(folder_tracks, total_duration)
        content = generator.get_bedrock_response(prompt)
        
        if content:
            # 결과 저장
            generator.save_results(folder_tracks, content)
            
            logging.info(f"\n=== {folder_name} 폴더 처리 완료 ===")
            logging.info(f"트랙 수: {len(folder_tracks)}")
            logging.info(f"총 재생시간: {str(timedelta(milliseconds=total_duration))}")
            
            if content:
                logging.info("\n=== 생성된 YouTube 콘텐츠 ===")
                content_lines = content.split('\n')
                for line in content_lines:
                    if line.strip():
                        logging.info(line.strip())
                        
            return True
            
        return False
        
    except Exception as e:
        logging.error(f"폴더 처리 실패: {str(e)}")
        return False

if __name__ == "__main__":
    main()