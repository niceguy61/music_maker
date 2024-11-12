import os
import logging
import pandas as pd

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('music_analysis.log', encoding='utf-8')
        ]
    )

def check_csv_files(csv_dir):
    required_files = ['tracks.csv', 'episodes.csv', 'track_episodes.csv']
    try:
        if not os.path.exists(csv_dir):
            logging.info(f"CSV 디렉토리를 생성합니다: {csv_dir}")
            os.makedirs(csv_dir, exist_ok=True)
            return False
            
        for file_name in required_files:
            file_path = os.path.join(csv_dir, file_name)
            if not os.path.isfile(file_path):
                logging.info(f"필요한 CSV 파일이 없습니다: {file_name}")
                return False
                
            if os.path.getsize(file_path) == 0:
                logging.info(f"CSV 파일이 비어 있습니다: {file_name}")
                return False
                
            if not os.access(file_path, os.R_OK):
                logging.error(f"CSV 파일에 대한 읽기 권한이 없습니다: {file_name}")
                return False
                
            try:
                df = pd.read_csv(file_path)
                if len(df) == 0:
                    logging.info(f"CSV 파일에 데이터가 없습니다: {file_name}")
                    return False
            except Exception as e:
                logging.error(f"CSV 파일 읽기 실패: {file_name} - {str(e)}")
                return False
                
        logging.info("모든 CSV 파일이 정상적으로 존재합니다.")
        return True
        
    except Exception as e:
        logging.error(f"CSV 파일 검사 중 오류 발생: {str(e)}")
        return False